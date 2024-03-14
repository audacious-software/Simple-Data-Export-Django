# pylint: disable=no-name-in-module, wrong-import-position

import sys

if sys.version_info[0] > 2:
    from django.urls import re_path as url, include # pylint: disable=no-name-in-module
else:
    from django.conf.urls import url, include

import django

urlpatterns = [
    url(r'^admin/', django.contrib.admin.site.urls),
    url(r'^export/', include('simple_data_export.urls')),
]
