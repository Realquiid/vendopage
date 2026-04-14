

# config/urls.py - replace the admin index override with this:
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.admin.views.decorators import staff_member_required
from django.views.generic import RedirectView
from sellers import api_views

admin.site.login_template = 'admin/custom_login.html'
admin.site.site_header = 'VendoPage Admin'
admin.site.site_title = 'VendoPage'
admin.site.index_title = 'Welcome to VendoPage Dashboard'

urlpatterns = [
    # This must come BEFORE path('admin/', ...) to intercept /admin/
    path('admin/', staff_member_required(
        RedirectView.as_view(pattern_name='admin_dashboard', permanent=False)
    )),
    path('admin/django/', admin.site.urls),  # Django admin still accessible at /admin/django/
    path('', include('sellers.urls')),
    path('api/vendor/<str:phone>/', api_views.get_vendor_by_phone, name='api_vendor'),
    path('api/products/create/', api_views.create_product_from_whatsapp, name='api_create_product'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)