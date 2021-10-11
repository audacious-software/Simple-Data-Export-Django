# pylint: disable=line-too-long

from django.conf.urls import url

from .views import simple_data_export_download_report

urlpatterns = [
    url(r'^report/(?P<report_id>\d+)/download$', simple_data_export_download_report, name='simple_data_export_download_report'),
]
