# sellers/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Sum
from django.utils import timezone
from datetime import timedelta, datetime
import urllib.parse
from django.db import IntegrityError
from sellers.models import Seller
from products.models import Product, ProductImage
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from PIL import Image
import os
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal, InvalidOperation
import uuid
import json
from sellers.email import send_password_reset_email
import random
import string
import logging

# Helper function to reset weekly analytics
def reset_weekly_analytics_if_needed(seller):
    """Reset weekly stats every Monday"""
    now = timezone.now()
    days_since_reset = (now - seller.last_analytics_reset).days
    
    if days_since_reset >= 7:
        seller.weekly_page_views = 0
        seller.weekly_whatsapp_clicks = 0
        seller.last_analytics_reset = now
        seller.save()

# Public Views
# sellers/views.py - Replace your home() function with this

def about(request):
    """About page"""
    return render(request, 'about.html')

def privacy(request):
    """Privacy Policy page"""
    return render(request, 'privacy.html')

def terms(request):
    """Terms of Service page"""
    return render(request, 'terms.html')
def contact(request):
    """Contact page"""
    return render(request, 'contact.html')

def home(request):
    """Homepage with seller listings - Only show sellers with 5+ products"""
    
    # Only show sellers who:
    # 1. Are active
    # 2. Are NOT staff/superusers (regular sellers only)
    # 3. Have at least 5 active products
    featured_sellers = Seller.objects.filter(
        is_featured=True,
        is_active=True,
        is_staff=False,
        is_superuser=False
    ).annotate(
        product_count=Count('products', filter=Q(
            products__is_archived=False,
            products__is_sold_out=False
        ))
    ).filter(
        product_count__gte=5  # Must have at least 5 active products
    ).order_by('-product_count')[:4]
    
    # Regular sellers (not featured) with 5+ products
    sellers = Seller.objects.filter(
        is_active=True,
        is_staff=False,
        is_superuser=False
    ).annotate(
        product_count=Count('products', filter=Q(
            products__is_archived=False,
            products__is_sold_out=False
        ))
    ).filter(
        product_count__gte=5  # Must have at least 5 active products
    ).exclude(
        id__in=featured_sellers.values_list('id', flat=True)
    ).order_by('-product_count')[:20]  # Show top 20 sellers by product count
    
    return render(request, 'home.html', {
        'featured_sellers': featured_sellers,
        'sellers': sellers
    })

# sellers/views.py (or wherever your seller_page view is)




def seller_page(request, slug):
    """
    Individual seller's product page with analytics.
    Page views are only tracked for non-owners (not counting when seller views their own page).
    """
    seller = get_object_or_404(Seller, slug=slug, is_active=True)
    
    # Track page view ONLY if viewer is NOT the seller themselves
    # This prevents sellers from inflating their own analytics
    if not request.user.is_authenticated or request.user.id != seller.id:
        seller.total_page_views += 1
        seller.weekly_page_views += 1
        seller.save(update_fields=['total_page_views', 'weekly_page_views'])
    
    # Get active products (not archived, within 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    products = Product.objects.filter(
        seller=seller,
        is_archived=False,
        created_at__gte=thirty_days_ago
    ).prefetch_related('images').order_by('-created_at')
    
    # Optional: Add a flag to show if viewing own page
    is_owner = request.user.is_authenticated and request.user.id == seller.id
    
    return render(request, 'seller_page.html', {
    'seller': seller,
    'products': products,
    'is_owner': request.user.is_authenticated and request.user.id == seller.id,
})



def login_view(request):
    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip()
        password   = request.POST.get('password', '')

        # Try username first, then email
        user = authenticate(request, username=identifier, password=password)

        if not user:
            # Maybe they typed their email — look up the username
            try:
                seller = Seller.objects.get(email__iexact=identifier)
                user = authenticate(request, username=seller.username, password=password)
            except Seller.DoesNotExist:
                pass

        if user and user.is_active:
            login(request, user)
            next_url = request.GET.get('next', '')
            return redirect(next_url or 'dashboard')

        return render(request, 'register.html', {
            'error': 'Wrong username/email or password. Try again.',
            'active_tab': 'login',
            'login_username': identifier,   # repopulate the field
        })

    return render(request, 'register.html', {'active_tab': 'login'})


@login_required
@require_http_methods(["POST"])
def update_watermark(request):
    if request.user.subscription_type == 'premium':
        request.user.watermark_enabled = 'watermark_enabled' in request.POST
        request.user.save(update_fields=['watermark_enabled'])
    return redirect('settings')

def guest_upload_view(request):
    """Homepage 'Start Uploading' — same page for everyone"""
    return render(request, 'dashboard/upload.html') 

def logout_view(request):
    logout(request)
    return redirect('home')

# Dashboard
@login_required
def dashboard(request):
    """Seller dashboard with analytics"""
    seller = request.user
    
    # Reset weekly analytics if needed
    reset_weekly_analytics_if_needed(seller)
    
    # Get products
    active_products = Product.objects.filter(
        seller=seller, 
        is_archived=False,
        is_sold_out=False
    ).prefetch_related('images')
    
    sold_out_products = Product.objects.filter(
        seller=seller,
        is_archived=False,
        is_sold_out=True
    ).prefetch_related('images')
    
    archived_products = Product.objects.filter(
        seller=seller, 
        is_archived=True
    ).prefetch_related('images')
    
    # Analytics
    total_views = seller.weekly_page_views
    whatsapp_clicks = seller.weekly_whatsapp_clicks
    
    # Most viewed product this week
    most_viewed = Product.objects.filter(
        seller=seller,
        is_archived=False
    ).order_by('-views').first()
    
    # All products for display
    all_products = Product.objects.filter(
        seller=seller
    ).prefetch_related('images').order_by('-created_at')[:50]
    
    # Generate share message for catalog
    catalog_url = request.build_absolute_uri(f'/{seller.slug}')
    share_message = f"🛍️ Check out my product catalog!\n\n{seller.business_name}\n\n{catalog_url}\n\n✨ Browse all my products anytime!"
    whatsapp_share_url = f"https://wa.me/?text={urllib.parse.quote(share_message)}"
    
    return render(request, 'dashboard/dashboard.html', {
        'products': all_products,
        'active_count': active_products.count(),
        'sold_out_count': sold_out_products.count(),
        'archived_count': archived_products.count(),
        'total_views': total_views,
        'whatsapp_clicks': whatsapp_clicks,
        'most_viewed': most_viewed,
        'product_limit': None,  # Unlimited!
        'whatsapp_share_url': whatsapp_share_url,
        'catalog_url': catalog_url,
    })
from django.views.decorators.http import require_http_methods
import traceback

from django.core.files.uploadedfile import InMemoryUploadedFile
import logging
logger = logging.getLogger(__name__)

from django.views.decorators.http import require_http_methods
import traceback


# @login_required
@require_http_methods(["GET", "POST"])
def upload_product(request):
    """Upload product - instant response"""
    
    # GET request - show upload form
    if request.method == 'GET':
        return render(request, 'dashboard/upload.html')
    
    # POST request - handle upload
    try:
        seller = request.user
        
        # Get form data
        description = request.POST.get('description', '').strip()
        price = request.POST.get('price', '').strip()
        
        # Get image URLs (already uploaded to Cloudinary by frontend)
        image_urls = request.POST.getlist('image_urls[]')
        
        # Validate
        if not image_urls:
            return JsonResponse({
                'success': False,
                'error': 'No images provided'
            }, status=400)
        
        if len(image_urls) > 10:
            return JsonResponse({
                'success': False,
                'error': 'Maximum 10 images per product'
            }, status=400)
        
        # Validate URLs are from Cloudinary
        for url in image_urls:
            if not url.startswith('https://res.cloudinary.com/'):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid image URL'
                }, status=400)
        
        # Parse price
        price_value = None
        if price:
            try:
                price_value = Decimal(price)
                if price_value < 0:
                    return JsonResponse({
                        'success': False,
                        'error': 'Price cannot be negative'
                    }, status=400)
            except (ValueError, Exception):
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid price format'
                }, status=400)
        
        # Create product (INSTANT - no upload happening)
        from products.models import Product, ProductImage
        
        product = Product.objects.create(
            seller=seller,
            description=description,
            price=price_value
        )
        
        # Save image URLs (INSTANT - just saving text)
        for index, url in enumerate(image_urls):
            ProductImage.objects.create(
                product=product,
                image_url=url,
                order=index
            )
        
        logger.info(f"✅ Product {product.id} created instantly with {len(image_urls)} images")
        
        return JsonResponse({
            'success': True,
            'message': f'Product created with {len(image_urls)} image{"s" if len(image_urls) > 1 else ""}!',
            'product_id': product.id,
            'redirect_url': '/dashboard/'
        })
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}\n{traceback.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to create product. Please try again.'
        }, status=500)

        # API Endpoints
@login_required
@require_http_methods(["POST"])
def archive_product(request, product_id):
    """Archive a product"""
    product = get_object_or_404(Product, id=product_id, seller=request.user)
    product.is_archived = True
    product.save()
    return JsonResponse({'success': True})

@login_required
@require_http_methods(["POST"])
def reactivate_product(request, product_id):
    """Reactivate an archived product"""
    product = get_object_or_404(Product, id=product_id, seller=request.user)
    product.is_archived = False
    product.is_sold_out = False  # Also mark as available
    product.save()
    return JsonResponse({'success': True})

@login_required
@require_http_methods(["POST"])
def mark_sold_out(request, product_id):
    """Mark product as sold out"""
    product = get_object_or_404(Product, id=product_id, seller=request.user)
    product.is_sold_out = True
    product.save()
    return JsonResponse({'success': True})

@login_required
@require_http_methods(["POST"])
def mark_available(request, product_id):
    """Mark product as available again"""
    product = get_object_or_404(Product, id=product_id, seller=request.user)
    product.is_sold_out = False
    product.save()
    return JsonResponse({'success': True})

@login_required
@require_http_methods(["DELETE"])
def delete_product(request, product_id):
    """Delete permanently - but we encourage sold out instead"""
    product = get_object_or_404(Product, id=product_id, seller=request.user)
    product.delete()
    return JsonResponse({'success': True})

@require_http_methods(["POST"])
def track_whatsapp_click(request, product_id):
    """Track when someone clicks WhatsApp button"""
    try:
        product = get_object_or_404(Product, id=product_id)
        product.whatsapp_clicks += 1
        product.views += 1
        product.save(update_fields=['whatsapp_clicks', 'views'])
        
        # Update seller analytics
        product.seller.weekly_whatsapp_clicks += 1
        product.seller.save(update_fields=['weekly_whatsapp_clicks'])
        
        return JsonResponse({'success': True})
    except:
        return JsonResponse({'success': False}, status=400)



@login_required
def dashboard_settings(request):
    return render(request, 'dashboard/settings.html')

@login_required
def update_profile_picture(request):
    if request.method != 'POST':
        return redirect('settings')

    seller = request.user

    # Remove picture
    if request.POST.get('remove_picture'):
        if seller.profile_picture:
            try:
                import cloudinary.uploader
                # Get the public_id from the CloudinaryResource
                public_id = seller.profile_picture.public_id
                if public_id:
                    cloudinary.uploader.destroy(public_id)
            except Exception as e:
                logger.error(f"Cloudinary delete error: {str(e)}")
            seller.profile_picture = None
            seller.save(update_fields=['profile_picture'])
        return redirect('settings')

    # URL-based upload (from frontend Cloudinary direct upload)
    if request.POST.get('profile_picture_url'):
        try:
            url = request.POST.get('profile_picture_url')
            # Extract public_id: https://res.cloudinary.com/xxx/image/upload/v123/vendopage/profiles/abc.jpg
            # → vendopage/profiles/abc
            parts = url.split('/upload/')
            if len(parts) > 1:
                path = parts[1]
                # Remove version segment (v1234567/)
                path_parts = path.split('/')
                if path_parts[0].startswith('v') and path_parts[0][1:].isdigit():
                    path_parts = path_parts[1:]
                public_id = '/'.join(path_parts).rsplit('.', 1)[0]
            else:
                public_id = url

            seller.profile_picture = public_id
            seller.save(update_fields=['profile_picture'])
            return JsonResponse({'success': True})
        except Exception as e:
            logger.error(f"Profile picture URL save error: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return redirect('settings')

@login_required
def update_business_info(request):
    """Update business information"""
    if request.method == 'POST':
        seller = request.user
        
        business_name = request.POST.get('business_name', '').strip()
        bio = request.POST.get('bio', '').strip()
        category = request.POST.get('category')
        whatsapp_number = request.POST.get('whatsapp_number', '').strip()
        
        # Validate
        if not business_name:
            messages.error(request, 'Business name is required')
            return redirect('settings')
        
        if not whatsapp_number:
            messages.error(request, 'WhatsApp number is required')
            return redirect('settings')
        
        # Check if phone number is already taken by another user
        if Seller.objects.filter(whatsapp_number=whatsapp_number).exclude(id=seller.id).exists():
            messages.error(request, 'This WhatsApp number is already registered')
            return redirect('settings')
        
        # Update
        seller.business_name = business_name
        seller.bio = bio
        seller.category = category
        seller.whatsapp_number = whatsapp_number
        seller.save()
        
        # messages.success(request, 'Business information updated!')
    
    return redirect('settings')

@login_required
def update_account(request):
    """Update email address"""
    if request.method == 'POST':
        seller = request.user
        email = request.POST.get('email', '').strip().lower()
        
        if not email:
            messages.error(request, 'Email is required')
            return redirect('settings')
        
        # Validate email format
        if '@' not in email or '.' not in email.split('@')[1]:
            messages.error(request, 'Invalid email format')
            return redirect('settings')
        
        # Check if email is already taken by another user
        if Seller.objects.filter(email__iexact=email).exclude(id=seller.id).exists():
            messages.error(request, 'This email is already registered')
            return redirect('settings')
        
        seller.email = email
        seller.save()
        # messages.success(request, 'Email updated successfully!')
    
    return redirect('settings')

@login_required
def change_password(request):
    """Change user password"""
    if request.method == 'POST':
        seller = request.user
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        # Verify current password
        if not seller.check_password(current_password):
            messages.error(request, 'Current password is incorrect')
            return redirect('settings')
        
        # Check new passwords match
        if new_password != confirm_password:
            messages.error(request, 'New passwords do not match')
            return redirect('settings')
        
        # Validate new password
        if len(new_password) < 6:
            messages.error(request, 'Password must be at least 6 characters')
            return redirect('settings')
        
        try:
            validate_password(new_password, seller)
        except ValidationError as e:
            messages.error(request, ' '.join(e.messages))
            return redirect('settings')
        
        # Update password
        seller.set_password(new_password)
        seller.save()
        
        # Keep user logged in after password change
        update_session_auth_hash(request, seller)
        
        # messages.success(request, 'Password changed successfully!')
    
    return redirect('settings')




logger = logging.getLogger(__name__)

def forgot_password(request):
    """Request password reset - sends 5-digit code via email"""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()

        try:
            seller = Seller.objects.get(email__iexact=email)

            # Generate 5-digit code
            reset_code = ''.join(random.choices(string.digits, k=5))

            # Store in session
            request.session['reset_code'] = reset_code
            request.session['reset_email'] = email
            request.session['reset_code_expires'] = (
                timezone.now() + timedelta(minutes=10)
            ).isoformat()

            # Send via Brevo
            email_sent = send_password_reset_email(
                to_email=email,
                business_name=seller.business_name,
                reset_code=reset_code
            )

            if not email_sent:
                messages.error(request, 'Failed to send reset email. Please try again.')
                return render(request, 'auth/forgot_password.html')

        except Seller.DoesNotExist:
            pass  # Don't reveal whether email exists

        except Exception as e:
            logger.error(f"Password reset failed: {str(e)}")
            messages.error(request, f'Something went wrong. Please try again.')
            return render(request, 'auth/forgot_password.html')

        # Redirect whether email exists or not (security)
        return redirect('verify_reset_code')

    return render(request, 'auth/forgot_password.html')


def verify_reset_code(request):
    """Verify the 5-digit code"""
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        
        stored_code = request.session.get('reset_code')
        expires = request.session.get('reset_code_expires')
        
        if not stored_code or not expires:
            messages.error(request, 'No reset code found. Please request a new one.')
            return redirect('forgot_password')
        
        # Check if expired
        expires_dt = datetime.fromisoformat(expires)
        if timezone.now() > expires_dt:
            del request.session['reset_code']
            del request.session['reset_code_expires']
            messages.error(request, 'Code expired. Please request a new one.')
            return redirect('forgot_password')
        
        # Check if code matches
        if code == stored_code:
            # Generate token for password reset
            reset_token = uuid.uuid4().hex
            request.session['reset_token'] = reset_token
            request.session['reset_token_expires'] = (timezone.now() + timedelta(minutes=30)).isoformat()
            
            return redirect('reset_password', token=reset_token)
        else:
            messages.error(request, 'Invalid code. Please try again.')
    
    return render(request, 'auth/verify_code.html')


def reset_password(request, token):
    """Reset password with new one"""
    from datetime import datetime
    
    stored_token = request.session.get('reset_token')
    expires = request.session.get('reset_token_expires')
    email = request.session.get('reset_email')
    
    if not stored_token or token != stored_token or not expires or not email:
        messages.error(request, 'Invalid or expired reset link.')
        return redirect('forgot_password')
    
    expires_dt = datetime.fromisoformat(expires)
    if timezone.now() > expires_dt:
        messages.error(request, 'Reset link expired. Please request a new one.')
        return redirect('forgot_password')
    
    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if new_password != confirm_password:
            messages.error(request, 'Passwords do not match')
            return render(request, 'auth/reset_password.html')
        
        if len(new_password) < 6:
            messages.error(request, 'Password must be at least 6 characters')
            return render(request, 'auth/reset_password.html')
        
        try:
            seller = Seller.objects.get(email__iexact=email)
            seller.set_password(new_password)
            seller.save()
            
            # Clear session
            for key in ['reset_code', 'reset_email', 'reset_code_expires', 'reset_token', 'reset_token_expires']:
                if key in request.session:
                    del request.session[key]
            
            messages.success(request, '✓ Password reset successful! Please login with your new password.')
            return redirect('login')
            
        except Seller.DoesNotExist:
            messages.error(request, 'User not found.')
            return redirect('forgot_password')
    
    return render(request, 'auth/reset_password.html')













# sellers/views.py - Add these admin views

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum, Q
from datetime import timedelta

@staff_member_required
def admin_dashboard(request):
    """Custom admin dashboard"""
    
    # Platform Statistics (exclude staff/superusers)
    total_sellers = Seller.objects.filter(
        is_active=True,
        is_staff=False,
        is_superuser=False
    ).count()
    total_products = Product.objects.filter(is_archived=False).count()
    total_page_views = Seller.objects.filter(
        is_staff=False,
        is_superuser=False
    ).aggregate(Sum('total_page_views'))['total_page_views__sum'] or 0
    total_whatsapp_clicks = Seller.objects.filter(
        is_staff=False,
        is_superuser=False
    ).aggregate(Sum('weekly_whatsapp_clicks'))['weekly_whatsapp_clicks__sum'] or 0
    
    # Recent Activity (only sellers, not staff)
    recent_sellers = Seller.objects.filter(
        is_active=True,
        is_staff=False,
        is_superuser=False
    ).order_by('-created_at')[:10]
    recent_products = Product.objects.filter(
        is_archived=False
    ).select_related('seller').order_by('-created_at')[:10]
    
    # Top Performers (only sellers)
    top_sellers_by_views = Seller.objects.filter(
        is_active=True,
        is_staff=False,
        is_superuser=False
    ).order_by('-weekly_page_views')[:10]
    top_sellers_by_products = Seller.objects.filter(
        is_active=True,
        is_staff=False,
        is_superuser=False
    ).annotate(
        product_count=Count('products', filter=Q(products__is_archived=False))
    ).order_by('-product_count')[:10]
    
    # Subscription Breakdown (only sellers)
    subscription_stats = Seller.objects.filter(
        is_staff=False,
        is_superuser=False
    ).values('subscription_type').annotate(count=Count('id'))
    
    # Revenue Estimates
    premium_count = Seller.objects.filter(
        subscription_type='premium',
        is_staff=False,
        is_superuser=False
    ).count()
    monthly_revenue = premium_count * 2000
    
    context = {
        'total_sellers': total_sellers,
        'total_products': total_products,
        'total_page_views': total_page_views,
        'total_whatsapp_clicks': total_whatsapp_clicks,
        'recent_sellers': recent_sellers,
        'recent_products': recent_products,
        'top_sellers_by_views': top_sellers_by_views,
        'top_sellers_by_products': top_sellers_by_products,
        'subscription_stats': subscription_stats,
        'premium_count': premium_count,
        'monthly_revenue': monthly_revenue,
    }
    
    return render(request, 'admin_dashboard/dashboard.html', context)


@staff_member_required
def admin_sellers(request):
    """Manage sellers (excludes staff/superusers)"""
    sellers = Seller.objects.filter(
        is_active=True,
        is_staff=False,
        is_superuser=False
    ).annotate(
        product_count=Count('products', filter=Q(products__is_archived=False))
    ).order_by('-created_at')
    
    # Filters
    subscription_filter = request.GET.get('subscription')
    if subscription_filter:
        sellers = sellers.filter(subscription_type=subscription_filter)
    
    search = request.GET.get('search')
    if search:
        sellers = sellers.filter(
            Q(business_name__icontains=search) |
            Q(username__icontains=search) |
            Q(email__icontains=search)
        )
    
    return render(request, 'admin_dashboard/sellers.html', {'sellers': sellers})


@staff_member_required
def admin_seller_detail(request, seller_id):
    """View/edit seller details"""
    seller = get_object_or_404(Seller, id=seller_id)
    products = Product.objects.filter(seller=seller).order_by('-created_at')[:20]
    
    # Fix seller slug if missing
    if not seller.slug:
        seller.save()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'change_subscription':
            new_type = request.POST.get('subscription_type')
            seller.subscription_type = new_type
            if new_type == 'premium':
                seller.subscription_expires = timezone.now() + timedelta(days=30)
            seller.save()
            messages.success(request, f'Subscription changed to {new_type}')
        
        elif action == 'toggle_featured':
            seller.is_featured = not seller.is_featured
            seller.save()
            status = 'featured' if seller.is_featured else 'unfeatured'
            messages.success(request, f'Seller is now {status}')
        
        elif action == 'deactivate':
            seller.is_active = False
            seller.save()
            messages.warning(request, f'Seller {seller.business_name} has been deactivated')
        
        return redirect('admin_seller_detail', seller_id=seller_id)
    
    return render(request, 'admin_dashboard/seller_detail.html', {
        'seller': seller,
        'products': products
    })



@staff_member_required
def admin_products(request):
    """Manage all products"""
    products = Product.objects.select_related('seller').order_by('-created_at')
    
    # Filters
    status = request.GET.get('status')
    if status == 'sold_out':
        products = products.filter(is_sold_out=True)
    elif status == 'archived':
        products = products.filter(is_archived=True)
    elif status == 'active':
        products = products.filter(is_archived=False, is_sold_out=False)
    
    return render(request, 'admin_dashboard/products.html', {'products': products[:100]})


@staff_member_required
def admin_analytics(request):
    """Platform analytics"""
    
    # Time-based analytics
    last_7_days = timezone.now() - timedelta(days=7)
    last_30_days = timezone.now() - timedelta(days=30)
    
    new_sellers_7d = Seller.objects.filter(created_at__gte=last_7_days).count()
    new_sellers_30d = Seller.objects.filter(created_at__gte=last_30_days).count()
    
    new_products_7d = Product.objects.filter(created_at__gte=last_7_days).count()
    new_products_30d = Product.objects.filter(created_at__gte=last_30_days).count()
    
    # Category breakdown
    category_stats = Seller.objects.values('category').annotate(
        count=Count('id')
    ).order_by('-count')
    
    context = {
        'new_sellers_7d': new_sellers_7d,
        'new_sellers_30d': new_sellers_30d,
        'new_products_7d': new_products_7d,
        'new_products_30d': new_products_30d,
        'category_stats': category_stats,
    }
    
    return render(request, 'admin_dashboard/analytics.html', context)









# ==========================================
# STEP 5: Update sellers/views.py
# ==========================================



from .flutterwave import FlutterwavePayment

@login_required
def subscription(request):
    """Subscription page"""
    return render(request, 'dashboard/subscription.html', {
        'current_subscription': request.user.subscription_type,
        'subscription_expires': request.user.subscription_expires,
    })

@login_required
def upgrade_to_premium(request):
    """Initialize premium subscription payment"""
    if request.method == 'POST':
        seller = request.user
        
        # Generate unique transaction reference
        tx_ref = f"VDP-{seller.id}-{uuid.uuid4().hex[:8]}"
        
        # Premium price (₦2,000/month)
        amount = Decimal('2000.00')
        
        # Initialize Flutterwave payment
        flw = FlutterwavePayment()
        redirect_url = request.build_absolute_uri('/payment/verify/')
        
        result = flw.initialize_payment(
            email=seller.email,
            amount=amount,
            tx_ref=tx_ref,
            redirect_url=redirect_url,
            customer_name=seller.business_name
        )
        
        if result.get('status') == 'success':
            # Store transaction reference in session
            request.session['tx_ref'] = tx_ref
            request.session['upgrading_to_premium'] = True
            
            # Redirect to Flutterwave payment page
            payment_link = result['data']['link']
            return redirect(payment_link)
        else:
            messages.error(request, 'Payment initialization failed. Please try again.')
            return redirect('subscription')
    
    return redirect('subscription')

@login_required
def verify_payment(request):
    """Verify payment after Flutterwave redirect"""
    status = request.GET.get('status')
    tx_ref = request.GET.get('tx_ref')
    transaction_id = request.GET.get('transaction_id')
    
    # Check if this was a premium upgrade
    if not request.session.get('upgrading_to_premium'):
        messages.error(request, 'Invalid payment session')
        return redirect('subscription')
    
    # Verify the transaction
    flw = FlutterwavePayment()
    result = flw.verify_payment(transaction_id)
    
    if result.get('status') == 'success':
        data = result.get('data', {})
        
        # Check if payment was successful
        if data.get('status') == 'successful' and data.get('tx_ref') == tx_ref:
            # Upgrade user to premium
            seller = request.user
            seller.subscription_type = 'premium'
            seller.subscription_expires = timezone.now() + timedelta(days=30)
            seller.save()
            
            # Clear session
            request.session.pop('upgrading_to_premium', None)
            request.session.pop('tx_ref', None)
            
            messages.success(request, '🎉 Welcome to Premium! Your subscription is now active.')
            return redirect('dashboard')
        else:
            messages.error(request, 'Payment verification failed. Please contact support.')
            return redirect('subscription')
    else:
        messages.error(request, 'Payment verification failed. Please try again.')
        return redirect('subscription')

@csrf_exempt
@require_http_methods(["POST"])
def flutterwave_webhook(request):
    """Handle Flutterwave webhook for payment notifications"""
    try:
        # Get signature from headers
        signature = request.headers.get('verif-hash')
        
        # Verify webhook signature
        flw = FlutterwavePayment()
        payload = request.body.decode('utf-8')
        
        if not signature or not flw.verify_webhook_signature(signature, payload):
            return JsonResponse({'status': 'error', 'message': 'Invalid signature'}, status=400)
        
        # Process the webhook
        data = json.loads(payload)
        
        # Handle successful payment
        if data.get('event') == 'charge.completed' and data.get('data', {}).get('status') == 'successful':
            tx_ref = data['data'].get('tx_ref')
            
            # You can add additional processing here
            # For example, sending confirmation emails
            
            return JsonResponse({'status': 'success'})
        
        return JsonResponse({'status': 'received'})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)




# ── 1. CHECK USERNAME AVAILABILITY ──────────────────────────
def check_username(request):
    """
    GET /api/check-username/?u=chioma
    Returns JSON {available: true/false}
    Used by the homepage entry modal for live feedback.
    """
    u = request.GET.get('u', '').strip().lower()
    if not u or len(u) < 2:
        return JsonResponse({'available': False, 'error': 'Too short'})
    # Only allow letters, numbers, underscores
    import re
    if not re.match(r'^[a-z0-9_]+$', u):
        return JsonResponse({'available': False, 'error': 'Invalid characters'})
    taken = Seller.objects.filter(username__iexact=u).exists()
    return JsonResponse({'available': not taken})
 
 
# ── 2. GUEST INIT ────────────────────────────────────────────
@require_http_methods(["POST"])
def guest_init(request):
    """
    POST /api/guest-init/
    Body: {business_name, username}
 
    Saves the guest's intended business name and username to the
    session so the upload page can show them, and the register
    page can pre-fill them.
 
    Returns {success: true} or {success: false, error: "..."}
    """
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)
 
    business_name = data.get('business_name', '').strip()
    username      = data.get('username', '').strip().lower()
 
    if not business_name or not username:
        return JsonResponse({'success': False, 'error': 'Both fields required'}, status=400)
 
    import re
    if not re.match(r'^[a-z0-9_]+$', username):
        return JsonResponse({'success': False, 'error': 'Username can only use letters, numbers, underscores'}, status=400)
 
    # Check username isn't already taken
    if Seller.objects.filter(username__iexact=username).exists():
        return JsonResponse({'success': False, 'error': f'"{username}" is already taken. Try another.'})
 
    # Store in session — these travel with the user through upload → preview → register
    request.session['guest_business_name'] = business_name
    request.session['guest_username']      = username
    # guest_key is created later when they actually upload products
    request.session.modified = True
 
    return JsonResponse({'success': True})
 
 
# ── 3. UPLOAD PRODUCTS BATCH (guest + auth) ──────────────────
@require_http_methods(["POST"])
def upload_products_batch(request):
    """
    Handles batch product creation for BOTH authenticated sellers
    and guests who have gone through the entry modal.
    """
    try:
        products_data = json.loads(request.POST.get('products', '[]'))
 
        if not products_data:
            return JsonResponse({'success': False, 'error': 'No products provided'}, status=400)
        if len(products_data) > 50:
            return JsonResponse({'success': False, 'error': 'Maximum 50 products per batch'}, status=400)
 
        # ── GUEST FLOW ───────────────────────────────────────
        if not request.user.is_authenticated:
            guest_key = request.session.get('guest_key')
            if not guest_key:
                guest_key = uuid.uuid4().hex
                request.session['guest_key'] = guest_key
                request.session.modified = True
 
        created = []
 
        for item in products_data:
            valid_urls = [
                url for url in item.get('image_urls', [])
                if isinstance(url, str) and url.startswith('https://res.cloudinary.com/')
            ]
            if not valid_urls:
                continue
 
            price_value = None
            raw_price = str(item.get('price', '')).strip()
            if raw_price:
                try:
                    price_value = Decimal(raw_price)
                    if price_value < 0:
                        price_value = None
                except Exception:
                    price_value = None
 
            product = Product.objects.create(
                seller      = request.user if request.user.is_authenticated else None,
                guest_key   = guest_key if not request.user.is_authenticated else None,
                description = str(item.get('description', '')).strip(),
                price       = price_value,
            )
 
            for index, url in enumerate(valid_urls[:10]):
                ProductImage.objects.create(
                    product   = product,
                    image_url = url,
                    order     = index,
                )
 
            created.append(product.id)
 
        if not created:
            return JsonResponse({'success': False, 'error': 'No valid products to save'}, status=400)
 
        if request.user.is_authenticated:
            return JsonResponse({
                'success': True,
                'created': len(created),
                'redirect_url': '/dashboard/',
            })
        else:
            return JsonResponse({
                'success': True,
                'created': len(created),
                'redirect_url': f'/preview/{guest_key}/',
            })
 
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid data format'}, status=400)
    except Exception as e:
        logger.error(f"Batch upload error: {str(e)}\n{traceback.format_exc()}")
        return JsonResponse({'success': False, 'error': 'Failed to save. Please try again.'}, status=500)
 
 
# ── 4. GUEST STORE PREVIEW ───────────────────────────────────
def guest_store_preview(request, guest_key):
    """
    /preview/<guest_key>/
    Shows real DB products for the guest, renders seller_page.html
    look-alike with a registration modal.
    Authenticated users are bounced to dashboard.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
 
    products = Product.objects.filter(
        guest_key = guest_key,
        seller    = None,
        is_archived = False,
    ).prefetch_related('images').order_by('created_at')
 
    if not products.exists():
        return redirect('upload_product')
 
    business_name = request.session.get('guest_business_name', 'Your Store')
    username      = request.session.get('guest_username', '')
 
    return render(request, 'guest_seller_page.html', {
        'products':      products,
        'guest_key':     guest_key,
        'business_name': business_name,
        'username':      username,
    })
 




 
# ── 5. REGISTER VIEW (updated — no username field in form) ───
def register_view(request):
    if request.method == 'POST':
        # Pull pre-chosen username from session (set in guest_init)
        # Fall back to a POST field for direct registration without guest flow
        username = (
            request.session.get('guest_username') or
            request.POST.get('username', '')
        ).strip().lower()

        if not username and business_name:
            import re
            username = re.sub(r'[^a-z0-9]', '_', business_name.lower()).strip('_')[:28]

        # If generated username is taken, append a short suffix
        if username and Seller.objects.filter(username__iexact=username).exists():
            if not request.session.get('guest_username'):
                # Only auto-fix if not from modal (modal should have pre-checked)
                import random
                username = f"{username[:25]}_{random.randint(10,99)}"
 
        business_name   = (
            request.session.get('guest_business_name') or
            request.POST.get('business_name', '')
        ).strip()
 
        email           = request.POST.get('email', '').strip().lower()
        password        = request.POST.get('password', '')
        whatsapp_number = request.POST.get('whatsapp_number', '').strip()
        country_code    = request.POST.get('country_code', '+234').strip()
        currency_code   = request.POST.get('currency_code', 'NGN').strip()
        currency_symbol = request.POST.get('currency_symbol', '₦').strip()
        category        = request.POST.get('category', 'other')
 
        if country_code and not whatsapp_number.startswith('+'):
            full_whatsapp = country_code + whatsapp_number
        else:
            full_whatsapp = whatsapp_number
 
        errors = []
 
        if not all([username, email, password, business_name, whatsapp_number]):
            errors.append('All fields are required')
        if username and Seller.objects.filter(username__iexact=username).exists():
            # Username was reserved in guest_init but someone else grabbed it in the meantime
            errors.append(f'Username "{username}" was just taken. Please go back and choose another.')
        if email and Seller.objects.filter(email__iexact=email).exists():
            errors.append(f'Email "{email}" is already registered.')
        if full_whatsapp and Seller.objects.filter(whatsapp_number=full_whatsapp).exists():
            errors.append('WhatsApp number is already registered.')
        if email and ('@' not in email or '.' not in email.split('@')[1]):
            errors.append('Please enter a valid email address')
        if password and len(password) < 6:
            errors.append('Password must be at least 6 characters long')
 
        if errors:
            return render(request, 'register.html', {
                'errors': errors, 'active_tab': 'register',
                'email': email,
                'business_name': business_name,
                'username': username,
                'whatsapp_number': whatsapp_number,
                'category': category,
            })
 
        try:
            seller = Seller.objects.create_user(
                username        = username,
                email           = email,
                password        = password,
                business_name   = business_name,
                whatsapp_number = full_whatsapp,
                category        = category,
                country_code    = country_code,
                currency_code   = currency_code,
                currency_symbol = currency_symbol,
                subscription_type = 'free',
            )
 
            # ── TRANSFER GUEST PRODUCTS ──────────────────────
            guest_key = request.session.get('guest_key')
            if guest_key:
                transferred = Product.objects.filter(
                    guest_key = guest_key,
                    seller    = None,
                ).update(seller=seller, guest_key=None)
                logger.info(f"Transferred {transferred} guest products → seller {seller.id}")
 
            # Clear guest session data
            for key in ['guest_key', 'guest_username', 'guest_business_name']:
                request.session.pop(key, None)
 
            login(request, seller)
            # Send straight to dashboard — their products are already there
            return redirect('dashboard')
 
        except IntegrityError as e:
            err = str(e)
            if 'username' in err:
                errors.append('Username is already taken')
            elif 'email' in err:
                errors.append('Email is already registered')
            elif 'whatsapp' in err:
                errors.append('WhatsApp number is already registered')
            else:
                errors.append('Registration failed. Please try again.')
 
            return render(request, 'register.html', {
                'errors': errors, 'active_tab': 'register',
                'email': email,
                'business_name': business_name,
                'username': username,
                'whatsapp_number': whatsapp_number,
                'category': category,
            })
 
    return render(request, 'register.html', {'active_tab': 'register'})