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

