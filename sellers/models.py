# sellers/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify
from django.utils import timezone
from cloudinary.models import CloudinaryField
import uuid

class Seller(AbstractUser):
    SUBSCRIPTION_CHOICES = [
        ('free', 'Free'),
        ('premium', 'Premium'),
    ]
    
    # CATEGORY CHOICES - Matching your registration form exactly
    CATEGORY_CHOICES = [
        ('fashion', 'Fashion & Apparel'),
        ('beauty', 'Beauty & Cosmetics'),
        ('electronics', 'Electronics & Gadgets'),
        ('food', 'Food & Beverages'),
        ('home', 'Home & Garden'),
        ('sports', 'Sports & Fitness'),
        ('health', 'Health & Wellness'),
        ('other', 'Other'),
    ]
    
    business_name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    whatsapp_number = models.CharField(max_length=20, unique=True)
    bio = models.TextField(blank=True, null=True)
    profile_picture = CloudinaryField('image', blank=True, null=True)
    slug = models.SlugField(unique=True, blank=True)
    watermark_enabled = models.BooleanField(default=True)
    country_code  = models.CharField(max_length=10, default='+234')
    currency_code = models.CharField(max_length=10, default='NGN')
    currency_symbol = models.CharField(max_length=10, default='₦')
    store_mode = models.BooleanField(default=False)
    store_mode_enabled_at = models.DateTimeField(blank=True, null=True)
    # UPDATED: Changed from plain CharField to choices field
    category = models.CharField(
        max_length=100,
        choices=CATEGORY_CHOICES,
        default='other',
        blank=True,
        null=True
    )
    
    subscription_type = models.CharField(max_length=20, choices=SUBSCRIPTION_CHOICES, default='free')
    subscription_expires = models.DateTimeField(blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Analytics
    total_page_views = models.IntegerField(default=0)
    weekly_page_views = models.IntegerField(default=0)
    weekly_whatsapp_clicks = models.IntegerField(default=0)
    last_analytics_reset = models.DateTimeField(default=timezone.now)
    
    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        
        if not self.slug:
            base_slug = slugify(self.business_name)
            if not base_slug:
                base_slug = f"seller-{uuid.uuid4().hex[:8]}"
            
            slug = base_slug
            counter = 1
            while Seller.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        
        super().save(*args, **kwargs)
    
    def get_product_limit(self):
        """Returns product limit based on subscription. None = unlimited"""
        return None
    
    def shows_powered_by_badge(self):
        """Returns True for free users (they see 'Powered by VendoPage')"""
        return self.subscription_type == 'free'
    
    @property
    def is_subscribed(self):
        """
        Returns True if user has active premium subscription.
        This property is used in templates to show/hide the verified badge.
        """
        if self.subscription_type != 'premium':
            return False
        
        # Check if subscription has expired
        if self.subscription_expires:
            return self.subscription_expires > timezone.now()
        
        # If no expiration date but marked as premium, consider it active
        return True
    
    @property
    def subscription_active(self):
        """Alias for is_subscribed - for template compatibility"""
        return self.is_subscribed
    
    def __str__(self):
        return self.business_name



from django.conf import settings


# ── Vendor Bank Account ─────────────────────────────────────
class VendorBankAccount(models.Model):
    seller        = models.OneToOneField(
                        settings.AUTH_USER_MODEL,
                        on_delete=models.CASCADE,
                        related_name='bank_account'
                    )
    account_name  = models.CharField(max_length=200)
    account_number= models.CharField(max_length=20)
    bank_name     = models.CharField(max_length=200)
    bank_code     = models.CharField(max_length=20, blank=True)  # Flutterwave bank code
    is_verified   = models.BooleanField(default=False)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)
    recipient_code = models.CharField(max_length=100, blank=True)
    def __str__(self):
        return f"{self.seller.business_name} — {self.bank_name} {self.account_number}"


# ── Order ────────────────────────────────────────────────────
class Order(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending Payment'),      # payment not yet confirmed
        ('paid',      'Paid — Awaiting Shipment'),
        ('shipped',   'Shipped'),
        ('delivered', 'Delivered'),            # buyer confirmed receipt
        ('disputed',  'Disputed'),
        ('refunded',  'Refunded'),
        ('completed', 'Completed'),            # payout released to vendor
    ]

    order_ref        = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    seller           = models.ForeignKey(
                           settings.AUTH_USER_MODEL,
                           on_delete=models.CASCADE,
                           related_name='orders_received'
                       )

    # Buyer info (no account required)
    buyer_name       = models.CharField(max_length=200)
    buyer_email      = models.EmailField()
    buyer_phone      = models.CharField(max_length=30)
    delivery_address = models.TextField()
    delivery_city    = models.CharField(max_length=100, blank=True)
    delivery_country = models.CharField(max_length=100, blank=True)

    # Financials
    subtotal         = models.DecimalField(max_digits=12, decimal_places=2)
    platform_fee     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vendor_payout    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency         = models.CharField(max_length=10, default='NGN')

    # Status
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Payment
    flutterwave_tx_id  = models.CharField(max_length=200, blank=True)
    flutterwave_tx_ref = models.CharField(max_length=200, blank=True, unique=True)
    payment_verified   = models.BooleanField(default=False)
    paid_at            = models.DateTimeField(blank=True, null=True)

    # Shipping
    tracking_info      = models.CharField(max_length=500, blank=True)
    courier_name       = models.CharField(max_length=200, blank=True)
    shipped_at         = models.DateTimeField(blank=True, null=True)

    # Delivery confirmation
    delivered_at       = models.DateTimeField(blank=True, null=True)
    auto_release_at    = models.DateTimeField(blank=True, null=True)  # 72hrs after shipped_at

    payment_type     = models.CharField(
    max_length=10,
    choices=[('escrow','Escrow'),('direct','Direct')],
    default='escrow'
    )
    delivery_required = models.BooleanField(default=True)
    
    # Payout
    payout_triggered   = models.BooleanField(default=False)
    payout_at          = models.DateTimeField(blank=True, null=True)
    flutterwave_transfer_id = models.CharField(max_length=200, blank=True)

    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {self.order_ref} — {self.seller.business_name}"



    def calculate_fees(self):
        """
        Pull platform fee % from PlatformSettings (configurable from Django admin).
        Falls back to 5% if settings row doesn't exist yet.
        """
        from decimal import Decimal
        try:
            fee_percent = PlatformSettings.get().transaction_fee_percent
        except Exception:
            fee_percent = Decimal('5.00')
 
        self.platform_fee  = (self.subtotal * fee_percent) / Decimal('100')
        self.vendor_payout = self.subtotal - self.platform_fee
 

    def set_auto_release(self, hours=72):
        """Set auto-release timestamp after vendor marks shipped."""
        from datetime import timedelta
        self.auto_release_at = timezone.now() + timedelta(hours=hours)


# ── Order Item ───────────────────────────────────────────────
class OrderItem(models.Model):
    order       = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_id  = models.IntegerField()               # snapshot at time of order
    product_name= models.CharField(max_length=500)    # snapshot
    product_image_url = models.URLField(blank=True)   # snapshot
    price       = models.DecimalField(max_digits=12, decimal_places=2)
    quantity    = models.PositiveIntegerField(default=1)

    @property
    def line_total(self):
        return self.price * self.quantity
    
    

    def __str__(self):
        return f"{self.quantity}x {self.product_name}"


# ── Dispute ──────────────────────────────────────────────────
class Dispute(models.Model):
    STATUS_CHOICES = [
        ('open',           'Open'),
        ('vendor_replied', 'Vendor Replied'),
        ('under_review',   'Under Admin Review'),
        ('resolved_buyer', 'Resolved — Refund to Buyer'),
        ('resolved_vendor','Resolved — Paid to Vendor'),
        ('closed',         'Closed'),
    ]
    REASON_CHOICES = [
        ('not_received',   'Item not received'),
        ('wrong_item',     'Wrong item sent'),
        ('damaged',        'Item arrived damaged'),
        ('not_as_described','Not as described'),
        ('other',          'Other'),
    ]

    order          = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='dispute')
    raised_by      = models.CharField(max_length=20, default='buyer')  # 'buyer' or 'vendor'
    reason         = models.CharField(max_length=50, choices=REASON_CHOICES)
    buyer_message  = models.TextField()
    buyer_evidence = models.URLField(blank=True)      # optional screenshot/photo URL
    vendor_reply   = models.TextField(blank=True)
    vendor_evidence= models.URLField(blank=True)
    admin_note     = models.TextField(blank=True)
    status         = models.CharField(max_length=30, choices=STATUS_CHOICES, default='open')
    created_at     = models.DateTimeField(auto_now_add=True)
    resolved_at    = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Dispute on Order {self.order.order_ref} — {self.status}"


# ── Review ───────────────────────────────────────────────────
class Review(models.Model):
    order    = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='review')
    seller   = models.ForeignKey(
                   settings.AUTH_USER_MODEL,
                   on_delete=models.CASCADE,
                   related_name='reviews_received'
               )
    rating   = models.PositiveSmallIntegerField()   # 1–5
    comment  = models.TextField(blank=True)
    is_verified = models.BooleanField(default=True) # always True — tied to real order
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.rating}★ for {self.seller.business_name}"




class PlatformSettings(models.Model):
    """
    Singleton model — only one row ever exists.
    Controls platform-wide settings configurable from Django admin.
    """
    transaction_fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=5.00,
        help_text="Platform fee percentage taken from each escrow order (e.g. 5.00 = 5%)"
    )
    premium_monthly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=2000.00,
        help_text="Monthly premium subscription price in NGN"
    )
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name = "Platform Settings"
        verbose_name_plural = "Platform Settings"
 
    def __str__(self):
        return f"Platform Settings (fee: {self.transaction_fee_percent}%, premium: ₦{self.premium_monthly_price}/mo)"
 
    @classmethod
    def get(cls):
        """
        Always returns the single settings object.
        Creates it with defaults if it doesn't exist yet.
        """
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
 
    def save(self, *args, **kwargs):
        # Force pk=1 — singleton pattern
        self.pk = 1
        super().save(*args, **kwargs)
 