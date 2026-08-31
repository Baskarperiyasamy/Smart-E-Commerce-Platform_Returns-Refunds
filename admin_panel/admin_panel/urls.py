from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "SmartCart Admin"
admin.site.site_title = "SmartCart Admin"
admin.site.index_title = "User, Product & Order Management"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("storefront.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
