from django.conf.urls import include, url
from django.contrib import admin
from django.urls import path

admin.autodiscover()

urlpatterns = [
    path('admin/', admin.site.urls),
    url(r'^accounts/', include('django.contrib.auth.urls')),
    url(r'^export/', include('simple_data_export.urls')),
]
