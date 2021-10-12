# pylint: disable=line-too-long

import importlib
import json
import os

import requests

from django.conf import settings
from django.core.checks import Error, register
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch.dispatcher import receiver
from django.urls import reverse
from django.utils import timezone

SIMPLE_DATA_EXPORT_FILE_FOLDER = 'simple_data_export_uploads'

class ReportJobManager(models.Manager): # pylint: disable=too-few-public-methods
    def create_jobs(self, requester, data_sources, data_types, start_time=None, end_time=None, custom_parameters=None): # pylint: disable=too-many-arguments, no-self-use
        batch_request = ReportJobBatchRequest(requester=requester, requested=timezone.now())

        job_parameters = {}

        job_parameters['data_sources'] = data_sources
        job_parameters['data_types'] = list(set(data_types))
        job_parameters['start_time'] = start_time
        job_parameters['end_time'] = end_time

        if custom_parameters is not None:
            job_parameters['custom_parameters'] = custom_parameters
        else:
            job_parameters['custom_parameters'] = {}

        batch_request.parameters = json.dumps(job_parameters, indent=2)

        batch_request.save()

class ReportJob(models.Model):
    objects = ReportJobManager()

    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    requested = models.DateTimeField(db_index=True)
    started = models.DateTimeField(db_index=True, null=True, blank=True)
    completed = models.DateTimeField(db_index=True, null=True, blank=True)

    job_index = models.IntegerField(default=1)
    job_count = models.IntegerField(default=1)

    parameters = models.TextField(max_length=(32 * 1024 * 1024 * 1024), default='{}')

    report = models.FileField(upload_to=SIMPLE_DATA_EXPORT_FILE_FOLDER, null=True, blank=True)

    def get_absolute_url(self):
        return reverse('simple_data_export_download', args=[self.pk])

@receiver(post_delete, sender=ReportJob)
def report_job_post_delete_handler(sender, **kwargs): # pylint: disable=unused-argument
    job = kwargs['instance']

    try:
        storage, path = job.report.storage, job.report.path
        storage.delete(path)
    except ValueError:
        pass

@register()
def check_reports_upload_protected(app_configs, **kwargs): # pylint: disable=unused-argument
    errors = []

    http_url = 'https://' + settings.ALLOWED_HOSTS[0] + settings.MEDIA_URL + SIMPLE_DATA_EXPORT_FILE_FOLDER

    response = requests.get(http_url)

    if response.status_code >= 200 and response.status_code < 400:
        error = Error('Raw reports folder is readable over HTTP', hint='Update webserver configuration to deny read access (' + http_url + ') via HTTP(S).', obj=None, id='simple_data_export.E001')

        errors.append(error)

    return errors

@register()
def check_reports_upload_available(app_configs, **kwargs): # pylint: disable=unused-argument
    errors = []

    folder_path = os.path.join(settings.MEDIA_ROOT, SIMPLE_DATA_EXPORT_FILE_FOLDER)

    if os.path.exists(folder_path) is False:
        error = Error('Raw reports folder is missing', hint='Verify that the folder for export files (' + folder_path + ') is present on the local filesystem.', obj=None, id='simple_data_export.E002')

        errors.append(error)

    return errors

@register()
def check_data_export_parameters(app_configs, **kwargs): # pylint: disable=unused-argument
    errors = []

    if hasattr(settings, 'SITE_URL') is False:
        error = Error('SITE_URL parameter not defined', hint='Update configuration to include SITE_URL.', obj=None, id='simple_data_export.E003')
        errors.append(error)

    if hasattr(settings, 'SIMPLE_DATA_EXPORTER_SITE_NAME') is False:
        error = Error('SIMPLE_DATA_EXPORTER_SITE_NAME parameter not defined', hint='Update configuration to include SIMPLE_DATA_EXPORTER_SITE_NAME.', obj=None, id='simple_data_export.E004')
        errors.append(error)

    if hasattr(settings, 'SIMPLE_DATA_EXPORTER_OBFUSCATE_IDENTIFIERS') is False:
        error = Error('SIMPLE_DATA_EXPORTER_OBFUSCATE_IDENTIFIERS parameter not defined', hint='Update configuration to include SIMPLE_DATA_EXPORTER_OBFUSCATE_IDENTIFIERS.', obj=None, id='simple_data_export.E005')
        errors.append(error)

    return errors

class ReportDestination(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='simple_data_export_destinations', on_delete=models.CASCADE)

    destination = models.CharField(max_length=4096)
    description = models.CharField(max_length=4096, null=True, blank=True)

    parameters = models.TextField(max_length=(32 * 1024 * 1024 * 1024))

    def fetch_parameters(self):
        return json.loads(self.parameters)

    def add_parameter(self, key, value):
        parameters = self.fetch_parameters()

        if value is None and (key in parameters):
            del parameters[key]
        else:
            parameters[key] = value

        self.parameters = json.dumps(parameters, indent=2)
        self.save()

    def transmit(self, report_file):
        for app in settings.INSTALLED_APPS:
            try:
                export_api = importlib.import_module(app + '.simple_data_export_api')

                export_api.send_to_destination(self, report_file)
            except ImportError:
                pass
            except AttributeError:
                pass

class ReportJobBatchRequest(models.Model):
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    requested = models.DateTimeField(db_index=True)
    started = models.DateTimeField(db_index=True, null=True, blank=True)
    completed = models.DateTimeField(db_index=True, null=True, blank=True)

    parameters = models.TextField(max_length=(32 * 1024 * 1024 * 1024))

    def process(self): # pylint: disable=too-many-locals, too-many-branches, too-many-statements
        self.started = timezone.now()
        self.save()

        params = json.loads(self.parameters)

        sources = []

        if ('data_sources' in params) is False:
            for app in settings.INSTALLED_APPS:
                try:
                    export_api = importlib.import_module(app + '.simple_data_export_api')

                    export_sources = export_api.export_data_sources(params)

                    for new_source in export_sources:
                        if (new_source in sources) is False:
                            sources.append(new_source)
                except ImportError:
                    pass
                except AttributeError:
                    pass
        else:
            sources.extend(params['data_sources'])

        sources.sort()

        pending_jobs = []

        requested = timezone.now()

        sources_per_job = 50

        try:
            sources_per_job = settings.SIMPLE_DATA_EXPORT_DATA_SOURCES_PER_REPORT_JOB
        except AttributeError:
            pass

        source_index = 0

        while source_index < len(sources):
            pending_sources = sources[source_index:(source_index + sources_per_job)]

            job = ReportJob(requester=self.requester, requested=requested)

            job_params = {}

            job_params['data_sources'] = pending_sources
            job_params['data_types'] = params['data_types']
            job_params['start_time'] = params['start_time']
            job_params['end_time'] = params['end_time']
            job_params['custom_parameters'] = params['custom_parameters']

            job.parameters = json.dumps(job_params, indent=2)
            job.save()

            pending_jobs.append(job)

            source_index += sources_per_job

        index = 1

        for job in pending_jobs:
            job.job_index = index
            job.job_count = len(pending_jobs)
            job.save()

            index += 1

        self.completed = timezone.now()
        self.save()
