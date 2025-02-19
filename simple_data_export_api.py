# pylint: disable=line-too-long

from __future__ import print_function

import io
import json
import logging
import os
import shutil
import time
import traceback

import boto3
import dropbox
import paramiko
import pytz

from botocore.config import Config

from django.conf import settings

logger = logging.getLogger(__name__) # pylint: disable=invalid-name

def send_to_destination(destination, report_path, report): # pylint: disable=too-many-branches, too-many-statements, too-many-locals
    file_sent = False

    here_tz = pytz.timezone(settings.TIME_ZONE)

    sleep_durations = [
        0,
        60,
        120,
        300,
    ]

    try:
        sleep_durations = settings.SIMPLE_DATA_EXPORT_UPLOAD_SLEEP_DURATIONS
    except AttributeError:
        pass # Use defaults above.

    report_parameters = json.loads(report.parameters).get('custom_parameters', {})

    parameters = destination.fetch_parameters()

    parameters.update(report_parameters)

    if destination.destination == 'dropbox':
        try:
            if 'access_token' in parameters:
                client = dropbox.Dropbox(parameters['access_token'])

                path = '/'

                if 'path' in report_parameters:
                    path = report_parameters['path']

                    path = path + '/'

                if parameters.get('prepend_host', False):
                    path = path + settings.ALLOWED_HOSTS[0] + '-'

                if parameters.get('prepend_date', False):
                    path = path + report.requested.astimezone(here_tz).date().isoformat() + '-'

                if parameters.get('prepend_source_range', False):
                    report_parameters = json.loads(report.parameters)

                    data_sources = report_parameters.get('data_sources', [])

                    if len(data_sources) == 1:
                        path = path + data_sources[0] + '-'
                    elif len(data_sources) >= 2:
                        path = path + data_sources[0] + '.' + data_sources[-1] + '-'

                path = path + os.path.basename(os.path.normpath(report_path))

                for duration in sleep_durations:
                    time.sleep(duration)

                    try:
                        with io.open(report_path, 'rb') as report_file:
                            client.files_upload(report_file.read(), path)

                            file_sent = True
                    except: # pylint: disable=bare-except
                        if duration == sleep_durations[-1]:
                            logger.error('Unable to upload - error encountered. (Latest sleep = %s seconds.)', duration)
                            logger.error(traceback.format_exc())

        except BaseException:
            traceback.print_exc()
    elif destination.destination == 'sftp': # pylint: disable=too-many-nested-blocks
        try:
            if ('username' in parameters) and ('host' in parameters) and ('key' in parameters):
                path = ''

                if 'path' in parameters:
                    path = parameters['path']

                    path = path + '/'

                if parameters.get('prepend_host', False):
                    path = path + settings.ALLOWED_HOSTS[0] + '-'

                if parameters.get('prepend_date', False):
                    path = path + report.requested.astimezone(here_tz).date().isoformat() + '-'

                if parameters.get('prepend_source_range', False):
                    report_parameters = json.loads(report.parameters)

                    data_sources = report_parameters.get('data_sources', [])

                    if len(data_sources) == 1:
                        path = path + data_sources[0] + '-'
                    elif len(data_sources) >= 2:
                        path = path + data_sources[0] + '.' + data_sources[-1] + '-'

                path = path + os.path.basename(os.path.normpath(report_path))

                for duration in sleep_durations:
                    time.sleep(duration)

                    try:
                        key = paramiko.RSAKey.from_private_key(io.StringIO(parameters['key']))

                        ssh_client = paramiko.SSHClient()

                        trust_host_keys = True

                        try:
                            trust_host_keys = settings.SIMPLE_DATA_EXPORT_TRUST_HOST_KEYS
                        except AttributeError:
                            pass

                        if trust_host_keys:
                            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy()) # nosec

                        ssh_client.connect(hostname=parameters['host'], username=parameters['username'], pkey=key)

                        ftp_client = ssh_client.open_sftp()
                        ftp_client.put(report_path, path)
                        ftp_client.close()

                        file_sent = True

                        break
                    except: # pylint: disable=bare-except
                        if duration == sleep_durations[-1]:
                            logger.error('Unable to upload - error encountered. (Latest sleep = %s seconds.)', duration)
                            logger.error(traceback.format_exc())

        except BaseException:
            traceback.print_exc()
    elif destination.destination == 's3':
        try:
            if ('region' in parameters) and ('access_key_id' in parameters) and ('secret_access_key' in parameters) and ('bucket' in parameters):
                aws_config = Config(
                    region_name=parameters['region'],
                    retries={'max_attempts': 10, 'mode': 'standard'}
                )

                os.environ['AWS_ACCESS_KEY_ID'] = parameters['access_key_id']
                os.environ['AWS_SECRET_ACCESS_KEY'] = parameters['secret_access_key']

                client = boto3.client('s3', config=aws_config)

                s3_bucket = parameters['bucket']

                path = ''

                if 'path' in parameters:
                    path = parameters['path']

                    if path[-1] != '/':
                        path = path + '/'

                if parameters.get('prepend_host', False):
                    path = path + settings.ALLOWED_HOSTS[0] + '-'

                if parameters.get('prepend_date', False):
                    path = path + report.requested.astimezone(here_tz).date().isoformat() + '-'

                if parameters.get('prepend_source_range', False):
                    report_parameters = json.loads(report.parameters)

                    data_sources = report_parameters.get('data_sources', [])

                    if len(data_sources) == 1:
                        path = path + data_sources[0] + '-'
                    elif len(data_sources) >= 2:
                        path = path + data_sources[0] + '.' + data_sources[-1] + '-'

                path = path + os.path.basename(os.path.normpath(report_path))

                with io.open(report_path, 'rb') as report_file:
                    client.put_object(Body=report_file.read(), Bucket=s3_bucket, Key=path)

                    file_sent = True
        except BaseException:
            traceback.print_exc()

    elif destination.destination == 'local':
        try:
            if 'path' in parameters:
                path = parameters['path']

                if path[-1] != '/':
                    path = path + '/'

            if parameters.get('prepend_host', False):
                path = path + settings.ALLOWED_HOSTS[0] + '-'

            if parameters.get('prepend_date', False):
                path = path + report.requested.astimezone(here_tz).date().isoformat() + '-'

            if parameters.get('prepend_source_range', False):
                report_parameters = json.loads(report.parameters)

                data_sources = report_parameters.get('data_sources', [])

                if len(data_sources) == 1:
                    path = path + data_sources[0] + '-'
                elif len(data_sources) >= 2:
                    path = path + data_sources[0] + '.' + data_sources[-1] + '-'

            path = path + os.path.basename(os.path.normpath(report_path))

            shutil.copyfile(report_path, path)

            file_sent = True

        except BaseException:
            traceback.print_exc()

    if file_sent is False:
        logger.error('Unable to transmit report to destination "%s".', destination.destination)
