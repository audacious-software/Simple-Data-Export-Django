# pylint: disable=line-too-long

import io
import os
import shutil
import time
import traceback

import dropbox
import paramiko

from django.conf import settings
from django.utils import timezone

def send_to_destination(destination, report_path): # pylint: disable=too-many-branches, too-many-statements
    file_sent = False

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

    if destination.destination == 'dropbox':
        try:
            parameters = destination.fetch_parameters()

            if 'access_token' in parameters:
                client = dropbox.Dropbox(parameters['access_token'])

                path = '/'

                if 'path' in parameters:
                    path = parameters['path']

                path = path + '/'

                if ('prepend_host' in parameters) and parameters['prepend_host']:
                    path = path + settings.ALLOWED_HOSTS[0] + '-'

                if ('prepend_date' in parameters) and parameters['prepend_date']:
                    path = path + timezone.now().date().isoformat() + '-'

                path = path + os.path.basename(os.path.normpath(report_path))

                for duration in sleep_durations:
                    time.sleep(duration)

                    try:
                        with io.open(report_path, 'rb') as report_file:
                            client.files_upload(report_file.read(), path)

                            file_sent = True
                    except: # pylint: disable=bare-except
                        if duration == sleep_durations[-1]:
                            print('Unable to upload - error encountered. (Latest sleep = ' + str(duration) + ' seconds.)')

                            traceback.print_exc()

        except BaseException:
            traceback.print_exc()
    elif destination.destination == 'sftp': # pylint: disable=too-many-nested-blocks
        try:
            parameters = destination.fetch_parameters()

            if ('username' in parameters) and ('host' in parameters) and ('key' in parameters):
                path = ''

                if 'path' in parameters:
                    path = parameters['path']

                if ('prepend_date' in parameters) and parameters['prepend_date']:
                    path = path + timezone.now().date().isoformat() + '-'

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
                            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy()) # lgtm[py/paramiko-missing-host-key-validation]

                        ssh_client.connect(hostname=parameters['host'], username=parameters['username'], pkey=key)

                        ftp_client = ssh_client.open_sftp()
                        ftp_client.put(report_path, path)
                        ftp_client.close()

                        file_sent = True
                    except: # pylint: disable=bare-except
                        if duration == sleep_durations[-1]:
                            print('Unable to upload - error encountered. (Latest sleep = ' + str(duration) + ' seconds.)')

                            traceback.print_exc()

        except BaseException:
            traceback.print_exc()

    elif destination.destination == 'local':
        try:
            parameters = destination.fetch_parameters()

            if 'path' in parameters:
                path = parameters['path']

            if ('prepend_date' in parameters) and parameters['prepend_date']:
                path = path + timezone.now().date().isoformat() + '-'

            path = path + os.path.basename(os.path.normpath(report_path))

            shutil.copyfile(report_path, path)

            file_sent = True

        except BaseException:
            traceback.print_exc()

    if file_sent is False:
        print('Unable to transmit report to destination "' + destination.destination + '".')
