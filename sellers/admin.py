# sellers/admin.py
# ─────────────────────────────────────────────────────────────────────────────
# Registers: Seller, PlatformSettings, VendorBankAccount, Order, Dispute, Review
#
# NOTE: Product and ProductImage are intentionally NOT registered here.
#       They are owned exclusively by products/admin.py.
#       Registering them in both files causes a duplicate registration crash.
# ─────────────────────────────────────────────────────────────────────────────

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.utils import timezone
from django.urls import reverse
from django.db.models import Sum, Count
from datetime import timedelta
from decimal import Decimal

from .models import (
    Seller,
    PlatformSettings,
    VendorBankAccount,
    Order,
    OrderItem,
    Dispute,
    Review,
)


# ─────────────────────────────────────────────────────────────
# INLINE: VendorBankAccount inside Seller
# ─────────────────────────────────────────────────────────────
class VendorBankAccountInline(admin.StackedInline):
    model = VendorBankAccount
    extra = 0
    readonly_fields = ['is_verified', 'created_at', 'updated_at']
    fields = ['account_name', 'account_number', 'bank_name', 'bank_code', 'is_verified']
    can_delete = True


# ─────────────────────────────────────────────────────────────
# INLINE: OrderItem inside Order
# ─────────────────────────────────────────────────────────────
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['product_id', 'product_name', 'price', 'quantity', 'line_total_display', 'product_thumb']
    fields = ['product_thumb', 'product_name', 'price', 'quantity', 'line_total_display']
    can_delete = False

    def line_total_display(self, obj):
        return f"{obj.price * obj.quantity:,.2f}"
    line_total_display.short_description = 'Line Total'

    def product_thumb(self, obj):
        if obj.product_image_url:
            return format_html(
                '<img src="{}" style="height:50px;width:50px;object-fit:cover;border-radius:4px;" />',
                obj.product_image_url
            )
        return '—'
    product_thumb.short_description = 'Image'


# ─────────────────────────────────────────────────────────────
# INLINE: Dispute inside Order
# ─────────────────────────────────────────────────────────────
class DisputeInline(admin.StackedInline):
    model = Dispute
    extra = 0
    readonly_fields = ['raised_by', 'reason', 'buyer_message', 'buyer_evidence', 'created_at']
    fields = [
        'raised_by', 'reason', 'status',
        'buyer_message', 'buyer_evidence',
        'vendor_reply', 'vendor_evidence',
        'admin_note', 'resolved_at',
    ]
    can_delete = False


# ─────────────────────────────────────────────────────────────
# SELLER ADMIN
# ─────────────────────────────────────────────────────────────
@admin.register(Seller)
class SellerAdmin(UserAdmin):
    list_display = [
        'business_name',
        'username',
        'email',
        'subscription_badge',
        'store_mode_badge',
        'weekly_page_views',
        'weekly_whatsapp_clicks',
        'product_count',
        'total_orders',
        'total_revenue',
        'is_featured',
        'is_active',
        'created_at',
    ]
    list_filter = [
        'subscription_type',
        'is_featured',
        'store_mode',
        'category',
        'is_active',
        'created_at',
    ]
    search_fields = ['business_name', 'username', 'email', 'whatsapp_number', 'slug']
    list_editable = ['is_featured']
    readonly_fields = [
        'slug', 'created_at', 'last_analytics_reset',
        'total_page_views', 'weekly_page_views', 'weekly_whatsapp_clicks',
        'store_link', 'store_mode_enabled_at',
    ]
    inlines = [VendorBankAccountInline]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    fieldsets = UserAdmin.fieldsets + (
        ('Business Info', {
            'fields': (
                'business_name', 'whatsapp_number', 'bio',
                'profile_picture', 'slug', 'store_link', 'category',
                'country_code', 'currency_code', 'currency_symbol',
            )
        }),
        ('Subscription', {
            'fields': ('subscription_type', 'subscription_expires', 'is_featured'),
        }),
        ('Store Mode', {
            'fields': ('store_mode', 'store_mode_enabled_at', 'watermark_enabled'),
        }),
        ('Analytics', {
            'fields': (
                'total_page_views', 'weekly_page_views',
                'weekly_whatsapp_clicks', 'last_analytics_reset',
            ),
            'classes': ('collapse',),
        }),
    )

    # ── Computed columns ──────────────────────────────────────

    def subscription_badge(self, obj):
        if obj.subscription_type == 'premium':
            return format_html(
                '<span style="background:#fef3c7;color:#92400e;padding:2px 10px;'
                'border-radius:100px;font-size:11px;font-weight:700;">⭐ Premium</span>'
            )
        return format_html(
            '<span style="background:#f3f4f6;color:#6b7280;padding:2px 10px;'
            'border-radius:100px;font-size:11px;">Free</span>'
        )
    subscription_badge.short_description = 'Plan'

    def store_mode_badge(self, obj):
        if obj.store_mode:
            return format_html(
                '<span style="background:#d1fae5;color:#065f46;padding:2px 10px;'
                'border-radius:100px;font-size:11px;font-weight:700;">● On</span>'
            )
        return format_html(
            '<span style="background:#f3f4f6;color:#9ca3af;padding:2px 10px;'
            'border-radius:100px;font-size:11px;">Off</span>'
        )
    store_mode_badge.short_description = 'Store Mode'

    def store_link(self, obj):
        if obj.slug:
            url = f'https://vendopage.com/{obj.slug}'
            return format_html('<a href="{}" target="_blank">{}</a>', url, url)
        return '—'
    store_link.short_description = 'Public Store URL'

    def product_count(self, obj):
        return obj.products.filter(is_archived=False).count()
    product_count.short_description = 'Products'

    def total_orders(self, obj):
        count = Order.objects.filter(
            seller=obj,
            status__in=['paid', 'shipped', 'delivered', 'completed', 'disputed']
        ).count()
        if count:
            url = reverse('admin:sellers_order_changelist') + f'?seller__id__exact={obj.id}'
            return format_html('<a href="{}">{}</a>', url, count)
        return 0
    total_orders.short_description = 'Orders'

    def total_revenue(self, obj):
        total = Order.objects.filter(
            seller=obj,
            status__in=['delivered', 'completed'],
            payout_triggered=True,
        ).aggregate(t=Sum('vendor_payout'))['t'] or Decimal('0')
        if total:
            sym = obj.currency_symbol or '₦'
            return format_html(
                '<strong style="color:#059669;">{}{:,.0f}</strong>',
                sym, total
            )
        return '—'
    total_revenue.short_description = 'Revenue Paid Out'

    # ── Bulk actions ──────────────────────────────────────────

    actions = [
        'make_premium', 'make_free',
        'feature_seller', 'unfeature_seller',
        'enable_store_mode', 'disable_store_mode',
        'reset_weekly_analytics',
        'deactivate_sellers', 'activate_sellers',
    ]

    def make_premium(self, request, queryset):
        updated = queryset.update(
            subscription_type='premium',
            subscription_expires=timezone.now() + timedelta(days=30)
        )
        self.message_user(request, f"✅ {updated} seller(s) upgraded to Premium (30 days)")
    make_premium.short_description = "Upgrade to Premium (30 days)"

    def make_free(self, request, queryset):
        updated = queryset.update(subscription_type='free', subscription_expires=None)
        self.message_user(request, f"⬇️ {updated} seller(s) downgraded to Free")
    make_free.short_description = "Downgrade to Free"

    def feature_seller(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, f"⭐ {updated} seller(s) featured on homepage")
    feature_seller.short_description = "Feature on homepage"

    def unfeature_seller(self, request, queryset):
        updated = queryset.update(is_featured=False)
        self.message_user(request, f"🗑️ {updated} seller(s) removed from featured")
    unfeature_seller.short_description = "Remove from featured"

    def enable_store_mode(self, request, queryset):
        updated = queryset.update(store_mode=True, store_mode_enabled_at=timezone.now())
        self.message_user(request, f"🔓 Store Mode enabled for {updated} seller(s)")
    enable_store_mode.short_description = "Enable Store Mode"

    def disable_store_mode(self, request, queryset):
        updated = queryset.update(store_mode=False)
        self.message_user(request, f"🔒 Store Mode disabled for {updated} seller(s)")
    disable_store_mode.short_description = "Disable Store Mode"

    def reset_weekly_analytics(self, request, queryset):
        updated = queryset.update(
            weekly_page_views=0,
            weekly_whatsapp_clicks=0,
            last_analytics_reset=timezone.now()
        )
        self.message_user(request, f"📊 Weekly analytics reset for {updated} seller(s)")
    reset_weekly_analytics.short_description = "Reset weekly analytics"

    def deactivate_sellers(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"🚫 {updated} seller(s) deactivated")
    deactivate_sellers.short_description = "Deactivate sellers (ban)"

    def activate_sellers(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"✅ {updated} seller(s) activated")
    activate_sellers.short_description = "Activate sellers"


# ─────────────────────────────────────────────────────────────
# ORDER ADMIN
# ─────────────────────────────────────────────────────────────
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'order_ref_short', 'seller_link', 'buyer_name',
        'subtotal_display', 'fee_display', 'payout_display',
        'status_badge', 'payment_type', 'payout_triggered',
        'created_at',
    ]
    list_filter = [
        'status', 'payment_type', 'payout_triggered',
        'currency', 'created_at',
    ]
    search_fields = [
        'order_ref', 'buyer_name', 'buyer_email', 'buyer_phone',
        'seller__business_name', 'flutterwave_tx_ref', 'flutterwave_tx_id',
    ]
    readonly_fields = [
        'order_ref', 'seller', 'buyer_name', 'buyer_email', 'buyer_phone',
        'delivery_address', 'delivery_city', 'subtotal', 'platform_fee',
        'vendor_payout', 'currency', 'flutterwave_tx_id', 'flutterwave_tx_ref',
        'payment_verified', 'paid_at', 'shipped_at', 'delivered_at',
        'auto_release_at', 'payout_at', 'flutterwave_transfer_id', 'created_at',
    ]
    inlines = [OrderItemInline, DisputeInline]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    list_select_related = ['seller']

    fieldsets = [
        ('Order Reference', {
            'fields': ('order_ref', 'seller', 'payment_type', 'currency'),
        }),
        ('Buyer', {
            'fields': ('buyer_name', 'buyer_email', 'buyer_phone', 'delivery_address', 'delivery_city'),
        }),
        ('Financials', {
            'fields': ('subtotal', 'platform_fee', 'vendor_payout'),
        }),
        ('Status & Shipping', {
            'fields': (
                'status', 'tracking_info', 'courier_name',
                'paid_at', 'shipped_at', 'delivered_at', 'auto_release_at',
            ),
        }),
        ('Payment', {
            'fields': ('flutterwave_tx_ref', 'flutterwave_tx_id', 'payment_verified'),
            'classes': ('collapse',),
        }),
        ('Payout', {
            'fields': ('payout_triggered', 'payout_at', 'flutterwave_transfer_id'),
            'classes': ('collapse',),
        }),
    ]

    actions = ['trigger_payout_action', 'mark_delivered_action', 'mark_refunded_action']

    def order_ref_short(self, obj):
        ref = str(obj.order_ref)[:8].upper()
        url = reverse('admin:sellers_order_change', args=[obj.id])
        return format_html(
            '<a href="{}" style="font-family:monospace;font-weight:700;">#{}</a>', url, ref
        )
    order_ref_short.short_description = 'Order Ref'

    def seller_link(self, obj):
        url = reverse('admin:sellers_seller_change', args=[obj.seller.id])
        return format_html('<a href="{}">{}</a>', url, obj.seller.business_name)
    seller_link.short_description = 'Seller'

    def subtotal_display(self, obj):
        return f"{obj.currency} {obj.subtotal:,.0f}"
    subtotal_display.short_description = 'Order Total'

    def fee_display(self, obj):
        return format_html(
            '<span style="color:#b91c1c;">{} {:,.0f}</span>',
            obj.currency, obj.platform_fee
        )
    fee_display.short_description = 'Platform Fee'

    def payout_display(self, obj):
        return format_html(
            '<strong style="color:#059669;">{} {:,.0f}</strong>',
            obj.currency, obj.vendor_payout
        )
    payout_display.short_description = 'Vendor Payout'

    def status_badge(self, obj):
        colours = {
            'pending':   ('#f3f4f6', '#6b7280'),
            'paid':      ('#fff7ed', '#c2410c'),
            'shipped':   ('#eff6ff', '#1d4ed8'),
            'delivered': ('#d1fae5', '#065f46'),
            'completed': ('#d1fae5', '#065f46'),
            'disputed':  ('#fee2e2', '#b91c1c'),
            'refunded':  ('#f5f3ff', '#6d28d9'),
        }
        bg, fg = colours.get(obj.status, ('#f3f4f6', '#6b7280'))
        return format_html(
            '<span style="background:{};color:{};padding:2px 10px;border-radius:100px;'
            'font-size:11px;font-weight:700;">{}</span>',
            bg, fg, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def trigger_payout_action(self, request, queryset):
        from sellers.views import _trigger_payout
        count = 0
        for order in queryset.filter(payout_triggered=False, status__in=['delivered', 'completed']):
            _trigger_payout(order)
            count += 1
        self.message_user(request, f"💸 Payout triggered for {count} order(s)")
    trigger_payout_action.short_description = "Trigger payout to vendor"

    def mark_delivered_action(self, request, queryset):
        updated = queryset.filter(status='shipped').update(
            status='delivered', delivered_at=timezone.now()
        )
        self.message_user(request, f"✅ {updated} order(s) marked as delivered")
    mark_delivered_action.short_description = "Mark as Delivered (admin override)"

    def mark_refunded_action(self, request, queryset):
        updated = queryset.exclude(status='refunded').update(status='refunded')
        self.message_user(request, f"💜 {updated} order(s) marked as refunded")
    mark_refunded_action.short_description = "Mark as Refunded"


# ─────────────────────────────────────────────────────────────
# DISPUTE ADMIN
# ─────────────────────────────────────────────────────────────
@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = [
        'order_ref_link', 'seller_name', 'buyer_email',
        'reason', 'status_badge', 'raised_by', 'created_at',
    ]
    list_filter = ['status', 'reason', 'raised_by', 'created_at']
    search_fields = [
        'order__order_ref', 'order__buyer_email',
        'order__seller__business_name', 'buyer_message',
    ]
    readonly_fields = [
        'order', 'raised_by', 'reason',
        'buyer_message', 'buyer_evidence', 'created_at',
    ]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    list_select_related = ['order', 'order__seller']

    fieldsets = [
        ('Order', {'fields': ('order', 'raised_by', 'reason', 'status')}),
        ('Buyer Side', {'fields': ('buyer_message', 'buyer_evidence')}),
        ('Vendor Side', {'fields': ('vendor_reply', 'vendor_evidence')}),
        ('Admin Resolution', {'fields': ('admin_note', 'resolved_at')}),
    ]

    actions = ['resolve_for_buyer', 'resolve_for_vendor']

    def order_ref_link(self, obj):
        url = reverse('admin:sellers_order_change', args=[obj.order.id])
        return format_html(
            '<a href="{}" style="font-family:monospace;font-weight:700;">#{}</a>',
            url, str(obj.order.order_ref)[:8].upper()
        )
    order_ref_link.short_description = 'Order'

    def seller_name(self, obj):
        return obj.order.seller.business_name
    seller_name.short_description = 'Seller'

    def buyer_email(self, obj):
        return obj.order.buyer_email
    buyer_email.short_description = 'Buyer Email'

    def status_badge(self, obj):
        colours = {
            'open':            ('#fee2e2', '#b91c1c'),
            'vendor_replied':  ('#eff6ff', '#1d4ed8'),
            'under_review':    ('#fff7ed', '#c2410c'),
            'resolved_buyer':  ('#d1fae5', '#065f46'),
            'resolved_vendor': ('#d1fae5', '#065f46'),
            'closed':          ('#f3f4f6', '#6b7280'),
        }
        bg, fg = colours.get(obj.status, ('#f3f4f6', '#6b7280'))
        return format_html(
            '<span style="background:{};color:{};padding:2px 10px;border-radius:100px;'
            'font-size:11px;font-weight:700;">{}</span>',
            bg, fg, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def resolve_for_buyer(self, request, queryset):
        for dispute in queryset.filter(status__in=['open', 'vendor_replied', 'under_review']):
            dispute.status      = 'resolved_buyer'
            dispute.resolved_at = timezone.now()
            dispute.save()
            dispute.order.status = 'refunded'
            dispute.order.save()
        self.message_user(request, "✅ Disputes resolved in buyer's favour — manual refund required")
    resolve_for_buyer.short_description = "Resolve: Refund buyer (manual refund needed)"

    def resolve_for_vendor(self, request, queryset):
        from sellers.views import _trigger_payout
        for dispute in queryset.filter(status__in=['open', 'vendor_replied', 'under_review']):
            dispute.status      = 'resolved_vendor'
            dispute.resolved_at = timezone.now()
            dispute.save()
            order              = dispute.order
            order.status       = 'delivered'
            order.delivered_at = timezone.now()
            order.save()
            _trigger_payout(order)
        self.message_user(request, "✅ Disputes resolved in vendor's favour — payouts triggered")
    resolve_for_vendor.short_description = "Resolve: Pay vendor (triggers payout)"


# ─────────────────────────────────────────────────────────────
# REVIEW ADMIN
# ─────────────────────────────────────────────────────────────
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = [
        'order_ref_link', 'seller_link', 'stars',
        'comment_short', 'is_verified', 'created_at',
    ]
    list_filter = ['rating', 'is_verified', 'created_at']
    search_fields = [
        'order__order_ref', 'seller__business_name',
        'order__buyer_name', 'comment',
    ]
    readonly_fields = ['order', 'seller', 'rating', 'is_verified', 'created_at']
    ordering = ['-created_at']
    list_select_related = ['order', 'seller']
    actions = ['delete_selected']

    def order_ref_link(self, obj):
        url = reverse('admin:sellers_order_change', args=[obj.order.id])
        return format_html(
            '<a href="{}" style="font-family:monospace;">#{}</a>',
            url, str(obj.order.order_ref)[:8].upper()
        )
    order_ref_link.short_description = 'Order'

    def seller_link(self, obj):
        url = reverse('admin:sellers_seller_change', args=[obj.seller.id])
        return format_html('<a href="{}">{}</a>', url, obj.seller.business_name)
    seller_link.short_description = 'Seller'

    def stars(self, obj):
        filled = '★' * obj.rating
        empty  = '☆' * (5 - obj.rating)
        colour = '#f59e0b' if obj.rating >= 4 else '#6b7280'
        return format_html(
            '<span style="color:{};font-size:15px;">{}</span>'
            '<span style="color:#d1d5db;">{}</span>',
            colour, filled, empty
        )
    stars.short_description = 'Rating'

    def comment_short(self, obj):
        c = obj.comment or ''
        return (c[:80] + '…') if len(c) > 80 else c or '—'
    comment_short.short_description = 'Comment'


# ─────────────────────────────────────────────────────────────
# VENDOR BANK ACCOUNT ADMIN
# ─────────────────────────────────────────────────────────────
@admin.register(VendorBankAccount)
class VendorBankAccountAdmin(admin.ModelAdmin):
    list_display = [
        'seller_link', 'account_name', 'account_number_masked',
        'bank_name', 'is_verified', 'created_at',
    ]
    list_filter  = ['is_verified', 'bank_name', 'created_at']
    search_fields = [
        'seller__business_name', 'account_name',
        'account_number', 'bank_name',
    ]
    readonly_fields    = ['seller', 'created_at', 'updated_at']
    list_select_related = ['seller']
    actions = ['mark_verified', 'mark_unverified']

    def seller_link(self, obj):
        url = reverse('admin:sellers_seller_change', args=[obj.seller.id])
        return format_html('<a href="{}">{}</a>', url, obj.seller.business_name)
    seller_link.short_description = 'Seller'

    def account_number_masked(self, obj):
        n = obj.account_number
        return f"****{n[-4:]}" if len(n) >= 4 else n
    account_number_masked.short_description = 'Account No.'

    def mark_verified(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f"✅ {updated} account(s) marked as verified")
    mark_verified.short_description = "Mark as Verified"

    def mark_unverified(self, request, queryset):
        updated = queryset.update(is_verified=False)
        self.message_user(request, f"⚠️ {updated} account(s) marked as unverified")
    mark_unverified.short_description = "Mark as Unverified"


# ─────────────────────────────────────────────────────────────
# PLATFORM SETTINGS ADMIN  (singleton — one row only)
# ─────────────────────────────────────────────────────────────
@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ['transaction_fee_percent', 'premium_monthly_price', 'updated_at']

    fieldsets = [
        ('Transaction Fees', {
            'fields': ('transaction_fee_percent',),
            'description': (
                'Percentage taken from each escrow order as platform revenue. '
                'e.g. 5.00 = 5%. Takes effect immediately on all new orders.'
            ),
        }),
        ('Subscription Pricing', {
            'fields': ('premium_monthly_price',),
            'description': 'Monthly premium price in NGN. Takes effect on next payment attempt.',
        }),
    ]

    def has_add_permission(self, request):
        return not PlatformSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False