# products/models.py
from django.db import models
from django.utils import timezone
from datetime import timedelta
from sellers.models import Seller


class Product(models.Model):
    seller      = models.ForeignKey(
        Seller, on_delete=models.CASCADE,
        null=True, blank=True, related_name='products'
    )
    # ── Name field (added) ──────────────────────────────────────────────────
    name        = models.CharField(max_length=80, blank=True, default='')
    # ────────────────────────────────────────────────────────────────────────
    description = models.TextField(blank=True, null=True)
    price       = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    is_archived = models.BooleanField(default=False)
    is_sold_out = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)
    views       = models.IntegerField(default=0)
    whatsapp_clicks = models.IntegerField(default=0)
    guest_key   = models.CharField(max_length=64, blank=True, null=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    # ── Helpers ──────────────────────────────────────────────────────────────

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(days=30)

    def get_primary_image(self):
        return self.images.first()

    def get_whatsapp_message(self):
        """
        Builds a clean WhatsApp pre-fill message.
        Uses `name` first; falls back to a truncated description.
        """
        # Prefer the dedicated name field; fall back to first 60 chars of description
        title = (
            self.name.strip()
            or (self.description[:60].strip() if self.description else None)
            or 'this item'
        )

        msg = f"Hi! I'm interested in {title}"

        if self.price:
            # Format with currency symbol if available, otherwise plain number
            symbol = getattr(self.seller, 'currency_symbol', '₦') or '₦'
            msg += f" ({symbol}{self.price:,.0f})"

        msg += f"\n\nFrom: {self.seller.business_name}"
        return msg

    def get_shareable_link(self, request):
        return request.build_absolute_uri(f'/{self.seller.slug}')

    def __str__(self):
        label = self.name or (self.description[:40] if self.description else '—')
        return f"{self.seller.business_name} · {label}"


class ProductImage(models.Model):
    product   = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image_url = models.URLField(max_length=500)
    order     = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"Image {self.order} for {self.product}"