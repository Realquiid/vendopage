# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect
from sellers import api_views

admin.site.login_template = 'admin/custom_login.html'
admin.site.site_header = 'VendoPage Admin'
admin.site.site_title = 'VendoPage'
admin.site.index_title = 'Welcome to VendoPage Dashboard'

@staff_member_required
def custom_admin_index(request):
    return redirect('admin_dashboard')  # your named URL in sellers/urls.py

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('sellers.urls')),
    path('api/vendor/<str:phone>/', api_views.get_vendor_by_phone, name='api_vendor'),
    path('api/products/create/', api_views.create_product_from_whatsapp, name='api_create_product'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Override the admin index AFTER registering urls
admin.site.index = custom_admin_index