
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify
from django.utils import timezone
import uuid

class Seller(AbstractUser):
    SUBSCRIPTION_CHOICES = [
        ('free', 'Free'),  # Now unlimited products!
        ('premium', 'Premium'),  # Removes "Powered by" badge
    ]
    
    business_name = models.CharField(max_length=200)
    
    # IMPORTANT: Make these unique with case-insensitive checks
    email = models.EmailField(unique=True)  # Built-in unique
    whatsapp_number = models.CharField(max_length=20, unique=True)
    # username is already unique from AbstractUser
    
    bio = models.TextField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    slug = models.SlugField(unique=True, blank=True)
    category = models.CharField(max_length=100)
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
        # Normalize email to lowercase
        if self.email:
            self.email = self.email.lower()
        
        # Generate slug if not exists
        if not self.slug:
            base_slug = slugify(self.business_name)
            if not base_slug:  # If business name only has special chars
                base_slug = f"seller-{uuid.uuid4().hex[:8]}"
            
            slug = base_slug
            counter = 1
            while Seller.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        
        super().save(*args, **kwargs)
    
    def get_product_limit(self):
        """Now returns None (unlimited) for all users"""
        return None  # Everyone gets unlimited!
    
    def shows_powered_by_badge(self):
        """Only free users see the badge"""
        return self.subscription_type == 'free'
    
    def __str__(self):
        return self.business_name
