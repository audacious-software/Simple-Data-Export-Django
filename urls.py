# pylint: disable=line-too-long, wrong-import-position

import sys

if sys.version_info[0] > 2:
    from django.urls import re_path as url # pylint: disable=no-name-in-module
else:
    from django.conf.urls import url

from .views import simple_data_export_download_report, simple_data_export_form

urlpatterns = [
    url(r'^report/(?P<report_id>\d+)/download$', simple_data_export_download_report, name='simple_data_export_download_report'),
    url(r'^$', simple_data_export_form, name='simple_data_export_form'),
]
