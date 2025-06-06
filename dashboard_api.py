
from django.urls import reverse

def dashboard_pages():
    pages = []

    pages.append({
        'url': reverse('simple_data_export_form'),
        'icon': 'download',
        'title': 'Export Data',
    })

    return pages
