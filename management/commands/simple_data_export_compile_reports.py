# -*- coding: utf-8 -*-
# pylint: disable=no-member,line-too-long

from __future__ import print_function

from builtins import str # pylint: disable=redefined-builtin

import datetime
import importlib
import io
import json
import os
import tempfile
import traceback
import zipfile

import zipstream

import pytz

from django.conf import settings
from django.core.files import File
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from quicksilver.decorators import handle_lock, handle_schedule, add_qs_arguments

from ...models import ReportJob, ReportJobBatchRequest

REMOVE_SLEEP_MAX = 60 # Added to avoid "WindowsError: [Error 32] The process cannot access the file because it is being used by another process"

class Command(BaseCommand):
    help = 'Compiles request data export reports.'

    @add_qs_arguments
    def add_arguments(self, parser):
        pass

    @handle_lock
    @handle_schedule
    def handle(self, *args, **options): # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        os.umask(000)

        pending = ReportJob.objects.filter(started=None, completed=None)

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

                tz_info = pytz.timezone(settings.TIME_ZONE)

                if 'start_time' in parameters and parameters['start_time']:
                    tokens = parameters['start_time'].split('/')

                    start_time = datetime.datetime(int(tokens[2]), \
                                                   int(tokens[0]), \
                                                   int(tokens[1]), \
                                                   0, \
                                                   0, \
                                                   0, \
                                                   0, \
                                                   tz_info)

                if 'end_time' in parameters and parameters['end_time']:
                    tokens = parameters['end_time'].split('/')

                    end_time = datetime.datetime(int(tokens[2]), \
                                                 int(tokens[0]), \
                                                 int(tokens[1]), \
                                                 23, \
                                                 59, \
                                                 59, \
                                                 999999, \
                                                 tz_info)

                prefix = 'simple_data_export_final'

                if 'prefix' in parameters:
                    prefix = parameters['prefix']

                suffix = report.started.date().isoformat()

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
                                            output_file = os.path.normpath(export_api.compile_data_export(data_type, data_sources, start_time=start_time, end_time=end_time, custom_parameters=custom_parameters))

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
                                            print('Verify that ' + app + ' "' + data_type + '" exporter implements all compile_data_export arguments!')
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
                    with zipfile.ZipFile(filename, 'a') as zip_output:
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
                    subject = render_to_string('simple_data_export_report_subject.txt', {
                        'report': report,
                        'url': settings.SITE_URL
                    })

                    if 'email_subject' in parameters:
                        subject = parameters['email_subject']

                    message = render_to_string('simple_data_export_report_message.txt', {
                        'report': report,
                        'url': settings.SITE_URL
                    })

                    tokens = settings.SITE_URL.split('/')
                    host = ''

                    site_human_name = 'Simple Data Exporter'

                    try:
                        site_human_name = settings.SIMPLE_DATA_EXPORTER_SITE_NAME
                    except AttributeError:
                        pass

                    while tokens and tokens[-1] == '':
                        tokens.pop()

                    if tokens:
                        host = tokens[-1]

                    send_mail(subject, \
                              message, \
                              site_human_name + ' <noreply@' + host + '>', \
                              [report.requester.email], \
                              fail_silently=False)

                for extra_destination in report.requester.pdk_report_destinations.all():
                    extra_destination.transmit(filename)

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

        if request is not None:
            request.process()
