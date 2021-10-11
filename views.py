# pylint: disable=line-too-long, invalid-name

import io
import os

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils.encoding import smart_str

from .models import ReportJob

@staff_member_required
def simple_data_export_download_report(request, report_id): # pylint: disable=unused-argument
    job = get_object_or_404(ReportJob, pk=int(report_id))

    filename = settings.MEDIA_ROOT + '/' + job.report.name

    response = FileResponse(io.open(filename, 'rb', encoding='utf-8'), content_type='application/octet-stream') # pylint: disable=consider-using-with

    download_name = 'pdk-export_' + job.started.date().isoformat() + '_' + smart_str(job.pk) + '.zip'

    response['Content-Length'] = os.path.getsize(filename)
    response['Content-Disposition'] = 'attachment; filename=' + download_name

    return response
