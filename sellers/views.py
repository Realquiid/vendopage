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
from sellers.email import (
    send_password_reset_email,
    send_welcome_email,
    send_first_product_email,
    send_first_whatsapp_click_email,
)
import random
import string
import logging
import traceback

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def reset_weekly_analytics_if_needed(seller):
    """Reset weekly stats every 7 days"""
    now = timezone.now()
    if (now - seller.last_analytics_reset).days >= 7:
        seller.weekly_page_views = 0
        seller.weekly_whatsapp_clicks = 0
        seller.last_analytics_reset = now
        seller.save()


def _store_url(seller):
    return f'https://vendopage.com/{seller.slug}'


# ─────────────────────────────────────────────
# PUBLIC PAGES
# ─────────────────────────────────────────────
def about(request):
    return render(request, 'about.html')

def privacy(request):
    return render(request, 'privacy.html')

def terms(request):
    return render(request, 'terms.html')

def contact(request):
    return render(request, 'contact.html')


def home(request):
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
    ).filter(product_count__gte=5).order_by('-product_count')[:4]

    sellers = Seller.objects.filter(
        is_active=True,
        is_staff=False,
        is_superuser=False
    ).annotate(
        product_count=Count('products', filter=Q(
            products__is_archived=False,
            products__is_sold_out=False
        ))
    ).filter(product_count__gte=5).exclude(
        id__in=featured_sellers.values_list('id', flat=True)
    ).order_by('-product_count')[:20]

    return render(request, 'home.html', {
        'featured_sellers': featured_sellers,
        'sellers': sellers,
    })


def seller_page(request, slug):
    seller = get_object_or_404(Seller, slug=slug, is_active=True)

    if not request.user.is_authenticated or request.user.id != seller.id:
        seller.total_page_views += 1
        seller.weekly_page_views += 1
        seller.save(update_fields=['total_page_views', 'weekly_page_views'])

    thirty_days_ago = timezone.now() - timedelta(days=30)
    products = Product.objects.filter(
        seller=seller,
        is_archived=False,
        created_at__gte=thirty_days_ago
    ).prefetch_related('images').order_by('-created_at')

    return render(request, 'seller_page.html', {
        'seller': seller,
        'products': products,
        'is_owner': request.user.is_authenticated and request.user.id == seller.id,
    })


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────
def login_view(request):
    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(request, username=identifier, password=password)

        if not user:
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
            'login_username': identifier,
        })

    return render(request, 'register.html', {'active_tab': 'login'})


def logout_view(request):
    logout(request)
    return redirect('home')


def guest_upload_view(request):
    return render(request, 'dashboard/upload.html')


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────
@login_required
def dashboard(request):
    seller = request.user
    reset_weekly_analytics_if_needed(seller)

    active_products = Product.objects.filter(seller=seller, is_archived=False, is_sold_out=False).prefetch_related('images')
    sold_out_products = Product.objects.filter(seller=seller, is_archived=False, is_sold_out=True).prefetch_related('images')
    archived_products = Product.objects.filter(seller=seller, is_archived=True).prefetch_related('images')
    most_viewed = Product.objects.filter(seller=seller, is_archived=False).order_by('-views').first()
    all_products = Product.objects.filter(seller=seller).prefetch_related('images').order_by('-created_at')[:50]

    catalog_url = request.build_absolute_uri(f'/{seller.slug}')
    share_message = f"🛍️ Check out my product catalog!\n\n{seller.business_name}\n\n{catalog_url}\n\n✨ Browse all my products anytime!"
    whatsapp_share_url = f"https://wa.me/?text={urllib.parse.quote(share_message)}"

    return render(request, 'dashboard/dashboard.html', {
        'products': all_products,
        'active_count': active_products.count(),
        'sold_out_count': sold_out_products.count(),
        'archived_count': archived_products.count(),
        'total_views': seller.weekly_page_views,
        'whatsapp_clicks': seller.weekly_whatsapp_clicks,
        'most_viewed': most_viewed,
        'product_limit': None,
        'whatsapp_share_url': whatsapp_share_url,
        'catalog_url': catalog_url,
    })


# ─────────────────────────────────────────────
# UPLOAD PRODUCT (single)
# ─────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
def upload_product(request):
    if request.method == 'GET':
        return render(request, 'dashboard/upload.html')

    try:
        seller = request.user
        description = request.POST.get('description', '').strip()
        price = request.POST.get('price', '').strip()
        image_urls = request.POST.getlist('image_urls[]')

        if not image_urls:
            return JsonResponse({'success': False, 'error': 'No images provided'}, status=400)
        if len(image_urls) > 10:
            return JsonResponse({'success': False, 'error': 'Maximum 10 images per product'}, status=400)

        for url in image_urls:
            if not url.startswith('https://res.cloudinary.com/'):
                return JsonResponse({'success': False, 'error': 'Invalid image URL'}, status=400)

        price_value = None
        if price:
            try:
                price_value = Decimal(price)
                if price_value < 0:
                    return JsonResponse({'success': False, 'error': 'Price cannot be negative'}, status=400)
            except Exception:
                return JsonResponse({'success': False, 'error': 'Invalid price format'}, status=400)

        product = Product.objects.create(seller=seller, description=description, price=price_value)
        for index, url in enumerate(image_urls):
            ProductImage.objects.create(product=product, image_url=url, order=index)

        logger.info(f"✅ Product {product.id} created with {len(image_urls)} images")
        return JsonResponse({'success': True, 'product_id': product.id, 'redirect_url': '/dashboard/'})

    except Exception as e:
        logger.error(f"Upload error: {str(e)}\n{traceback.format_exc()}")
        return JsonResponse({'success': False, 'error': 'Failed to create product.'}, status=500)


# ─────────────────────────────────────────────
# PRODUCT ACTIONS
# ─────────────────────────────────────────────
@login_required
@require_http_methods(["POST"])
def archive_product(request, product_id):
    product = get_object_or_404(Product, id=product_id, seller=request.user)
    product.is_archived = True
    product.save()
    return JsonResponse({'success': True})


@login_required
@require_http_methods(["POST"])
def reactivate_product(request, product_id):
    product = get_object_or_404(Product, id=product_id, seller=request.user)
    product.is_archived = False
    product.is_sold_out = False
    product.save()
    return JsonResponse({'success': True})


@login_required
@require_http_methods(["POST"])
def mark_sold_out(request, product_id):
    product = get_object_or_404(Product, id=product_id, seller=request.user)
    product.is_sold_out = True
    product.save()
    return JsonResponse({'success': True})


@login_required
@require_http_methods(["POST"])
def mark_available(request, product_id):
    product = get_object_or_404(Product, id=product_id, seller=request.user)
    product.is_sold_out = False
    product.save()
    return JsonResponse({'success': True})


@login_required
@require_http_methods(["DELETE"])
def delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id, seller=request.user)
    product.delete()
    return JsonResponse({'success': True})


@require_http_methods(["POST"])
def track_whatsapp_click(request, product_id):
    """
    Track WhatsApp click.
    Sends 'first click' email when seller's total lifetime clicks hit exactly 1.
    """
    try:
        product = get_object_or_404(Product, id=product_id)
        product.whatsapp_clicks += 1
        product.views += 1
        product.save(update_fields=['whatsapp_clicks', 'views'])

        seller = product.seller
        seller.weekly_whatsapp_clicks += 1
        seller.save(update_fields=['weekly_whatsapp_clicks'])

        # Fire first-click email on the very first ever WhatsApp click
        total_clicks = Product.objects.filter(seller=seller).aggregate(
            total=Sum('whatsapp_clicks')
        )['total'] or 0
        if total_clicks == 1:
            try:
                send_first_whatsapp_click_email(
                    to_email=seller.email,
                    business_name=seller.business_name,
                    store_url=_store_url(seller),
                )
            except Exception as e:
                logger.error(f"First WA click email failed: {e}")

        return JsonResponse({'success': True})
    except Exception:
        return JsonResponse({'success': False}, status=400)


# ─────────────────────────────────────────────
# SETTINGS
# ─────────────────────────────────────────────
@login_required
def dashboard_settings(request):
    return render(request, 'dashboard/settings.html')


@login_required
@require_http_methods(["POST"])
def update_watermark(request):
    if request.user.subscription_type == 'premium':
        request.user.watermark_enabled = 'watermark_enabled' in request.POST
        request.user.save(update_fields=['watermark_enabled'])
    return redirect('settings')


@login_required
def update_profile_picture(request):
    if request.method != 'POST':
        return redirect('settings')

    seller = request.user

    if request.POST.get('remove_picture'):
        if seller.profile_picture:
            try:
                import cloudinary.uploader
                public_id = seller.profile_picture.public_id
                if public_id:
                    cloudinary.uploader.destroy(public_id)
            except Exception as e:
                logger.error(f"Cloudinary delete error: {str(e)}")
            seller.profile_picture = None
            seller.save(update_fields=['profile_picture'])
        return redirect('settings')

    if request.POST.get('profile_picture_url'):
        try:
            url = request.POST.get('profile_picture_url')
            parts = url.split('/upload/')
            if len(parts) > 1:
                path = parts[1]
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
    if request.method == 'POST':
        seller = request.user
        business_name = request.POST.get('business_name', '').strip()
        bio = request.POST.get('bio', '').strip()
        category = request.POST.get('category')
        whatsapp_number = request.POST.get('whatsapp_number', '').strip()

        if not business_name:
            messages.error(request, 'Business name is required')
            return redirect('settings')
        if not whatsapp_number:
            messages.error(request, 'WhatsApp number is required')
            return redirect('settings')
        if Seller.objects.filter(whatsapp_number=whatsapp_number).exclude(id=seller.id).exists():
            messages.error(request, 'This WhatsApp number is already registered')
            return redirect('settings')

        seller.business_name = business_name
        seller.bio = bio
        seller.category = category
        seller.whatsapp_number = whatsapp_number
        seller.save()

    return redirect('settings')


@login_required
def update_account(request):
    if request.method == 'POST':
        seller = request.user
        email = request.POST.get('email', '').strip().lower()

        if not email:
            messages.error(request, 'Email is required')
            return redirect('settings')
        if '@' not in email or '.' not in email.split('@')[1]:
            messages.error(request, 'Invalid email format')
            return redirect('settings')
        if Seller.objects.filter(email__iexact=email).exclude(id=seller.id).exists():
            messages.error(request, 'This email is already registered')
            return redirect('settings')

        seller.email = email
        seller.save()

    return redirect('settings')


@login_required
def change_password(request):
    if request.method == 'POST':
        seller = request.user
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        if not seller.check_password(current_password):
            messages.error(request, 'Current password is incorrect')
            return redirect('settings')
        if new_password != confirm_password:
            messages.error(request, 'New passwords do not match')
            return redirect('settings')
        if len(new_password) < 6:
            messages.error(request, 'Password must be at least 6 characters')
            return redirect('settings')

        try:
            validate_password(new_password, seller)
        except ValidationError as e:
            messages.error(request, ' '.join(e.messages))
            return redirect('settings')

        seller.set_password(new_password)
        seller.save()
        update_session_auth_hash(request, seller)

    return redirect('settings')


# ─────────────────────────────────────────────
# PASSWORD RESET FLOW
# ─────────────────────────────────────────────
def forgot_password(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        try:
            seller = Seller.objects.get(email__iexact=email)
            reset_code = ''.join(random.choices(string.digits, k=5))

            request.session['reset_code'] = reset_code
            request.session['reset_email'] = email
            request.session['reset_code_expires'] = (
                timezone.now() + timedelta(minutes=10)
            ).isoformat()

            email_sent = send_password_reset_email(
                to_email=email,
                business_name=seller.business_name,
                reset_code=reset_code
            )

            if not email_sent:
                messages.error(request, 'Failed to send reset email. Please try again.')
                return render(request, 'auth/forgot_password.html')

        except Seller.DoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Password reset failed: {str(e)}")
            messages.error(request, 'Something went wrong. Please try again.')
            return render(request, 'auth/forgot_password.html')

        return redirect('verify_reset_code')

    return render(request, 'auth/forgot_password.html')


def verify_reset_code(request):
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        stored_code = request.session.get('reset_code')
        expires = request.session.get('reset_code_expires')

        if not stored_code or not expires:
            messages.error(request, 'No reset code found. Please request a new one.')
            return redirect('forgot_password')

        expires_dt = datetime.fromisoformat(expires)
        if timezone.now() > expires_dt:
            del request.session['reset_code']
            del request.session['reset_code_expires']
            messages.error(request, 'Code expired. Please request a new one.')
            return redirect('forgot_password')

        if code == stored_code:
            reset_token = uuid.uuid4().hex
            request.session['reset_token'] = reset_token
            request.session['reset_token_expires'] = (timezone.now() + timedelta(minutes=30)).isoformat()
            return redirect('reset_password', token=reset_token)
        else:
            messages.error(request, 'Invalid code. Please try again.')

    return render(request, 'auth/verify_code.html')


def reset_password(request, token):
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

            for key in ['reset_code', 'reset_email', 'reset_code_expires', 'reset_token', 'reset_token_expires']:
                request.session.pop(key, None)

            messages.success(request, '✓ Password reset successful! Please login.')
            return redirect('login')
        except Seller.DoesNotExist:
            messages.error(request, 'User not found.')
            return redirect('forgot_password')

    return render(request, 'auth/reset_password.html')


# ─────────────────────────────────────────────
# ADMIN VIEWS
# ─────────────────────────────────────────────
from django.contrib.admin.views.decorators import staff_member_required


@staff_member_required
def admin_dashboard(request):
    total_sellers = Seller.objects.filter(is_active=True, is_staff=False, is_superuser=False).count()
    total_products = Product.objects.filter(is_archived=False).count()
    total_page_views = Seller.objects.filter(is_staff=False, is_superuser=False).aggregate(Sum('total_page_views'))['total_page_views__sum'] or 0
    total_whatsapp_clicks = Seller.objects.filter(is_staff=False, is_superuser=False).aggregate(Sum('weekly_whatsapp_clicks'))['weekly_whatsapp_clicks__sum'] or 0
    recent_sellers = Seller.objects.filter(is_active=True, is_staff=False, is_superuser=False).order_by('-created_at')[:10]
    recent_products = Product.objects.filter(is_archived=False).select_related('seller').order_by('-created_at')[:10]
    top_sellers_by_views = Seller.objects.filter(is_active=True, is_staff=False, is_superuser=False).order_by('-weekly_page_views')[:10]
    top_sellers_by_products = Seller.objects.filter(is_active=True, is_staff=False, is_superuser=False).annotate(
        product_count=Count('products', filter=Q(products__is_archived=False))
    ).order_by('-product_count')[:10]
    subscription_stats = Seller.objects.filter(is_staff=False, is_superuser=False).values('subscription_type').annotate(count=Count('id'))
    premium_count = Seller.objects.filter(subscription_type='premium', is_staff=False, is_superuser=False).count()

    return render(request, 'admin_dashboard/dashboard.html', {
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
        'monthly_revenue': premium_count * 2000,
    })


@staff_member_required
def admin_sellers(request):
    sellers = Seller.objects.filter(is_active=True, is_staff=False, is_superuser=False).annotate(
        product_count=Count('products', filter=Q(products__is_archived=False))
    ).order_by('-created_at')

    subscription_filter = request.GET.get('subscription')
    if subscription_filter:
        sellers = sellers.filter(subscription_type=subscription_filter)

    search = request.GET.get('search')
    if search:
        sellers = sellers.filter(
            Q(business_name__icontains=search) | Q(username__icontains=search) | Q(email__icontains=search)
        )

    return render(request, 'admin_dashboard/sellers.html', {'sellers': sellers})


@staff_member_required
def admin_seller_detail(request, seller_id):
    seller = get_object_or_404(Seller, id=seller_id)
    products = Product.objects.filter(seller=seller).order_by('-created_at')[:20]

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
            messages.success(request, f'Seller is now {"featured" if seller.is_featured else "unfeatured"}')
        elif action == 'deactivate':
            seller.is_active = False
            seller.save()
            messages.warning(request, f'Seller {seller.business_name} deactivated')
        return redirect('admin_seller_detail', seller_id=seller_id)

    return render(request, 'admin_dashboard/seller_detail.html', {'seller': seller, 'products': products})


@staff_member_required
def admin_products(request):
    products = Product.objects.select_related('seller').order_by('-created_at')
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
    last_7_days = timezone.now() - timedelta(days=7)
    last_30_days = timezone.now() - timedelta(days=30)
    return render(request, 'admin_dashboard/analytics.html', {
        'new_sellers_7d': Seller.objects.filter(created_at__gte=last_7_days).count(),
        'new_sellers_30d': Seller.objects.filter(created_at__gte=last_30_days).count(),
        'new_products_7d': Product.objects.filter(created_at__gte=last_7_days).count(),
        'new_products_30d': Product.objects.filter(created_at__gte=last_30_days).count(),
        'category_stats': Seller.objects.values('category').annotate(count=Count('id')).order_by('-count'),
    })


# ─────────────────────────────────────────────
# SUBSCRIPTION / PAYMENT
# ─────────────────────────────────────────────
from .flutterwave import FlutterwavePayment


@login_required
def subscription(request):
    return render(request, 'dashboard/subscription.html', {
        'current_subscription': request.user.subscription_type,
        'subscription_expires': request.user.subscription_expires,
    })


@login_required
def upgrade_to_premium(request):
    if request.method == 'POST':
        seller = request.user
        tx_ref = f"VDP-{seller.id}-{uuid.uuid4().hex[:8]}"
        amount = Decimal('2000.00')

        flw = FlutterwavePayment()
        redirect_url = request.build_absolute_uri('/payment/verify/')
        result = flw.initialize_payment(
            email=seller.email, amount=amount, tx_ref=tx_ref,
            redirect_url=redirect_url, customer_name=seller.business_name
        )

        if result.get('status') == 'success':
            request.session['tx_ref'] = tx_ref
            request.session['upgrading_to_premium'] = True
            return redirect(result['data']['link'])
        else:
            messages.error(request, 'Payment initialization failed. Please try again.')
            return redirect('subscription')

    return redirect('subscription')


@login_required
def verify_payment(request):
    tx_ref = request.GET.get('tx_ref')
    transaction_id = request.GET.get('transaction_id')

    if not request.session.get('upgrading_to_premium'):
        messages.error(request, 'Invalid payment session')
        return redirect('subscription')

    flw = FlutterwavePayment()
    result = flw.verify_payment(transaction_id)

    if result.get('status') == 'success':
        data = result.get('data', {})
        if data.get('status') == 'successful' and data.get('tx_ref') == tx_ref:
            seller = request.user
            seller.subscription_type = 'premium'
            seller.subscription_expires = timezone.now() + timedelta(days=30)
            seller.save()
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
    try:
        signature = request.headers.get('verif-hash')
        flw = FlutterwavePayment()
        payload = request.body.decode('utf-8')
        if not signature or not flw.verify_webhook_signature(signature, payload):
            return JsonResponse({'status': 'error', 'message': 'Invalid signature'}, status=400)
        data = json.loads(payload)
        if data.get('event') == 'charge.completed' and data.get('data', {}).get('status') == 'successful':
            return JsonResponse({'status': 'success'})
        return JsonResponse({'status': 'received'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ─────────────────────────────────────────────
# GUEST FLOW
# ─────────────────────────────────────────────
def check_username(request):
    u = request.GET.get('u', '').strip().lower()
    if not u or len(u) < 2:
        return JsonResponse({'available': False, 'error': 'Too short'})
    import re
    if not re.match(r'^[a-z0-9_]+$', u):
        return JsonResponse({'available': False, 'error': 'Invalid characters'})
    taken = Seller.objects.filter(username__iexact=u).exists()
    return JsonResponse({'available': not taken})


@require_http_methods(["POST"])
def guest_init(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    business_name = data.get('business_name', '').strip()
    username = data.get('username', '').strip().lower()

    if not business_name or not username:
        return JsonResponse({'success': False, 'error': 'Both fields required'}, status=400)

    import re
    if not re.match(r'^[a-z0-9_]+$', username):
        return JsonResponse({'success': False, 'error': 'Username can only use letters, numbers, underscores'}, status=400)

    if Seller.objects.filter(username__iexact=username).exists():
        return JsonResponse({'success': False, 'error': f'"{username}" is already taken. Try another.'})

    request.session['guest_business_name'] = business_name
    request.session['guest_username'] = username
    request.session.modified = True
    return JsonResponse({'success': True})


@require_http_methods(["POST"])
def upload_products_batch(request):
    """
    Batch product creation for guests and authenticated sellers.
    Sends first-product email when authenticated seller uploads their first ever product.
    """
    try:
        products_data = json.loads(request.POST.get('products', '[]'))

        if not products_data:
            return JsonResponse({'success': False, 'error': 'No products provided'}, status=400)
        if len(products_data) > 50:
            return JsonResponse({'success': False, 'error': 'Maximum 50 products per batch'}, status=400)

        if not request.user.is_authenticated:
            guest_key = request.session.get('guest_key')
            if not guest_key:
                guest_key = uuid.uuid4().hex
                request.session['guest_key'] = guest_key
                request.session.modified = True

        # Check if this is auth seller's first ever upload (before creating)
        is_first_upload = False
        if request.user.is_authenticated:
            existing_count = Product.objects.filter(seller=request.user).count()
            is_first_upload = (existing_count == 0)

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
                seller=request.user if request.user.is_authenticated else None,
                guest_key=guest_key if not request.user.is_authenticated else None,
                description=str(item.get('description', '')).strip(),
                price=price_value,
            )

            for index, url in enumerate(valid_urls[:10]):
                ProductImage.objects.create(product=product, image_url=url, order=index)

            created.append(product.id)

        if not created:
            return JsonResponse({'success': False, 'error': 'No valid products to save'}, status=400)

        # Send first-product email to authenticated seller after first batch
        if request.user.is_authenticated and is_first_upload:
            try:
                send_first_product_email(
                    to_email=request.user.email,
                    business_name=request.user.business_name,
                    store_url=_store_url(request.user),
                )
            except Exception as e:
                logger.error(f"First product email failed: {e}")

        if request.user.is_authenticated:
            return JsonResponse({'success': True, 'created': len(created), 'redirect_url': '/dashboard/'})
        else:
            return JsonResponse({'success': True, 'created': len(created), 'redirect_url': f'/preview/{guest_key}/'})

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid data format'}, status=400)
    except Exception as e:
        logger.error(f"Batch upload error: {str(e)}\n{traceback.format_exc()}")
        return JsonResponse({'success': False, 'error': 'Failed to save. Please try again.'}, status=500)


def guest_store_preview(request, guest_key):
    if request.user.is_authenticated:
        return redirect('dashboard')

    products = Product.objects.filter(
        guest_key=guest_key,
        seller=None,
        is_archived=False,
    ).prefetch_related('images').order_by('created_at')

    if not products.exists():
        return redirect('upload_product')

    return render(request, 'guest_seller_page.html', {
        'products': products,
        'guest_key': guest_key,
        'business_name': request.session.get('guest_business_name', 'Your Store'),
        'username': request.session.get('guest_username', ''),
    })


def register_view(request):
    if request.method == 'POST':
        username = (
            request.session.get('guest_username') or
            request.POST.get('username', '')
        ).strip().lower()

        business_name = (
            request.session.get('guest_business_name') or
            request.POST.get('business_name', '')
        ).strip()

        if not username and business_name:
            import re
            username = re.sub(r'[^a-z0-9]', '_', business_name.lower()).strip('_')[:28]

        if username and Seller.objects.filter(username__iexact=username).exists():
            if not request.session.get('guest_username'):
                username = f"{username[:25]}_{random.randint(10, 99)}"

        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        whatsapp_number = request.POST.get('whatsapp_number', '').strip()
        country_code = request.POST.get('country_code', '+234').strip()
        currency_code = request.POST.get('currency_code', 'NGN').strip()
        currency_symbol = request.POST.get('currency_symbol', '₦').strip()
        category = request.POST.get('category', 'other')

        full_whatsapp = (country_code + whatsapp_number) if (country_code and not whatsapp_number.startswith('+')) else whatsapp_number

        errors = []
        if not all([username, email, password, business_name, whatsapp_number]):
            errors.append('All fields are required')
        if username and Seller.objects.filter(username__iexact=username).exists():
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
                'email': email, 'business_name': business_name,
                'username': username, 'whatsapp_number': whatsapp_number,
                'category': category,
            })

        try:
            seller = Seller.objects.create_user(
                username=username, email=email, password=password,
                business_name=business_name, whatsapp_number=full_whatsapp,
                category=category, country_code=country_code,
                currency_code=currency_code, currency_symbol=currency_symbol,
                subscription_type='free',
            )

            # Transfer guest products if any
            guest_key = request.session.get('guest_key')
            if guest_key:
                transferred = Product.objects.filter(
                    guest_key=guest_key, seller=None
                ).update(seller=seller, guest_key=None)
                logger.info(f"Transferred {transferred} guest products → seller {seller.id}")

            # Clear guest session
            for key in ['guest_key', 'guest_username', 'guest_business_name']:
                request.session.pop(key, None)

            login(request, seller)

            # Send welcome email (non-blocking — failure won't break registration)
            try:
                send_welcome_email(
                    to_email=seller.email,
                    business_name=seller.business_name,
                    store_url=_store_url(seller),
                )
            except Exception as e:
                logger.error(f"Welcome email failed: {e}")

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
                'email': email, 'business_name': business_name,
                'username': username, 'whatsapp_number': whatsapp_number,
                'category': category,
            })

    return render(request, 'register.html', {'active_tab': 'register'})