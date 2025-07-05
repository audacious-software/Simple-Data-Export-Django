# pylint: disable=line-too-long, invalid-name

import importlib
import io
import os

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse
from django.shortcuts import get_object_or_404, render
from django.utils.encoding import smart_str
from django.utils.text import slugify

from .models import ReportJob
from .utils import fetch_export_identifier

@staff_member_required
def simple_data_export_download_report(request, report_id): # pylint: disable=unused-argument
    job = get_object_or_404(ReportJob, pk=int(report_id))

    filename = '%s/%s' % (settings.MEDIA_ROOT, job.report.name)

    response = FileResponse(io.open(filename, 'rb'), content_type='application/octet-stream') # pylint: disable=consider-using-with

    download_name = 'data-export_' + job.started.date().isoformat() + '_' + smart_str(job.pk) + '.zip'

    response['Content-Length'] = os.path.getsize(filename)
    response['Content-Disposition'] = 'attachment; filename=' + download_name

    return response

@staff_member_required
def simple_data_export_form(request): # pylint: disable=too-many-branches
    context = {}

    new_sources = []

    for app in settings.INSTALLED_APPS:
        try:
            export_api = importlib.import_module(app + '.simple_data_export_api')

            data_sources = export_api.export_data_sources()

            for data_source in data_sources:
                if isinstance(data_source, str):
                    data_source = (data_source, data_source, 'Uncategorized Data Source')

                if (data_source in new_sources) is False:
                    new_sources.append(data_source)
        except ImportError:
            pass
        except AttributeError:
            pass

    new_sources.sort(key=lambda source: '%s--%s' % (source[2], source[1]))

    data_sources = []

    last_category = None

    for source in new_sources:
        if source[2] != last_category:
           data_sources.append((source[2],))

           last_category = source[2]

        data_sources.append(source)

    context['data_sources'] = data_sources

    context['data_types'] = []

    for app in settings.INSTALLED_APPS:
        try:
            export_api = importlib.import_module(app + '.simple_data_export_api')

            data_types = export_api.export_data_types()

            for data_type in data_types:
                if (data_type in context['data_types']) is False:
                    context['data_types'].append(data_type)
        except ImportError:
            pass
        except AttributeError:
            pass

    if request.method == 'POST':
        selected_sources = []
        selected_data_types = []

        for source in context['data_sources']:
            if ('source_' + source[0]) in request.POST: # pylint: disable=superfluous-parens
                selected_sources.append(source[0])

        for data_type in context['data_types']:
            if ('data_type_' + data_type[0]) in request.POST: # pylint: disable=superfluous-parens
                selected_data_types.append(data_type[0])

        start_time = request.POST.get('start_time', '')
        end_time = request.POST.get('end_time', '')

        if start_time.strip() == '':
            start_time = None

        if end_time.strip() == '':
            end_time = None

        ReportJob.objects.create_jobs(request.user, selected_sources, selected_data_types, start_time=start_time, end_time=end_time)

        context['message'] = 'Request submitted successfully.'

    return render(request, 'simple_data_export_form.html', context=context)
