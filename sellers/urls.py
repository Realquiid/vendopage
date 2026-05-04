# sellers/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ── Public pages ─────────────────────────────────────────
    path('', views.home, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # ── Dashboard ────────────────────────────────────────────
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/upload/', views.upload_product, name='upload_product'),
    path('dashboard/subscription/', views.subscription, name='subscription'),
    path('payment/upgrade/', views.upgrade_to_premium, name='upgrade_to_premium'),
    path('payment/verify/', views.verify_payment, name='verify_payment'),
    path('webhook/flutterwave/', views.flutterwave_webhook, name='flutterwave_webhook'),

    # ── Settings ─────────────────────────────────────────────
    path('dashboard/settings/', views.dashboard_settings, name='settings'),
    path('dashboard/settings/profile-picture/', views.update_profile_picture, name='update_profile_picture'),
    path('dashboard/settings/business-info/', views.update_business_info, name='update_business_info'),
    path('dashboard/settings/account/', views.update_account, name='update_account'),
    path('dashboard/settings/password/', views.change_password, name='change_password'),
    path('dashboard/settings/update-watermark/', views.update_watermark, name='update_watermark'),
    path('dashboard/settings/payout/', views.update_payout_account, name='update_payout_account'),
    path('dashboard/settings/store-mode/', views.toggle_store_mode, name='toggle_store_mode'),

    # ── Product API ──────────────────────────────────────────
    path('api/product/<int:product_id>/archive/', views.archive_product, name='archive_product'),
    path('api/product/<int:product_id>/reactivate/', views.reactivate_product, name='reactivate_product'),
    path('api/product/<int:product_id>/delete/', views.delete_product, name='delete_product'),
    path('api/products/batch/', views.upload_products_batch, name='upload_products_batch'),
    path('api/product/<int:product_id>/mark-sold-out/', views.mark_sold_out, name='mark_sold_out'),
    path('api/product/<int:product_id>/mark-available/', views.mark_available, name='mark_available'),
    path('api/product/<int:product_id>/track-whatsapp/', views.track_whatsapp_click, name='track_whatsapp_click'),

    # ── ESCROW — Buyer flow ──────────────────────────────────
    path('order/<slug:slug>/cart/', views.cart_view, name='cart'),
    path('order/<slug:slug>/checkout/', views.checkout_view, name='checkout'),
    path('order/<slug:slug>/pay/', views.initiate_payment, name='initiate_payment'),
    path('order/confirm/', views.order_confirmation, name='order_confirmation'),
    path('order/<str:order_ref>/', views.order_detail, name='order_detail'),
    path('order/<str:order_ref>/confirm-receipt/', views.confirm_receipt, name='confirm_receipt'),
    path('order/<str:order_ref>/dispute/', views.raise_dispute, name='raise_dispute'),
    path('order/<str:order_ref>/review/', views.leave_review, name='leave_review'),

    # ── ESCROW — Vendor flow ─────────────────────────────────
    path('dashboard/orders/', views.vendor_orders, name='vendor_orders'),
    path('dashboard/orders/<str:order_ref>/', views.vendor_order_detail, name='vendor_order_detail'),
    path('dashboard/orders/<str:order_ref>/ship/', views.mark_shipped, name='mark_shipped'),

    # ── ESCROW — Webhooks ────────────────────────────────────
    path('webhook/flutterwave/order/', views.flutterwave_order_webhook, name='flutterwave_order_webhook'),

    # ── Admin — core ─────────────────────────────────────────
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/sellers/', views.admin_sellers, name='admin_sellers'),
    path('admin-dashboard/sellers/<int:seller_id>/', views.admin_seller_detail, name='admin_seller_detail'),
    path('admin-dashboard/products/', views.admin_products, name='admin_products'),
    path('admin-dashboard/analytics/', views.admin_analytics, name='admin_analytics'),

    # ── Admin — disputes ─────────────────────────────────────
    path('admin-dashboard/disputes/', views.admin_disputes, name='admin_disputes'),
    path('admin-dashboard/disputes/<int:dispute_id>/resolve/', views.resolve_dispute, name='resolve_dispute'),

    # ── Admin — orders & payouts ─────────────────────────────
    path('admin-dashboard/orders/', views.admin_orders, name='admin_orders'),
    path('admin-dashboard/orders/<int:order_id>/trigger-payout/', views.admin_trigger_payout, name='admin_trigger_payout'),
    path('admin-dashboard/orders/<int:order_id>/mark-delivered/', views.admin_mark_delivered, name='admin_mark_delivered'),
    path('admin-dashboard/orders/<int:order_id>/mark-refunded/', views.admin_mark_refunded, name='admin_mark_refunded'),
    path('admin-dashboard/payouts/', views.admin_payouts, name='admin_payouts'),
    path('admin-dashboard/settings/', views.admin_settings, name='admin_settings'),

    # ── Admin — products actions ──────────────────────────────
    path('admin-dashboard/products/<int:product_id>/action/', views.admin_product_action, name='admin_product_action'),

    # ── Admin — reviews ───────────────────────────────────────
    path('admin-dashboard/reviews/', views.admin_reviews, name='admin_reviews'),
    path('admin-dashboard/reviews/<int:review_id>/delete/', views.admin_delete_review, name='admin_delete_review'),
    path('settings/currency/', views.update_currency, name='update_currency'),


    # ── Admin — bank accounts ─────────────────────────────────
    path('admin-dashboard/bank-accounts/', views.admin_bank_accounts, name='admin_bank_accounts'),
    path('admin-dashboard/bank-accounts/<int:account_id>/verify/', views.admin_verify_bank_account, name='admin_verify_bank_account'),

    # ── Auth / misc ──────────────────────────────────────────
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('verify-code/', views.verify_reset_code, name='verify_reset_code'),
    path('reset-password/<str:token>/', views.reset_password, name='reset_password'),
    path('about/', views.about, name='about'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('contact/', views.contact, name='contact'),
    path('api/banks/', views.get_banks, name='get_banks'),
    path('api/verify-bank-account/', views.verify_bank_account, name='verify_bank_account'),

    # ── Seller page — MUST stay last ─────────────────────────
    path('<slug:slug>/', views.seller_page, name='seller_page'),
]