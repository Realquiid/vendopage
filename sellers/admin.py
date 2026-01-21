# sellers/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Seller

@admin.register(Seller)
class SellerAdmin(UserAdmin):
    list_display = [
        'business_name', 
        'username', 
        'subscription_type',
        'weekly_page_views',
        'weekly_whatsapp_clicks',
        'product_count',
        'is_featured',
        'created_at'
    ]
    list_filter = ['subscription_type', 'is_featured', 'category', 'created_at']
    search_fields = ['business_name', 'username', 'email', 'whatsapp_number']
    list_editable = ['subscription_type', 'is_featured']
    
    fieldsets = UserAdmin.fieldsets + (
        ('Business Info', {
            'fields': ('business_name', 'whatsapp_number', 'bio', 'profile_picture', 'slug', 'category')
        }),
        ('Subscription', {
            'fields': ('subscription_type', 'subscription_expires', 'is_featured')
        }),
        ('Analytics', {
            'fields': ('total_page_views', 'weekly_page_views', 'weekly_whatsapp_clicks', 'last_analytics_reset'),
            'classes': ('collapse',)
        }),
    )
    
    def product_count(self, obj):
        return obj.products.filter(is_archived=False).count()
    product_count.short_description = 'Active Products'
    
    actions = ['make_premium', 'make_free', 'feature_seller', 'unfeature_seller', 'reset_weekly_analytics']
    
    def make_premium(self, request, queryset):
        queryset.update(subscription_type='premium')
        self.message_user(request, f"{queryset.count()} sellers upgraded to Premium")
    make_premium.short_description = "Upgrade to Premium"
    
    def make_free(self, request, queryset):
        queryset.update(subscription_type='free')
        self.message_user(request, f"{queryset.count()} sellers downgraded to Free")
    make_free.short_description = "Downgrade to Free"
    
    def feature_seller(self, request, queryset):
        queryset.update(is_featured=True)
        self.message_user(request, f"{queryset.count()} sellers featured")
    feature_seller.short_description = "Feature on homepage"
    
    def unfeature_seller(self, request, queryset):
        queryset.update(is_featured=False)
        self.message_user(request, f"{queryset.count()} sellers unfeatured")
    unfeature_seller.short_description = "Remove from featured"
    
    def reset_weekly_analytics(self, request, queryset):
        from django.utils import timezone
        queryset.update(
            weekly_page_views=0,
            weekly_whatsapp_clicks=0,
            last_analytics_reset=timezone.now()
        )
        self.message_user(request, f"Reset analytics for {queryset.count()} sellers")
    reset_weekly_analytics.short_description = "Reset weekly analytics"

