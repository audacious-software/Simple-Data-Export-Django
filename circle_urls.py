import django

from django.conf.urls import include, url

urlpatterns = [
    url(r'^admin/', django.contrib.admin.site.urls),
    url(r'^export/', include('simple_data_export.urls')),
]
