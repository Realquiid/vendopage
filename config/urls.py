# config/urls.py (main project URLs)
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from sellers import api_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('sellers.urls')),
    path('api/vendor/<str:phone>/', api_views.get_vendor_by_phone, name='api_vendor'),
    path('api/products/create/', api_views.create_product_from_whatsapp, name='api_create_product'), 
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

