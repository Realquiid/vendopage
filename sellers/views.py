# sellers/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Sum
from django.utils import timezone
from datetime import timedelta
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
from decimal import Decimal
import uuid
import json

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

def seller_page(request, slug):
    """Individual seller's product page with analytics"""
    seller = get_object_or_404(Seller, slug=slug, is_active=True)
    
    # Track page view
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
    
    return render(request, 'seller_page.html', {
        'seller': seller,
        'products': products
    })


def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip().lower()  # Normalize to lowercase
        password = request.POST.get('password', '')
        business_name = request.POST.get('business_name', '').strip()
        whatsapp_number = request.POST.get('whatsapp_number', '').strip()
        category = request.POST.get('category', '')
        
        errors = []
        
        # Validate required fields
        if not all([username, email, password, business_name, whatsapp_number, category]):
            errors.append('All fields are required')
        
        # Check username uniqueness (case-insensitive)
        if username and Seller.objects.filter(username__iexact=username).exists():
            errors.append(f'Username "{username}" is already taken. Please choose another.')
        
        # Check email uniqueness (case-insensitive)
        if email and Seller.objects.filter(email__iexact=email).exists():
            errors.append(f'Email "{email}" is already registered. Please use another email or login.')
        
        # Check phone number uniqueness
        if whatsapp_number and Seller.objects.filter(whatsapp_number=whatsapp_number).exists():
            errors.append(f'WhatsApp number "{whatsapp_number}" is already registered. Please use another number.')
        
        # Validate email format
        if email and ('@' not in email or '.' not in email.split('@')[1]):
            errors.append('Please enter a valid email address')
        
        # Validate password length
        if password and len(password) < 6:
            errors.append('Password must be at least 6 characters long')
        
        # Validate username format (alphanumeric and underscores only)
        if username and not username.replace('_', '').isalnum():
            errors.append('Username can only contain letters, numbers, and underscores')
        
        if errors:
            return render(request, 'register.html', {
                'errors': errors,
                'username': username,
                'email': email,
                'business_name': business_name,
                'whatsapp_number': whatsapp_number,
                'category': category,
            })
        
        try:
            # Create the seller with unlimited products
            seller = Seller.objects.create_user(
                username=username,
                email=email,
                password=password,
                business_name=business_name,
                whatsapp_number=whatsapp_number,
                category=category,
                subscription_type='free'  # Everyone gets free (which is unlimited!)
            )
            
            # Log them in
            login(request, seller)
            messages.success(request, f'🎉 Welcome {business_name}! You now have UNLIMITED products to list!')
            return redirect('dashboard')
            
        except IntegrityError as e:
            error_message = str(e)
            if 'username' in error_message:
                errors.append('Username is already taken')
            elif 'email' in error_message:
                errors.append('Email is already registered')
            elif 'whatsapp_number' in error_message:
                errors.append('WhatsApp number is already registered')
            else:
                errors.append('Registration failed. Please check your details and try again.')
            
            return render(request, 'register.html', {
                'errors': errors,
                'username': username,
                'email': email,
                'business_name': business_name,
                'whatsapp_number': whatsapp_number,
                'category': category,
            })
    
    return render(request, 'register.html')


def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        
        if user:
            login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'login.html', {'error': 'Invalid credentials'})
    
    return render(request, 'login.html')

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

@login_required
def upload_product(request):
    """Upload product - NO LIMIT!"""
    if request.method == 'POST':
        seller = request.user
        
        # NO MORE LIMIT CHECK - Everyone gets unlimited!
        
        # Get form data
        description = request.POST.get('description', '')
        price = request.POST.get('price')
        images = request.FILES.getlist('images')
        
        if not images:
            return JsonResponse({'error': 'Please upload at least one image'}, status=400)
        
        if len(images) > 10:
            return JsonResponse({'error': 'Maximum 10 images per product'}, status=400)
        
        # Create product
        product = Product.objects.create(
            seller=seller,
            description=description,
            price=price if price else None
        )
        
        # Create images
        for index, image in enumerate(images):
            ProductImage.objects.create(
                product=product,
                image=image,
                order=index
            )
        
        return JsonResponse({
            'success': True, 
            'message': f'Product created with {len(images)} images',
            'product_id': product.id
        })
    
    return render(request, 'dashboard/upload.html')

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
def settings(request):
    """Settings page"""
    return render(request, 'dashboard/settings.html')

@login_required
def update_profile_picture(request):
    """Update or remove profile picture"""
    if request.method == 'POST':
        seller = request.user
        
        # Remove picture
        if request.POST.get('remove_picture'):
            if seller.profile_picture:
                # Delete old file
                if os.path.isfile(seller.profile_picture.path):
                    os.remove(seller.profile_picture.path)
                seller.profile_picture = None
                seller.save()
                messages.success(request, 'Profile picture removed')
            return redirect('settings')
        
        # Upload new picture
        if 'profile_picture' in request.FILES:
            picture = request.FILES['profile_picture']
            
            # Validate file size (max 5MB)
            if picture.size > 5 * 1024 * 1024:
                messages.error(request, 'Image too large. Maximum size is 5MB.')
                return redirect('settings')
            
            # Validate file type
            allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
            if picture.content_type not in allowed_types:
                messages.error(request, 'Invalid file type. Please upload JPG, PNG, or GIF.')
                return redirect('settings')
            
            try:
                # Open and verify image
                img = Image.open(picture)
                img.verify()
                
                # Delete old picture if exists
                if seller.profile_picture:
                    if os.path.isfile(seller.profile_picture.path):
                        os.remove(seller.profile_picture.path)
                
                # Save new picture
                seller.profile_picture = picture
                seller.save()
                messages.success(request, 'Profile picture updated!')
                
            except Exception as e:
                messages.error(request, 'Invalid image file. Please try another.')
                return redirect('settings')
    
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
        
        messages.success(request, 'Business information updated!')
    
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
        messages.success(request, 'Email updated successfully!')
    
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
        
        messages.success(request, 'Password changed successfully!')
    
    return redirect('settings')































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

