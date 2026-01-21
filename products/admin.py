
# products/admin.py
from django.contrib import admin
from .models import Product, ProductImage

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ['image', 'order']
    readonly_fields = ['created_at']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'seller', 
        'description_preview', 
        'price', 
        'image_count',
        'is_sold_out',
        'is_archived', 
        'views',
        'whatsapp_clicks',
        'created_at'
    ]
    list_filter = ['is_archived', 'is_sold_out', 'created_at', 'seller']
    search_fields = ['seller__business_name', 'description']
    inlines = [ProductImageInline]
    list_editable = ['is_sold_out', 'is_archived']
    
    fieldsets = (
        ('Product Info', {
            'fields': ('seller', 'description', 'price')
        }),
        ('Status', {
            'fields': ('is_sold_out', 'is_archived')
        }),
        ('Analytics', {
            'fields': ('views', 'whatsapp_clicks', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'views', 'whatsapp_clicks']
    
    def description_preview(self, obj):
        if obj.description:
            return obj.description[:60] + ('...' if len(obj.description) > 60 else '')
        return 'No description'
    description_preview.short_description = 'Description'
    
    def image_count(self, obj):
        count = obj.images.count()
        if count > 1:
            return f'📷 {count} photos'
        return '📷 1 photo'
    image_count.short_description = 'Images'
    
    actions = ['mark_sold_out', 'mark_available', 'archive_products', 'unarchive_products']
    
    def mark_sold_out(self, request, queryset):
        count = queryset.update(is_sold_out=True)
        self.message_user(request, f"{count} products marked as sold out")
    mark_sold_out.short_description = "Mark as SOLD OUT"
    
    def mark_available(self, request, queryset):
        count = queryset.update(is_sold_out=False)
        self.message_user(request, f"{count} products marked as available")
    mark_available.short_description = "Mark as AVAILABLE"
    
    def archive_products(self, request, queryset):
        count = queryset.update(is_archived=True)
        self.message_user(request, f"{count} products archived")
    archive_products.short_description = "Archive products"
    
    def unarchive_products(self, request, queryset):
        count = queryset.update(is_archived=False)
        self.message_user(request, f"{count} products unarchived")
    unarchive_products.short_description = "Unarchive products"


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['id', 'product', 'order', 'image_preview', 'created_at']
    list_filter = ['created_at']
    search_fields = ['product__seller__business_name', 'product__description']
    
    def image_preview(self, obj):
        if obj.image:
            return f'<img src="{obj.image.url}" style="max-height: 50px; max-width: 50px; object-fit: cover;" />'
        return 'No image'
    image_preview.short_description = 'Preview'
    image_preview.allow_tags = True