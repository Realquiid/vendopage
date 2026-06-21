# sellers/models.py
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import AbstractUser, UserManager
from django.utils.text import slugify
from django.utils import timezone
from cloudinary.models import CloudinaryField
import uuid

class SellerManager(UserManager):
    def create_user(self, email=None, password=None, **extra_fields):
        if not email:
            raise ValueError("The given email must be set")
        email = self.normalize_email(email)
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email=email, password=password, **extra_fields)


        
class Seller(AbstractUser):
    SUBSCRIPTION_CHOICES = [
        ('free', 'Free'),
        ('premium', 'Premium'),
    ]

    # ── Monetization tiers ────────────────────────────────────
    TIER_CHOICES = [
        ('starter', 'Starter'),
        ('growth', 'Growth'),
        ('pro', 'Pro'),
    ]

    TIER_CONFIG = {
        'starter': {
            'label': 'Starter',
            'fee_percent': Decimal('5.00'),
            'cap': Decimal('50000.00'),
            'price': Decimal('0.00'),
        },
        'growth': {
            'label': 'Growth',
            'fee_percent': Decimal('2.50'),
            'cap': Decimal('300000.00'),
            'price': Decimal('2500.00'),
        },
        'pro': {
            'label': 'Pro',
            'fee_percent': Decimal('1.50'),
            'cap': Decimal('1500000.00'),
            'price': Decimal('5000.00'),
        },
    }

    OVERFLOW_FEE_PERCENT = Decimal('5.00')  # fallback rate once cap is exceeded

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

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    objects = SellerManager()

    business_name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    whatsapp_number = models.CharField(max_length=20, unique=True)
    bio = models.TextField(blank=True, null=True)
    profile_picture = CloudinaryField('image', blank=True, null=True)
    slug = models.SlugField(unique=True, blank=True)
    watermark_enabled = models.BooleanField(default=True)
    country_code = models.CharField(max_length=10, default='+234')
    currency_code = models.CharField(max_length=10, default='NGN')
    currency_symbol = models.CharField(max_length=10, default='₦')
    store_mode = models.BooleanField(default=False)
    store_mode_enabled_at = models.DateTimeField(blank=True, null=True)
    category = models.CharField(
        max_length=100,
        choices=CATEGORY_CHOICES,
        default='other',
        blank=True,
        null=True
    )

    subscription_type = models.CharField(max_length=20, choices=SUBSCRIPTION_CHOICES, default='free')
    subscription_expires = models.DateTimeField(blank=True, null=True)

    # ── Volume-capped monetization matrix ──────────────────────
    subscription_tier = models.CharField(
        max_length=10, choices=TIER_CHOICES, default='starter',
        help_text="Determines commission rate and monthly volume cap."
    )
    monthly_volume_processed = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        help_text="Total order subtotal processed this billing month."
    )
    tier_reset_date = models.DateField(
        default=timezone.now,
        help_text="Last date monthly_volume_processed was reset."
    )

    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    

    # Analytics
    total_page_views = models.IntegerField(default=0)
    weekly_page_views = models.IntegerField(default=0)
    weekly_whatsapp_clicks = models.IntegerField(default=0)
    last_analytics_reset = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(null=True, blank=True,help_text="Last time this seller made any request to the platform.")
    email_verified = models.BooleanField(default=False)
    email_verify_token = models.CharField(max_length=64, blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()

        if not self.username:
            base = slugify(self.business_name).replace('-', '_')[:25] or 'seller'
            uname = base
            counter = 1
            while Seller.objects.filter(username__iexact=uname).exclude(pk=self.pk).exists():
                uname = f"{base}_{counter}"
                counter += 1
            self.username = uname

        if not self.slug:
            base_slug = slugify(self.business_name)[:40]
            if not base_slug:
                base_slug = f"seller-{uuid.uuid4().hex[:8]}"

            slug = base_slug
            counter = 1
            while Seller.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
                if len(slug) > 50:
                    base_slug = base_slug[:40 - len(str(counter))]
                    slug = f"{base_slug}-{counter}"
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

        if self.subscription_expires:
            return self.subscription_expires > timezone.now()

        return True

    @property
    def subscription_active(self):
        """Alias for is_subscribed - for template compatibility"""
        return self.is_subscribed

    # ── Monetization helpers ───────────────────────────────────
    def get_tier_config(self):
        return self.TIER_CONFIG.get(self.subscription_tier, self.TIER_CONFIG['starter'])

    def get_commission_rate(self, order_amount=None):
        """
        Returns the platform fee % to apply to a transaction RIGHT NOW,
        based on volume already processed this month.

        - starter: always 5%
        - growth/pro: tier rate, UNLESS monthly_volume_processed already
          meets/exceeds the tier cap — then falls back to 5%.
        """
        config = self.get_tier_config()

        if self.subscription_tier == 'starter':
            return config['fee_percent']

        if self.monthly_volume_processed >= config['cap']:
            return self.OVERFLOW_FEE_PERCENT

        return config['fee_percent']

    def record_volume(self, amount):
        """Add an order's subtotal to this month's processed volume."""
        self.monthly_volume_processed = (self.monthly_volume_processed or Decimal('0.00')) + amount
        self.save(update_fields=['monthly_volume_processed'])

    def __str__(self):
        return self.business_name


from django.conf import settings


# ── Vendor Bank Account ─────────────────────────────────────
class VendorBankAccount(models.Model):
    seller = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bank_account'
    )
    account_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=20)
    bank_name = models.CharField(max_length=200)
    bank_code = models.CharField(max_length=20, blank=True)  # Flutterwave bank code
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    recipient_code = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.seller.business_name} — {self.bank_name} {self.account_number}"


# ── Order ────────────────────────────────────────────────────
class Order(models.Model):

    STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('paid', 'Paid — Awaiting Shipment'),
        ('shipped', 'Shipped'),
        ('RECEIVED', 'Received — Awaiting 24h Payout'),
        ('delivered', 'Delivered'),
        ('disputed', 'Disputed'),
        ('refunded', 'Refunded'),
        ('FAILED_PAYOUT', 'Payout Failed — Retrying Tomorrow'),
        ('completed', 'Completed — Paid Out'),
    ]

    order_ref = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders_received'
    )

    # Buyer info (no account required)
    buyer_name = models.CharField(max_length=200)
    buyer_email = models.EmailField()
    buyer_phone = models.CharField(max_length=30)
    delivery_address = models.TextField()
    delivery_city = models.CharField(max_length=100, blank=True)
    delivery_country = models.CharField(max_length=100, blank=True)
    # Financials
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vendor_payout = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default='NGN')
    commission_rate_applied = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True,
        help_text="The commission % actually applied to this order (for auditing)."
    )

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Payment
    flutterwave_tx_id = models.CharField(max_length=200, blank=True)
    flutterwave_tx_ref = models.CharField(max_length=200, blank=True, unique=True)
    payment_verified = models.BooleanField(default=False)
    paid_at = models.DateTimeField(blank=True, null=True)

    # Shipping
    tracking_info = models.CharField(max_length=500, blank=True)
    courier_name = models.CharField(max_length=200, blank=True)
    shipped_at = models.DateTimeField(blank=True, null=True)

    # Delivery confirmation
    delivered_at = models.DateTimeField(blank=True, null=True)
    auto_release_at = models.DateTimeField(blank=True, null=True)  # 72hrs after shipped_at

    payment_type = models.CharField(
        max_length=10,
        choices=[('escrow', 'Escrow'), ('direct', 'Direct')],
        default='escrow'
    )
    delivery_required = models.BooleanField(default=True)

    # Payout
    payout_triggered = models.BooleanField(default=False)
    payout_at = models.DateTimeField(blank=True, null=True)
    flutterwave_transfer_id = models.CharField(max_length=200, blank=True)
    refund_reference = models.CharField(max_length=200, blank=True)
    refund_initiated_at = models.DateTimeField(blank=True, null=True)
    is_disputed = models.BooleanField(default=False)
    dispute_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {self.order_ref} — {self.seller.business_name}"

    def calculate_fees(self):
        """
        Determines platform fee % from the seller's subscription tier and
        current monthly volume (with automatic fallback to 5% once the
        tier's volume cap is reached), then records the volume processed.
        """
        seller = self.seller
        fee_percent = seller.get_commission_rate(self.subtotal)

        self.commission_rate_applied = fee_percent
        self.platform_fee = (self.subtotal * fee_percent) / Decimal('100')
        self.vendor_payout = self.subtotal - self.platform_fee

        # Record volume AFTER computing this order's rate, so the cap
        # check reflects volume *before* this transaction.
        seller.record_volume(self.subtotal)

    def set_auto_release(self, hours=72):
        """Set auto-release timestamp after vendor marks shipped."""
        from datetime import timedelta
        self.auto_release_at = timezone.now() + timedelta(hours=hours)


# ── Order Item ───────────────────────────────────────────────
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_id = models.IntegerField()
    product_name = models.CharField(max_length=500)
    product_image_url = models.URLField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    @property
    def line_total(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.product_name}"


# ── Dispute ──────────────────────────────────────────────────
class Dispute(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('vendor_replied', 'Vendor Replied'),
        ('under_review', 'Under Admin Review'),
        ('resolved_buyer', 'Resolved — Refund to Buyer'),
        ('resolved_vendor', 'Resolved — Paid to Vendor'),
        ('closed', 'Closed'),
    ]
    REASON_CHOICES = [
        ('not_received', 'Item not received'),
        ('wrong_item', 'Wrong item sent'),
        ('damaged', 'Item arrived damaged'),
        ('not_as_described', 'Not as described'),
        ('other', 'Other'),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='dispute')
    raised_by = models.CharField(max_length=20, default='buyer')
    reason = models.CharField(max_length=50, choices=REASON_CHOICES)
    buyer_message = models.TextField()
    buyer_evidence = models.URLField(blank=True)
    vendor_reply = models.TextField(blank=True)
    vendor_evidence = models.URLField(blank=True)
    admin_note = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Dispute on Order {self.order.order_ref} — {self.status}"


# ── Review ───────────────────────────────────────────────────
class Review(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='review')
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews_received'
    )
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    is_verified = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

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
        help_text="Default/fallback platform fee percentage (used when seller has no tier override)."
    )
    premium_monthly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=2000.00,
        help_text="Legacy premium subscription price in NGN (kept for backward compatibility)."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Platform Settings"
        verbose_name_plural = "Platform Settings"

    def __str__(self):
        return f"Platform Settings (fee: {self.transaction_fee_percent}%, premium: ₦{self.premium_monthly_price}/mo)"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)