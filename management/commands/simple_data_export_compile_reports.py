# -*- coding: utf-8 -*-
# pylint: disable=no-member,line-too-long

from __future__ import print_function

from builtins import str # pylint: disable=redefined-builtin

import importlib
import io
import json
import logging
import os
import tempfile
import traceback
import zipfile

import arrow
import pytz
import zipstream

from django.conf import settings
from django.core.files import File
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from quicksilver.decorators import handle_lock, handle_schedule, handle_logging, add_qs_arguments

from ...models import ReportJob, ReportJobBatchRequest, ReportDestination

REMOVE_SLEEP_MAX = 60 # Added to avoid "WindowsError: [Error 32] The process cannot access the file because it is being used by another process"

class Command(BaseCommand):
    help = 'Compiles request data export reports.'

    @add_qs_arguments
    def add_arguments(self, parser):
        pass

    @handle_logging
    @handle_schedule
    @handle_lock
    def handle(self, *args, **options): # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        os.umask(000)

        here_tz = pytz.timezone(settings.TIME_ZONE)

        pending = ReportJob.objects.filter(started=None, completed=None)

        logger = options.get('_logger', None)

        if logger is None:
            logger = logging.getLogger(__name__)

        logger.debug('%s: Pending report jobs: %s', __name__, pending.count())

        while pending.count() > 0:
            report = ReportJob.objects.filter(started=None, completed=None)\
                                      .order_by('requested', 'pk')\
                                      .first()

            if report is not None:
                report.started = timezone.now()
                report.save()

                parameters = json.loads(report.parameters)

                data_sources = parameters['data_sources']
                data_types = parameters['data_types']

                custom_parameters = parameters['custom_parameters']

                start_time = None
                end_time = None

                if 'start_time' in parameters and parameters['start_time']:
                    start_time = arrow.get(parameters['start_time']).datetime

                if 'end_time' in parameters and parameters['end_time']:
                    end_time = arrow.get(parameters['end_time']).datetime

                prefix = 'simple_data_export_final'

                if 'prefix' in parameters:
                    prefix = parameters['prefix']

                suffix = report.started.astimezone(here_tz).date().isoformat()

                if 'suffix' in parameters:
                    suffix = parameters['suffix']

                filename = tempfile.gettempdir() + os.path.sep + prefix + '_' + str(report.pk) + '_' + suffix + '.zip'

                zips_to_merge = []

                with io.open(filename, 'wb') as final_output_file:
                    with zipstream.ZipFile(mode='w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as export_stream: # pylint: disable=line-too-long
                        to_delete = []

                        for data_type in data_types: # pylint: disable=too-many-nested-blocks
                            output_file = None

                            for app in settings.INSTALLED_APPS:
                                if output_file is None:
                                    try:
                                        export_api = importlib.import_module(app + '.simple_data_export_api')

                                        try:
                                            file_path = export_api.compile_data_export(data_type, data_sources, start_time=start_time, end_time=end_time, custom_parameters=custom_parameters)

                                            if file_path is not None:
                                                output_file = os.path.normpath(file_path)

                                                if output_file is not None:
                                                    output_file = os.path.normpath(output_file)

                                                    if output_file.lower().endswith('.zip'):
                                                        zips_to_merge.append(output_file)
                                                    else:
                                                        name = os.path.basename(os.path.normpath(output_file))

                                                        export_stream.write(output_file, name, compress_type=zipfile.ZIP_DEFLATED)

                                                        to_delete.append(output_file)
                                        except TypeError as exception:
                                            traceback.print_exc()
                                            logger.error('Verify that %s "%s" exporter implements all compile_data_export arguments!', app, data_type)
                                            raise exception

                                    except ImportError:
                                        output_file = None
                                    except AttributeError:
                                        output_file = None

                        for data in export_stream:
                            final_output_file.write(data)

                        for output_file in to_delete:
                            remove_sleep = 1.0

                            while remove_sleep < REMOVE_SLEEP_MAX:
                                try:
                                    os.remove(output_file)

                                    remove_sleep = REMOVE_SLEEP_MAX
                                except OSError:
                                    remove_sleep = remove_sleep * 2

                                    if remove_sleep >= REMOVE_SLEEP_MAX:
                                        traceback.print_exc()

                if zips_to_merge:
                    with zipfile.ZipFile(filename, 'a', compression=zipfile.ZIP_DEFLATED) as zip_output:
                        for zip_filename in zips_to_merge:
                            with zipfile.ZipFile(zip_filename, 'r') as zip_file:
                                for child_file in zip_file.namelist():
                                    with zip_file.open(child_file) as child_stream:
                                        zip_output.writestr(child_file, child_stream.read())

                report.completed = timezone.now()

                with io.open(filename, 'rb') as report_file:
                    report.report.save(filename.split(os.path.sep)[-1], File(report_file))

                report.save()

                if report.requester.email is not None:
                    site_human_name = 'Simple Data Exporter'

                    try:
                        site_human_name = settings.SIMPLE_DATA_EXPORTER_SITE_NAME
                    except AttributeError:
                        pass

                    subject = render_to_string('simple_data_export_report_subject.txt', {
                        'report': report,
                        'url': settings.SITE_URL,
                        'name': site_human_name
                    })

                    if 'email_subject' in parameters:
                        subject = parameters['email_subject']

                    message = render_to_string('simple_data_export_report_message.txt', {
                        'report': report,
                        'url': settings.SITE_URL,
                        'name': site_human_name
                    })

                    tokens = settings.SITE_URL.split('/')
                    host = ''

                    while tokens and tokens[-1] == '':
                        tokens.pop()

                    if tokens:
                        host = tokens[-1]

                    from_addr = site_human_name + ' <noreply@' + host + '>'

                    try:
                        from_addr = settings.SIMPLE_DATA_EXPORT_FROM_ADDRESS

                    except AttributeError:
                        pass

                    send_mail(subject, message, from_addr, [report.requester.email], fail_silently=False)

                try:
                    for extra_destination in ReportDestination.objects.filter(user=report.requester):
                        extra_destination.transmit(filename, report)
                except AttributeError:
                    traceback.print_exc()

                remove_sleep = 1.0

                while remove_sleep < REMOVE_SLEEP_MAX:
                    try:
                        os.remove(filename)

                        remove_sleep = REMOVE_SLEEP_MAX
                    except OSError:
                        remove_sleep = remove_sleep * 2

                        if remove_sleep >= REMOVE_SLEEP_MAX:
                            traceback.print_exc()

        request = ReportJobBatchRequest.objects.filter(started=None, completed=None)\
                      .order_by('requested', 'pk')\
                      .first()

        logger.debug('%s: Pending report job batch request: %s', __name__, request)

        if request is not None:
            request.process()

        logger.debug('%s: Going to sleep...', __name__)
