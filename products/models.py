# products/models.py
from django.db import models
from django.utils import timezone
from datetime import timedelta
from sellers.models import Seller


class Product(models.Model):
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='products')
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    is_archived = models.BooleanField(default=False)
    is_sold_out = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    views = models.IntegerField(default=0)
    whatsapp_clicks = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
    
    def is_expired(self):
        expiry_date = self.created_at + timedelta(days=30)
        return timezone.now() > expiry_date
    
    def get_primary_image(self):
        return self.images.first()
    
    def get_whatsapp_message(self):
        msg = f"Hi! I'm interested in this product"
        if self.description:
            desc = self.description[:50]
            msg += f": {desc}..."
        if self.price:
            msg += f" (₦{self.price:,.0f})"
        msg += f"\n\nPosted: {self.created_at.strftime('%B %d, %Y')}"
        msg += f"\n\nFrom: {self.seller.business_name}"
        return msg
    
    def get_shareable_link(self, request):
        return request.build_absolute_uri(f'/{self.seller.slug}')
    
    def __str__(self):
        return f"{self.seller.business_name} - {self.created_at.strftime('%Y-%m-%d')}"


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image_url = models.URLField(max_length=500)  # New primary field
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order', 'created_at']
    
    def __str__(self):
        return f"Image {self.order} for {self.product}"