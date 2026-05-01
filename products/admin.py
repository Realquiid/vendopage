
# products/admin.py
# from django.contrib import admin
# from .models import Product, ProductImage

# class ProductImageInline(admin.TabularInline):
#     model = ProductImage
#     extra = 1
#     fields = ['image', 'order']
#     readonly_fields = ['created_at']

# @admin.register(Product)
# class ProductAdmin(admin.ModelAdmin):
#     list_display = [
#         'id',
#         'seller', 
#         'description_preview', 
#         'price', 
#         'image_count',
#         'is_sold_out',
#         'is_archived', 
#         'views',
#         'whatsapp_clicks',
#         'created_at'
#     ]
#     list_filter = ['is_archived', 'is_sold_out', 'created_at', 'seller']
#     search_fields = ['seller__business_name', 'description']
#     inlines = [ProductImageInline]
#     list_editable = ['is_sold_out', 'is_archived']
    
#     fieldsets = (
#         ('Product Info', {
#             'fields': ('seller', 'description', 'price')
#         }),
#         ('Status', {
#             'fields': ('is_sold_out', 'is_archived')
#         }),
#         ('Analytics', {
#             'fields': ('views', 'whatsapp_clicks', 'created_at'),
#             'classes': ('collapse',)
#         }),
#     )
    
#     readonly_fields = ['created_at', 'views', 'whatsapp_clicks']
    
#     def description_preview(self, obj):
#         if obj.description:
#             return obj.description[:60] + ('...' if len(obj.description) > 60 else '')
#         return 'No description'
#     description_preview.short_description = 'Description'
    
#     def image_count(self, obj):
#         count = obj.images.count()
#         if count > 1:
#             return f'📷 {count} photos'
#         return '📷 1 photo'
#     image_count.short_description = 'Images'
    
#     actions = ['mark_sold_out', 'mark_available', 'archive_products', 'unarchive_products']
    
#     def mark_sold_out(self, request, queryset):
#         count = queryset.update(is_sold_out=True)
#         self.message_user(request, f"{count} products marked as sold out")
#     mark_sold_out.short_description = "Mark as SOLD OUT"
    
#     def mark_available(self, request, queryset):
#         count = queryset.update(is_sold_out=False)
#         self.message_user(request, f"{count} products marked as available")
#     mark_available.short_description = "Mark as AVAILABLE"
    
#     def archive_products(self, request, queryset):
#         count = queryset.update(is_archived=True)
#         self.message_user(request, f"{count} products archived")
#     archive_products.short_description = "Archive products"
    
#     def unarchive_products(self, request, queryset):
#         count = queryset.update(is_archived=False)
#         self.message_user(request, f"{count} products unarchived")
#     unarchive_products.short_description = "Unarchive products"


# @admin.register(ProductImage)
# class ProductImageAdmin(admin.ModelAdmin):
#     list_display = ['id', 'product', 'order', 'image_preview', 'created_at']
#     list_filter = ['created_at']
#     search_fields = ['product__seller__business_name', 'product__description']
    
#     def image_preview(self, obj):
#         if obj.image:
#             return f'<img src="{obj.image.url}" style="max-height: 50px; max-width: 50px; object-fit: cover;" />'
#         return 'No image'
#     image_preview.short_description = 'Preview'
#     image_preview.allow_tags = True



# products/admin.py
# ─────────────────────────────────────────────────────────────────────────────
# Registers: Product, ProductImage
#
# NOTE: Do NOT register Product or ProductImage in sellers/admin.py.
#       This file is the single owner of both models in the admin.
#
# BUG FIXED: The old image_preview method used obj.image (ImageField) but
#            ProductImage uses image_url (URLField). Fixed to use image_url.
# ─────────────────────────────────────────────────────────────────────────────

from django.contrib import admin
from django.utils.html import format_html
from .models import Product, ProductImage


# ─────────────────────────────────────────────────────────────
# INLINE: ProductImage inside Product
# ─────────────────────────────────────────────────────────────
class ProductImageInline(admin.TabularInline):
    model        = ProductImage
    extra        = 1
    fields       = ['image_preview', 'image_url', 'order']
    readonly_fields = ['image_preview', 'created_at']

    def image_preview(self, obj):
        # Uses image_url (URLField) — NOT obj.image (which doesn't exist)
        if obj.image_url:
            return format_html(
                '<img src="{}" style="height:60px;width:60px;object-fit:cover;'
                'border-radius:6px;border:1px solid #e5e7eb;" />',
                obj.image_url
            )
        return '—'
    image_preview.short_description = 'Preview'


# ─────────────────────────────────────────────────────────────
# PRODUCT ADMIN
# ─────────────────────────────────────────────────────────────
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'thumbnail',
        'description_preview',
        'seller_link',
        'price_display',
        'status_badge',
        'views',
        'whatsapp_clicks',
        'image_count',
        'created_at',
    ]
    list_filter   = ['is_archived', 'is_sold_out', 'created_at', 'seller__category']
    search_fields = ['seller__business_name', 'seller__username', 'description']
    inlines       = [ProductImageInline]
    # Removed list_editable=['is_sold_out', 'is_archived'] because it conflicts
    # with list_display having computed columns — use bulk actions instead.
    ordering      = ['-created_at']
    date_hierarchy = 'created_at'
    list_select_related = ['seller']

    fieldsets = (
        ('Product Info', {
            'fields': ('seller', 'description', 'price'),
        }),
        ('Status', {
            'fields': ('is_sold_out', 'is_archived'),
        }),
        ('Analytics', {
            'fields': ('views', 'whatsapp_clicks', 'created_at'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ['created_at', 'views', 'whatsapp_clicks']

    # ── Display columns ───────────────────────────────────────

    def thumbnail(self, obj):
        img = obj.images.order_by('order').first()
        if img and img.image_url:
            return format_html(
                '<img src="{}" style="height:48px;width:48px;object-fit:cover;'
                'border-radius:6px;border:1px solid #e5e7eb;" />',
                img.image_url
            )
        return '📦'
    thumbnail.short_description = ''

    def description_preview(self, obj):
        if obj.description:
            return obj.description[:60] + ('…' if len(obj.description) > 60 else '')
        return '—'
    description_preview.short_description = 'Description'

    def seller_link(self, obj):
        if obj.seller:
            from django.urls import reverse
            url = reverse('admin:sellers_seller_change', args=[obj.seller.id])
            return format_html('<a href="{}">{}</a>', url, obj.seller.business_name)
        return '— guest —'
    seller_link.short_description = 'Seller'

    def price_display(self, obj):
        if obj.price:
            sym = (obj.seller.currency_symbol if obj.seller else None) or '₦'
            return f"{sym}{obj.price:,.0f}"
        return '—'
    price_display.short_description = 'Price'

    def status_badge(self, obj):
        if obj.is_archived:
            return format_html(
                '<span style="background:#f3f4f6;color:#6b7280;padding:2px 8px;'
                'border-radius:100px;font-size:11px;">Archived</span>'
            )
        if obj.is_sold_out:
            return format_html(
                '<span style="background:#fee2e2;color:#b91c1c;padding:2px 8px;'
                'border-radius:100px;font-size:11px;">Sold Out</span>'
            )
        return format_html(
            '<span style="background:#d1fae5;color:#065f46;padding:2px 8px;'
            'border-radius:100px;font-size:11px;">● Live</span>'
        )
    status_badge.short_description = 'Status'

    def image_count(self, obj):
        count = obj.images.count()
        return f'📷 {count} photo{"s" if count != 1 else ""}'
    image_count.short_description = 'Images'

    # ── Bulk actions ──────────────────────────────────────────

    actions = ['mark_sold_out', 'mark_available', 'archive_products', 'unarchive_products']

    def mark_sold_out(self, request, queryset):
        count = queryset.update(is_sold_out=True)
        self.message_user(request, f"🔴 {count} product(s) marked as sold out")
    mark_sold_out.short_description = "Mark as Sold Out"

    def mark_available(self, request, queryset):
        count = queryset.update(is_sold_out=False)
        self.message_user(request, f"🟢 {count} product(s) marked as available")
    mark_available.short_description = "Mark as Available"

    def archive_products(self, request, queryset):
        count = queryset.update(is_archived=True)
        self.message_user(request, f"📦 {count} product(s) archived")
    archive_products.short_description = "Archive selected products"

    def unarchive_products(self, request, queryset):
        count = queryset.update(is_archived=False, is_sold_out=False)
        self.message_user(request, f"✅ {count} product(s) restored")
    unarchive_products.short_description = "Restore (unarchive) products"


# ─────────────────────────────────────────────────────────────
# PRODUCT IMAGE ADMIN  (standalone — for direct image management)
# ─────────────────────────────────────────────────────────────
@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display  = ['id', 'product_seller', 'image_preview', 'order', 'created_at']
    list_filter   = ['created_at']
    search_fields = ['product__seller__business_name', 'product__description']
    readonly_fields = ['created_at', 'image_preview']
    ordering      = ['product', 'order']

    def image_preview(self, obj):
        # Uses image_url (URLField) — correct field name from models.py
        if obj.image_url:
            return format_html(
                '<img src="{}" style="height:60px;width:60px;object-fit:cover;'
                'border-radius:6px;border:1px solid #e5e7eb;" />',
                obj.image_url
            )
        return '—'
    image_preview.short_description = 'Preview'

    def product_seller(self, obj):
        if obj.product and obj.product.seller:
            return f"{obj.product.seller.business_name} · {str(obj.product)[:30]}"
        return '—'
    product_seller.short_description = 'Product / Seller'