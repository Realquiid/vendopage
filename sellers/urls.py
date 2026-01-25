# sellers/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Public pages
    path('', views.home, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/upload/', views.upload_product, name='upload_product'),
    path('dashboard/subscription/', views.subscription, name='subscription'),
    path('payment/upgrade/', views.upgrade_to_premium, name='upgrade_to_premium'),
    path('payment/verify/', views.verify_payment, name='verify_payment'),
    path('webhook/flutterwave/', views.flutterwave_webhook, name='flutterwave_webhook'),

   
    path('dashboard/settings/', views.dashboard_settings, name='settings'),

    path('dashboard/settings/profile-picture/', views.update_profile_picture, name='update_profile_picture'),
    path('dashboard/settings/business-info/', views.update_business_info, name='update_business_info'),
    path('dashboard/settings/account/', views.update_account, name='update_account'),
    path('dashboard/settings/password/', views.change_password, name='change_password'),
    
    # API endpoints - Product actions
    path('api/product/<int:product_id>/archive/', views.archive_product, name='archive_product'),
    path('api/product/<int:product_id>/reactivate/', views.reactivate_product, name='reactivate_product'),
    path('api/product/<int:product_id>/delete/', views.delete_product, name='delete_product'),
    
    # NEW: Sold out feature
    path('api/product/<int:product_id>/mark-sold-out/', views.mark_sold_out, name='mark_sold_out'),
    path('api/product/<int:product_id>/mark-available/', views.mark_available, name='mark_available'),
    
    # NEW: Analytics tracking
    path('api/product/<int:product_id>/track-whatsapp/', views.track_whatsapp_click, name='track_whatsapp_click'),
 


    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/sellers/', views.admin_sellers, name='admin_sellers'),
    path('admin-dashboard/sellers/<int:seller_id>/', views.admin_seller_detail, name='admin_seller_detail'),
    path('admin-dashboard/products/', views.admin_products, name='admin_products'),
    path('admin-dashboard/analytics/', views.admin_analytics, name='admin_analytics'),


    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('verify-code/', views.verify_reset_code, name='verify_reset_code'),
    path('reset-password/<str:token>/', views.reset_password, name='reset_password'),
    

       
    # Seller page (must be last - catch-all)
    path('<slug:slug>/', views.seller_page, name='seller_page'),
]

