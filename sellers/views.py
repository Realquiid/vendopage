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
from sellers.models import (
    Seller, PlatformSettings,
    VendorBankAccount, Order, OrderItem, Dispute, Review,
)
from products.models import Product, ProductImage
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from sellers.geo_currency import detect_currency
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal, InvalidOperation
import uuid
import json
from sellers.email import (
    send_password_reset_email,
    send_welcome_email,
    send_first_product_email,
    send_first_whatsapp_click_email,
    send_order_confirmed_buyer,
    send_new_order_vendor,
    send_order_shipped_buyer,
    send_payment_sent_vendor,
    send_dispute_opened,
    send_dispute_resolved_buyer,    # NEW
    send_dispute_resolved_vendor,   # NEW
    send_premium_upgrade_email,     # NEW
    send_order_auto_released_buyer, # NEW
    send_review_received_vendor,    # NEW
)
import random
import string
import logging
import traceback
import requests as req
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def reset_weekly_analytics_if_needed(seller):
    now = timezone.now()
    if (now - seller.last_analytics_reset).days >= 7:
        seller.weekly_page_views = 0
        seller.weekly_whatsapp_clicks = 0
        seller.last_analytics_reset = now
        seller.save()


def _store_url(seller):
    return f'https://www.vendopage.com/{seller.slug}'


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
        is_featured=True, is_active=True, is_staff=False, is_superuser=False
    ).annotate(
        product_count=Count('products', filter=Q(
            products__is_archived=False, products__is_sold_out=False
        ))
    ).filter(product_count__gte=5).order_by('-product_count')[:4]

    sellers = Seller.objects.filter(
        is_active=True, is_staff=False, is_superuser=False
    ).annotate(
        product_count=Count('products', filter=Q(
            products__is_archived=False, products__is_sold_out=False
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

    products = Product.objects.filter(
        seller=seller,
        is_archived=False,
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


# ─────────────────────────────────────────────
# UPLOAD PRODUCT
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
    try:
        product = get_object_or_404(Product, id=product_id)
        product.whatsapp_clicks += 1
        product.views += 1
        product.save(update_fields=['whatsapp_clicks', 'views'])

        seller = product.seller
        seller.weekly_whatsapp_clicks += 1
        seller.save(update_fields=['weekly_whatsapp_clicks'])

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
    platform = PlatformSettings.get()
    transaction_fee_percent = platform.transaction_fee_percent
    premium_price = platform.premium_monthly_price
    example_order = 10000
    example_fee = (example_order * transaction_fee_percent) / 100
    example_payout = example_order - example_fee

    return render(request, 'dashboard/settings.html', {
        'platform_fee_percent': transaction_fee_percent,
        'transaction_fee':      transaction_fee_percent,
        'premium_price':        premium_price,
        'example_order':        example_order,
        'example_fee':          example_fee,
        'example_payout':       example_payout,
        'current_subscription': request.user.subscription_type,
        'subscription_expires': request.user.subscription_expires,
    })


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
# PASSWORD RESET
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
# SUBSCRIPTION / PAYMENT
# ─────────────────────────────────────────────
from .flutterwave import FlutterwavePayment


@login_required
def subscription(request):
    platform = PlatformSettings.get()
    transaction_fee_percent = platform.transaction_fee_percent
    premium_price = platform.premium_monthly_price
    example_order = 10000
    example_fee = (example_order * transaction_fee_percent) / 100
    example_payout = example_order - example_fee

    return render(request, 'dashboard/subscription.html', {
        'current_subscription': request.user.subscription_type,
        'subscription_expires': request.user.subscription_expires,
        'transaction_fee':      transaction_fee_percent,
        'premium_price':        premium_price,
        'example_order':        example_order,
        'example_fee':          example_fee,
        'example_payout':       example_payout,
    })


@login_required
def upgrade_to_premium(request):
    if request.method == 'POST':
        seller = request.user
        platform = PlatformSettings.get()
        amount = platform.premium_monthly_price
        tx_ref = f"VDP-{seller.id}-{uuid.uuid4().hex[:8]}"

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

            # ── NEW: send premium upgrade confirmation email ──
            try:
                send_premium_upgrade_email(
                    to_email=seller.email,
                    business_name=seller.business_name,
                    expires_date=seller.subscription_expires.strftime('%B %d, %Y'),
                )
            except Exception as e:
                logger.error(f"Premium upgrade email failed: {e}")

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
# UPLOAD BATCH
# ─────────────────────────────────────────────
@require_http_methods(["POST"])
def upload_products_batch(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Login required'}, status=401)

    try:
        products_data = json.loads(request.POST.get('products', '[]'))
        if not products_data:
            return JsonResponse({'success': False, 'error': 'No products provided'}, status=400)
        if len(products_data) > 50:
            return JsonResponse({'success': False, 'error': 'Maximum 50 products per batch'}, status=400)

        is_first_upload = Product.objects.filter(seller=request.user).count() == 0
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
                seller=request.user,
                description=str(item.get('description', '')).strip(),
                price=price_value,
            )
            for index, url in enumerate(valid_urls[:10]):
                ProductImage.objects.create(product=product, image_url=url, order=index)
            created.append(product.id)

        if not created:
            return JsonResponse({'success': False, 'error': 'No valid products to save'}, status=400)

        if is_first_upload:
            try:
                send_first_product_email(
                    to_email=request.user.email,
                    business_name=request.user.business_name,
                    store_url=_store_url(request.user),
                )
            except Exception as e:
                logger.error(f"First product email failed: {e}")

        return JsonResponse({'success': True, 'created': len(created), 'redirect_url': '/dashboard/'})

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid data format'}, status=400)
    except Exception as e:
        logger.error(f"Batch upload error: {str(e)}\n{traceback.format_exc()}")
        return JsonResponse({'success': False, 'error': 'Failed to save. Please try again.'}, status=500)


# ─────────────────────────────────────────────
# REGISTER
# ─────────────────────────────────────────────
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

        email           = request.POST.get('email', '').strip().lower()
        password        = request.POST.get('password', '')
        whatsapp_number = request.POST.get('whatsapp_number', '').strip()
        country_code    = request.POST.get('country_code', '+234').strip()
        currency_code   = request.POST.get('currency_code', 'NGN').strip()
        currency_symbol = request.POST.get('currency_symbol', '₦').strip()
        category        = request.POST.get('category', 'other')
        full_whatsapp   = (country_code + whatsapp_number) if (country_code and not whatsapp_number.startswith('+')) else whatsapp_number

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
            login(request, seller)
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


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────
@login_required
def dashboard(request):
    seller = request.user
    reset_weekly_analytics_if_needed(seller)

    active_products   = Product.objects.filter(seller=seller, is_archived=False, is_sold_out=False).prefetch_related('images')
    sold_out_products = Product.objects.filter(seller=seller, is_archived=False, is_sold_out=True).prefetch_related('images')
    archived_products = Product.objects.filter(seller=seller, is_archived=True).prefetch_related('images')
    most_viewed       = Product.objects.filter(seller=seller, is_archived=False).order_by('-views').first()
    all_products      = Product.objects.filter(seller=seller).prefetch_related('images').order_by('-created_at')[:50]

    catalog_url        = request.build_absolute_uri(f'/{seller.slug}')
    share_message      = f"🛍️ Check out my product catalog!\n\n{seller.business_name}\n\n{catalog_url}\n\n✨ Browse all my products anytime!"
    whatsapp_share_url = f"https://wa.me/?text={urllib.parse.quote(share_message)}"

    recent_orders    = []
    total_orders     = 0
    pending_orders   = 0
    total_earnings   = Decimal('0')
    pending_earnings = Decimal('0')

    if getattr(seller, 'store_mode', False):
        active_statuses = ['paid', 'shipped', 'delivered', 'disputed', 'completed']
        recent_orders = Order.objects.filter(seller=seller, status__in=active_statuses).order_by('-created_at')[:5]
        total_orders  = Order.objects.filter(seller=seller, status__in=active_statuses).count()
        pending_orders = Order.objects.filter(seller=seller, status__in=['paid', 'disputed']).count()
        total_earnings = Order.objects.filter(
            seller=seller, status__in=['delivered', 'completed'], payout_triggered=True,
        ).aggregate(total=Sum('vendor_payout'))['total'] or Decimal('0')
        pending_earnings = Order.objects.filter(
            seller=seller, status__in=['paid', 'shipped', 'disputed'], payment_type='escrow',
        ).aggregate(total=Sum('vendor_payout'))['total'] or Decimal('0')

    platform_settings = PlatformSettings.get()

    return render(request, 'dashboard/dashboard.html', {
        'products':             all_products,
        'active_count':         active_products.count(),
        'sold_out_count':       sold_out_products.count(),
        'archived_count':       archived_products.count(),
        'total_views':          seller.weekly_page_views,
        'whatsapp_clicks':      seller.weekly_whatsapp_clicks,
        'most_viewed':          most_viewed,
        'product_limit':        None,
        'whatsapp_share_url':   whatsapp_share_url,
        'catalog_url':          catalog_url,
        'recent_orders':        recent_orders,
        'total_orders':         total_orders,
        'pending_orders':       pending_orders,
        'total_earnings':       total_earnings,
        'pending_earnings':     pending_earnings,
        'platform_fee_percent': platform_settings.transaction_fee_percent,
        'premium_price':        platform_settings.premium_monthly_price,
    })


# ─────────────────────────────────────────────
# STORE MODE — TOGGLE + PAYOUT ACCOUNT
# ─────────────────────────────────────────────
@login_required
@require_http_methods(["POST"])
def toggle_store_mode(request):
    seller = request.user
    enabling = 'store_mode' in request.POST
    next_url = request.POST.get('next', 'settings')

    if enabling and not hasattr(seller, 'bank_account'):
        messages.error(request, 'Please add a payout account before enabling Store Mode.')
        return redirect('settings')

    seller.store_mode = enabling
    if seller.store_mode and not seller.store_mode_enabled_at:
        seller.store_mode_enabled_at = timezone.now()
    seller.save(update_fields=['store_mode', 'store_mode_enabled_at'])

    if enabling:
        messages.success(request, '🎉 Store Mode enabled! Buyers can now pay directly on your page.')
    else:
        messages.info(request, 'Store Mode has been disabled.')

    allowed = {'dashboard', 'settings'}
    return redirect(next_url if next_url in allowed else 'dashboard')


@login_required
@require_http_methods(["POST"])
def update_payout_account(request):
    seller = request.user
    account_number = request.POST.get('account_number', '').strip()
    bank_name      = request.POST.get('bank_name', '').strip()
    account_name   = request.POST.get('account_name', '').strip()

    if not all([account_number, bank_name, account_name]):
        messages.error(request, 'All payout fields are required.')
        return redirect('settings')

    VendorBankAccount.objects.update_or_create(
        seller=seller,
        defaults={
            'account_number': account_number,
            'bank_name':      bank_name,
            'account_name':   account_name,
            'is_verified':    False,
        }
    )
    messages.success(request, 'Payout account saved.')
    return redirect('settings')


# ─────────────────────────────────────────────
# CART + CHECKOUT
# ─────────────────────────────────────────────
def cart_view(request, slug):
    seller = get_object_or_404(Seller, slug=slug, is_active=True, store_mode=True)
    products = Product.objects.filter(
        seller=seller, is_archived=False,
    ).prefetch_related('images')
    product_map = {str(p.id): p for p in products}
    currency_info = detect_currency(request, seller)
    request.session['buyer_currency_code']   = currency_info['code']
    request.session['buyer_currency_symbol'] = currency_info['symbol']
    return render(request, 'store/cart.html', {
        'seller':        seller,
        'product_map':   product_map,
        'currency':      currency_info['symbol'],
        'currency_code': currency_info['code'],
        'currency_name': currency_info['name'],
    })


def checkout_view(request, slug):
    seller = get_object_or_404(Seller, slug=slug, is_active=True, store_mode=True)
    currency_symbol = request.session.get('buyer_currency_symbol', seller.currency_symbol or '₦')
    currency_code   = request.session.get('buyer_currency_code',   seller.currency_code   or 'NGN')
    if not request.session.get('buyer_currency_code'):
        currency_info   = detect_currency(request, seller)
        currency_symbol = currency_info['symbol']
        currency_code   = currency_info['code']
        request.session['buyer_currency_code']   = currency_code
        request.session['buyer_currency_symbol'] = currency_symbol
    products = Product.objects.filter(seller=seller, is_archived=False).prefetch_related('images')
    product_map = {str(p.id): p for p in products}
    return render(request, 'store/checkout.html', {
        'seller':        seller,
        'currency':      currency_symbol,
        'currency_code': currency_code,
        'product_map':   product_map,
    })


@require_http_methods(["POST"])
def initiate_payment(request, slug):
    seller = get_object_or_404(Seller, slug=slug, is_active=True, store_mode=True)

    buyer_name        = request.POST.get('buyer_name', '').strip()
    buyer_email       = request.POST.get('buyer_email', '').strip().lower()
    buyer_phone       = request.POST.get('buyer_phone', '').strip()
    delivery_address  = request.POST.get('delivery_address', '').strip()
    delivery_city     = request.POST.get('delivery_city', '').strip()
    cart_json         = request.POST.get('cart_json', '{}')
    payment_type      = request.POST.get('payment_type', 'escrow')
    delivery_required = request.POST.get('delivery_required', '1') == '1'

    if not all([buyer_name, buyer_email, buyer_phone, delivery_address]):
        messages.error(request, 'Please fill in all required fields.')
        return redirect('checkout', slug=slug)

    try:
        cart = json.loads(cart_json)
    except Exception:
        messages.error(request, 'Invalid cart data. Please go back and try again.')
        return redirect('cart', slug=slug)

    if not cart:
        messages.error(request, 'Your cart is empty.')
        return redirect('cart', slug=slug)

    product_ids = []
    for k in cart.keys():
        try:
            product_ids.append(int(k))
        except (ValueError, TypeError):
            pass

    db_products = {
        str(p.id): p
        for p in Product.objects.filter(id__in=product_ids, seller=seller, is_archived=False)
    }

    subtotal   = Decimal('0')
    line_items = []
    item_names = []

    for pid, item in cart.items():
        product = db_products.get(str(pid))
        if not product or not product.price:
            continue
        qty = max(1, int(item.get('qty', 1))) if isinstance(item, dict) else max(1, int(item))
        img = product.images.first()
        short_name = (product.description or 'Product')[:40]
        item_names.append(f"{short_name} x{qty}")
        line_items.append({
            'product_id':    product.id,
            'product_name':  product.description or 'Product',
            'product_image': img.image_url if img else '',
            'price':         str(product.price),
            'qty':           qty,
        })
        subtotal += product.price * qty

    if not line_items or subtotal <= 0:
        messages.error(request, 'No valid items in cart.')
        return redirect('cart', slug=slug)

    item_count    = len(line_items)
    payment_label = 'Protected Pay' if payment_type == 'escrow' else 'Direct Pay'
    if item_count == 1:
        pay_title       = f"Order: {item_names[0]}"
        pay_description = f"{payment_label} — {seller.business_name}"
    elif item_count <= 3:
        pay_title       = f"Order from {seller.business_name}"
        pay_description = f"{payment_label} — {', '.join(item_names)}"
    else:
        pay_title       = f"Order from {seller.business_name}"
        pay_description = f"{payment_label} — {item_count} items"

    tx_ref = f"VDP-ORD-{uuid.uuid4().hex[:12].upper()}"

    request.session['pending_order'] = {
        'tx_ref':            tx_ref,
        'seller_id':         seller.id,
        'buyer_name':        buyer_name,
        'buyer_email':       buyer_email,
        'buyer_phone':       buyer_phone,
        'delivery_address':  delivery_address,
        'delivery_city':     delivery_city,
        'line_items':        line_items,
        'subtotal':          str(subtotal),
        'currency':          request.session.get('buyer_currency_code', seller.currency_code or 'NGN'),
        'payment_type':      payment_type,
        'delivery_required': delivery_required,
    }
    request.session.modified = True

    flw = FlutterwavePayment()
    result = flw.initialize_payment(
        email=buyer_email, amount=subtotal, tx_ref=tx_ref,
        redirect_url=request.build_absolute_uri('/order/confirm/'),
        customer_name=buyer_name,
        currency=request.session.get('buyer_currency_code', seller.currency_code or 'NGN'),
        title=pay_title, description=pay_description,
    )

    if result.get('status') == 'success':
        return redirect(result['data']['link'])

    request.session.pop('pending_order', None)
    messages.error(request, 'Payment could not be started. Please try again.')
    return redirect('checkout', slug=slug)


def order_confirmation(request):
    tx_ref         = request.GET.get('tx_ref', '')
    transaction_id = request.GET.get('transaction_id', '')
    status         = request.GET.get('status', '')

    if status != 'successful' or not tx_ref or not transaction_id:
        request.session.pop('pending_order', None)
        return render(request, 'store/order_failed.html', {'reason': 'Payment was not completed.'})

    pending = request.session.get('pending_order')
    if not pending or pending.get('tx_ref') != tx_ref:
        try:
            existing = Order.objects.get(flutterwave_tx_ref=tx_ref)
            return redirect('order_detail', order_ref=str(existing.order_ref))
        except Order.DoesNotExist:
            return render(request, 'store/order_failed.html', {
                'reason': 'Session expired. If you were charged, contact support.'
            })

    flw    = FlutterwavePayment()
    result = flw.verify_payment(transaction_id)
    data   = result.get('data', {})

    if not (result.get('status') == 'success'
            and data.get('status') == 'successful'
            and data.get('tx_ref') == tx_ref):
        request.session.pop('pending_order', None)
        return render(request, 'store/order_failed.html', {
            'reason': 'Payment verification failed. If you were charged, contact support.'
        })

    try:
        seller = Seller.objects.get(id=pending['seller_id'])
    except Seller.DoesNotExist:
        request.session.pop('pending_order', None)
        return render(request, 'store/order_failed.html', {'reason': 'Store not found.'})

    subtotal     = Decimal(pending['subtotal'])
    payment_type = pending.get('payment_type', 'escrow')

    order = Order(
        seller             = seller,
        flutterwave_tx_ref = tx_ref,
        flutterwave_tx_id  = str(transaction_id),
        buyer_name         = pending['buyer_name'],
        buyer_email        = pending['buyer_email'],
        buyer_phone        = pending['buyer_phone'],
        delivery_address   = pending['delivery_address'],
        delivery_city      = pending.get('delivery_city', ''),
        subtotal           = subtotal,
        currency           = pending.get('currency', 'NGN'),
        status             = 'paid',
        payment_verified   = True,
        paid_at            = timezone.now(),
        payment_type       = payment_type,
    )
    order.calculate_fees()
    order.save()

    for li in pending['line_items']:
        OrderItem.objects.create(
            order             = order,
            product_id        = li['product_id'],
            product_name      = li['product_name'],
            product_image_url = li['product_image'],
            price             = Decimal(li['price']),
            quantity          = li['qty'],
        )

    request.session.pop('pending_order', None)

    if payment_type == 'direct':
        try:
            _trigger_payout(order)
        except Exception as e:
            logger.error(f"Direct pay payout failed for order {order.order_ref}: {e}")

    try:
        send_order_confirmed_buyer(
            to_email=order.buyer_email, buyer_name=order.buyer_name,
            order_ref=str(order.order_ref)[:8].upper(), seller_name=seller.business_name,
            items=list(order.items.all()), subtotal=order.subtotal, currency=order.currency,
            payment_type=payment_type,
        )
    except Exception as e:
        logger.error(f"Buyer confirmation email failed: {e}")

    try:
        send_new_order_vendor(
            to_email=seller.email, business_name=seller.business_name,
            buyer_name=order.buyer_name, order_ref=str(order.order_ref)[:8].upper(),
            items=list(order.items.all()), subtotal=order.subtotal, currency=order.currency,
            dashboard_url=f"https://www.vendopage.com/dashboard/orders/{order.order_ref}/",
            payment_type=payment_type,
        )
    except Exception as e:
        logger.error(f"Vendor new order email failed: {e}")

    return redirect('order_detail', order_ref=str(order.order_ref))

def get_my_ip(request):
    from django.http import HttpResponse
    import requests as req
    ip = req.get('https://api.ipify.org').text
    return HttpResponse(f'Your server IP is: {ip}')


# ─────────────────────────────────────────────
# BUYER VIEWS
# ─────────────────────────────────────────────
def order_detail(request, order_ref):
    order   = get_object_or_404(Order, order_ref=order_ref)
    dispute = getattr(order, 'dispute', None)
    review  = getattr(order, 'review', None)
    return render(request, 'store/order_detail.html', {'order': order, 'dispute': dispute, 'review': review})


@require_http_methods(["POST"])
def confirm_receipt(request, order_ref):
    order = get_object_or_404(Order, order_ref=order_ref)
    if order.status not in ('shipped',):
        messages.error(request, 'This order cannot be confirmed yet.')
        return redirect('order_detail', order_ref=order_ref)
    order.status       = 'delivered'
    order.delivered_at = timezone.now()
    order.save()
    _trigger_payout(order)
    return redirect('order_detail', order_ref=order_ref)


@require_http_methods(["GET", "POST"])
def raise_dispute(request, order_ref):
    order = get_object_or_404(Order, order_ref=order_ref)
    if hasattr(order, 'dispute'):
        messages.info(request, 'A dispute already exists for this order.')
        return redirect('order_detail', order_ref=order_ref)
    if order.status not in ('shipped', 'paid'):
        messages.error(request, 'You can only dispute an active order.')
        return redirect('order_detail', order_ref=order_ref)
    if request.method == 'POST':
        reason        = request.POST.get('reason', 'other')
        buyer_message = request.POST.get('message', '').strip()
        evidence_url  = request.POST.get('evidence_url', '').strip()
        if not buyer_message:
            messages.error(request, 'Please describe the issue.')
            return render(request, 'store/dispute.html', {'order': order})
        Dispute.objects.create(order=order, raised_by='buyer', reason=reason,
                               buyer_message=buyer_message, buyer_evidence=evidence_url)
        order.status = 'disputed'
        order.save()
        try:
            send_dispute_opened(
                vendor_email=order.seller.email,
                buyer_email=order.buyer_email,
                order_ref=str(order.order_ref)[:8].upper(),
                reason=reason,
                buyer_name=order.buyer_name,  # ← now passed so buyer email is personalised
            )
        except Exception as e:
            logger.error(f"Dispute email failed: {e}")
        messages.success(request, 'Dispute raised. Our team will review it within 48 hours.')
        return redirect('order_detail', order_ref=order_ref)
    return render(request, 'store/dispute.html', {'order': order})


@require_http_methods(["GET", "POST"])
def leave_review(request, order_ref):
    order = get_object_or_404(Order, order_ref=order_ref)
    if order.status not in ('delivered', 'completed'):
        messages.error(request, 'You can only review a completed order.')
        return redirect('order_detail', order_ref=order_ref)
    if hasattr(order, 'review'):
        messages.info(request, 'You have already reviewed this order.')
        return redirect('order_detail', order_ref=order_ref)
    if request.method == 'POST':
        try:
            rating = int(request.POST.get('rating', 0))
        except ValueError:
            rating = 0
        if rating < 1 or rating > 5:
            messages.error(request, 'Please select a rating between 1 and 5.')
            return render(request, 'store/leave_review.html', {'order': order})
        comment = request.POST.get('comment', '').strip()
        Review.objects.create(order=order, seller=order.seller, rating=rating, comment=comment)

        # ── NEW: notify vendor of new review ──
        try:
            send_review_received_vendor(
                to_email=order.seller.email,
                business_name=order.seller.business_name,
                order_ref=str(order.order_ref)[:8].upper(),
                rating=rating,
                comment=comment,
            )
        except Exception as e:
            logger.error(f"Review notification email failed: {e}")

        messages.success(request, 'Thank you for your review!')
        return redirect('order_detail', order_ref=order_ref)
    return render(request, 'store/leave_review.html', {'order': order})


# ─────────────────────────────────────────────
# VENDOR ORDERS
# ─────────────────────────────────────────────
@login_required
def vendor_orders(request):
    seller        = request.user
    status_filter = request.GET.get('status', '')
    orders        = Order.objects.filter(seller=seller).order_by('-created_at')
    
    if status_filter == 'completed':
        orders = orders.filter(status__in=['delivered', 'completed'])
    elif status_filter:
        orders = orders.filter(status=status_filter)
    counts = {
        'all':       Order.objects.filter(seller=seller).count(),
        'paid':      Order.objects.filter(seller=seller, status='paid').count(),
        'shipped':   Order.objects.filter(seller=seller, status='shipped').count(),
        'disputed':  Order.objects.filter(seller=seller, status='disputed').count(),
        'completed': Order.objects.filter(seller=seller, status__in=['delivered', 'completed']).count(),
    }
    return render(request, 'dashboard/orders.html', {
        'orders': orders[:50], 'counts': counts, 'status_filter': status_filter,
    })


@login_required
def vendor_order_detail(request, order_ref):
    order   = get_object_or_404(Order, order_ref=order_ref, seller=request.user)
    dispute = getattr(order, 'dispute', None)
    if request.method == 'POST' and dispute and request.POST.get('action') == 'reply_dispute':
        reply    = request.POST.get('vendor_reply', '').strip()
        evidence = request.POST.get('vendor_evidence', '').strip()
        if reply:
            dispute.vendor_reply    = reply
            dispute.vendor_evidence = evidence
            dispute.status          = 'vendor_replied'
            dispute.save()
            messages.success(request, 'Your response has been submitted.')
        return redirect('vendor_order_detail', order_ref=order_ref)
    return render(request, 'dashboard/order_detail.html', {'order': order, 'dispute': dispute})


@login_required
@require_http_methods(["GET", "POST"])
def mark_shipped(request, order_ref):
    order = get_object_or_404(Order, order_ref=order_ref, seller=request.user)
    if order.status not in ('paid', 'disputed'):
        messages.error(request, 'Only paid or disputed orders can be marked as shipped.')
        return redirect('vendor_order_detail', order_ref=order_ref)
    if request.method == 'POST':
        tracking_info = request.POST.get('tracking_info', '').strip()
        courier_name  = request.POST.get('courier_name', '').strip()
        order.status        = 'shipped'
        order.shipped_at    = timezone.now()
        order.tracking_info = tracking_info
        order.courier_name  = courier_name
        order.set_auto_release()
        order.save()
        try:
            send_order_shipped_buyer(
                to_email=order.buyer_email, buyer_name=order.buyer_name,
                order_ref=str(order.order_ref)[:8].upper(), seller_name=order.seller.business_name,
                tracking_info=tracking_info, courier_name=courier_name,
                order_url=f"https://www.vendopage.com/order/{order.order_ref}/",
            )
        except Exception as e:
            logger.error(f"Shipped email failed: {e}")
        messages.success(request, '✓ Order marked as shipped. Buyer has been notified.')
        return redirect('vendor_order_detail', order_ref=order_ref)
    return render(request, 'dashboard/mark_shipped.html', {'order': order})


# ─────────────────────────────────────────────
# PAYOUT
# ─────────────────────────────────────────────
def _trigger_payout(order):
    if order.payout_triggered:
        return
    try:
        bank = order.seller.bank_account
    except VendorBankAccount.DoesNotExist:
        logger.error(f"No bank account for seller {order.seller.id} — payout skipped")
        return

    headers = {
        'Authorization': f'Bearer {settings.FLUTTERWAVE_SECRET_KEY}',
        'Content-Type':  'application/json',
    }
    payload = {
        'account_bank':   bank.bank_code or bank.bank_name,
        'account_number': bank.account_number,
        'amount':         float(order.vendor_payout),
        'currency':       order.currency,
        'narration':      f'Vendopage payout — Order {str(order.order_ref)[:8].upper()}',
        'reference':      f'VDP-PAY-{uuid.uuid4().hex[:10]}',
    }
    try:
        r = req.post('https://api.flutterwave.com/v3/transfers',
                     json=payload, headers=headers, timeout=15)
        data = r.json()
        if data.get('status') == 'success':
            order.payout_triggered        = True
            order.payout_at               = timezone.now()
            order.status                  = 'completed'
            order.flutterwave_transfer_id = str(data['data'].get('id', ''))
            order.save()
            try:
                send_payment_sent_vendor(
                    to_email=order.seller.email, business_name=order.seller.business_name,
                    amount=order.vendor_payout, currency=order.currency,
                    order_ref=str(order.order_ref)[:8].upper(),
                    bank_name=bank.bank_name, account_number=bank.account_number[-4:],
                )
            except Exception as e:
                logger.error(f"Payout email failed: {e}")
        else:
            logger.error(f"Flutterwave payout failed for order {order.order_ref}: {data}")
    except Exception as e:
        logger.error(f"Payout request exception for order {order.order_ref}: {e}")


def auto_release_expired_orders():
    """
    Releases all shipped orders whose 72-hour window has passed.
    Called by the management command and admin settings panel.
    """
    now     = timezone.now()
    expired = Order.objects.filter(
        status='shipped', auto_release_at__lte=now, payout_triggered=False,
    )
    for order in expired:
        logger.info(f"Auto-releasing order {order.order_ref}")
        order.status       = 'delivered'
        order.delivered_at = now
        order.save()
        _trigger_payout(order)

        # ── NEW: notify buyer that order was auto-completed ──
        try:
            send_order_auto_released_buyer(
                to_email=order.buyer_email,
                buyer_name=order.buyer_name,
                order_ref=str(order.order_ref)[:8].upper(),
                seller_name=order.seller.business_name,
            )
        except Exception as e:
            logger.error(f"Auto-release buyer email failed for order {order.order_ref}: {e}")


@csrf_exempt
@require_http_methods(["POST"])
def flutterwave_order_webhook(request):
    try:
        signature = request.headers.get('verif-hash')
        payload   = request.body.decode('utf-8')
        flw = FlutterwavePayment()
        if not signature or not flw.verify_webhook_signature(signature, payload):
            return JsonResponse({'status': 'error', 'message': 'Invalid signature'}, status=400)

        data   = json.loads(payload)
        event  = data.get('event')
        charge = data.get('data', {})

        if event != 'charge.completed' or charge.get('status') != 'successful':
            return JsonResponse({'status': 'received'})

        tx_ref         = charge.get('tx_ref', '')
        transaction_id = str(charge.get('id', ''))

        if not tx_ref.startswith('VDP-ORD-'):
            return JsonResponse({'status': 'skipped - not an order payment'})

        try:
            Order.objects.get(flutterwave_tx_ref=tx_ref, payment_verified=True)
            return JsonResponse({'status': 'already_processed'})
        except Order.DoesNotExist:
            pass

        try:
            order = Order.objects.get(flutterwave_tx_ref=tx_ref, payment_verified=False)
            order.status            = 'paid'
            order.payment_verified  = True
            order.flutterwave_tx_id = transaction_id
            order.paid_at           = timezone.now()
            order.save()
            try:
                send_new_order_vendor(
                    to_email=order.seller.email, business_name=order.seller.business_name,
                    buyer_name=order.buyer_name, order_ref=str(order.order_ref)[:8].upper(),
                    items=list(order.items.all()), subtotal=order.subtotal, currency=order.currency,
                    dashboard_url=f"https://www.vendopage.com/dashboard/orders/{order.order_ref}/",
                )
            except Exception as e:
                logger.error(f"Webhook vendor email failed: {e}")
            return JsonResponse({'status': 'fixed_unverified_order'})
        except Order.DoesNotExist:
            pass

        logger.error(
            f"WEBHOOK ALERT: Payment received but no Order found.\n"
            f"tx_ref: {tx_ref}\ntransaction_id: {transaction_id}\n"
            f"amount: {charge.get('amount')} {charge.get('currency')}\n"
            f"customer: {charge.get('customer', {}).get('email')}\n"
            f"ACTION REQUIRED: Manual order creation or refund needed."
        )
        return JsonResponse({'status': 'logged_for_review'})

    except Exception as e:
        logger.error(f"Order webhook error: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ─────────────────────────────────────────────
# BANK PROXY APIs
# ─────────────────────────────────────────────
@require_http_methods(["GET"])
def get_banks(request):
    try:
        r = req.get(
            'https://api.flutterwave.com/v3/banks/NG',
            headers={'Authorization': f'Bearer {settings.FLUTTERWAVE_SECRET_KEY}'},
            timeout=10,
        )
        data = r.json()
        if data.get('status') == 'success' and data.get('data'):
            banks = [{'code': b['code'], 'name': b['name']} for b in data['data']]
            return JsonResponse({'success': True, 'banks': banks})
        raise Exception("Bad response from Flutterwave")
    except Exception as e:
        logger.error(f"get_banks error: {e}")
        fallback = [
            {'code': '044', 'name': 'Access Bank'},
            {'code': '011', 'name': 'First Bank of Nigeria'},
            {'code': '058', 'name': 'Guaranty Trust Bank (GTB)'},
            {'code': '057', 'name': 'Zenith Bank'},
            {'code': '033', 'name': 'United Bank for Africa (UBA)'},
            {'code': '214', 'name': 'First City Monument Bank (FCMB)'},
            {'code': '070', 'name': 'Fidelity Bank'},
            {'code': '050', 'name': 'EcoBank Nigeria'},
            {'code': '221', 'name': 'Stanbic IBTC Bank'},
            {'code': '232', 'name': 'Sterling Bank'},
            {'code': '032', 'name': 'Union Bank of Nigeria'},
            {'code': '035', 'name': 'Wema Bank'},
            {'code': '076', 'name': 'Polaris Bank'},
            {'code': '082', 'name': 'Keystone Bank'},
            {'code': '101', 'name': 'Providus Bank'},
            {'code': '215', 'name': 'Unity Bank'},
            {'code': '110', 'name': 'VFD Microfinance Bank'},
            {'code': '090267', 'name': 'Kuda Bank'},
            {'code': '090405', 'name': 'OPay'},
            {'code': '090175', 'name': 'PalmPay'},
            {'code': '090304', 'name': 'Moniepoint'},
        ]
        return JsonResponse({'success': True, 'banks': fallback, 'fallback': True})


@require_http_methods(["POST"])
def verify_bank_account(request):
    try:
        body           = json.loads(request.body)
        account_number = body.get('account_number', '').strip()
        bank_code      = body.get('bank_code', '').strip()

        if not account_number or not bank_code:
            return JsonResponse({'success': False, 'error': 'Missing fields'}, status=400)
        if len(account_number) != 10 or not account_number.isdigit():
            return JsonResponse({'success': False, 'error': 'Invalid account number'}, status=400)

        r = req.post(
            'https://api.flutterwave.com/v3/accounts/resolve',
            json={'account_number': account_number, 'account_bank': bank_code},
            headers={
                'Authorization': f'Bearer {settings.FLUTTERWAVE_SECRET_KEY}',
                'Content-Type': 'application/json',
            },
            timeout=10,
        )
        data = r.json()
        if data.get('status') == 'success' and data.get('data', {}).get('account_name'):
            return JsonResponse({'success': True, 'account_name': data['data']['account_name']})
        return JsonResponse({'success': False, 'error': data.get('message', 'Account not found')})

    except req.exceptions.Timeout:
        return JsonResponse({'success': False, 'error': 'Verification timed out. Please try again.'})
    except Exception as e:
        logger.error(f"verify_bank_account error: {e}")
        return JsonResponse({'success': False, 'error': 'Verification failed. Please try again.'}, status=500)


# ─────────────────────────────────────────────
# ADMIN VIEWS
# ─────────────────────────────────────────────
@staff_member_required
def admin_dashboard(request):
    total_sellers    = Seller.objects.filter(is_active=True, is_staff=False, is_superuser=False).count()
    total_products   = Product.objects.filter(is_archived=False).count()
    total_page_views = Seller.objects.filter(is_staff=False, is_superuser=False).aggregate(
        t=Sum('total_page_views'))['t'] or 0
    premium_count    = Seller.objects.filter(subscription_type='premium', is_staff=False, is_superuser=False).count()
    last_7d          = timezone.now() - timedelta(days=7)
    last_30d         = timezone.now() - timedelta(days=30)
    new_sellers_7d   = Seller.objects.filter(created_at__gte=last_7d).count()
    new_sellers_30d  = Seller.objects.filter(created_at__gte=last_30d).count()
    new_products_7d  = Product.objects.filter(created_at__gte=last_7d).count()
    recent_sellers       = Seller.objects.filter(is_active=True, is_staff=False, is_superuser=False).order_by('-created_at')[:8]
    top_sellers_by_views = Seller.objects.filter(is_active=True, is_staff=False, is_superuser=False).order_by('-weekly_page_views')[:10]
    subscription_stats   = Seller.objects.filter(is_staff=False, is_superuser=False).values('subscription_type').annotate(count=Count('id'))
    open_disputes_count   = Dispute.objects.filter(status__in=['open', 'vendor_replied', 'under_review']).count()
    pending_payouts_count = Order.objects.filter(payout_triggered=False, status__in=['delivered', 'completed']).count()
    platform              = PlatformSettings.get()
    return render(request, 'admin_dashboard/dashboard.html', {
        'total_sellers': total_sellers, 'total_products': total_products,
        'total_page_views': total_page_views, 'premium_count': premium_count,
        'new_sellers_7d': new_sellers_7d, 'new_sellers_30d': new_sellers_30d,
        'new_products_7d': new_products_7d, 'recent_sellers': recent_sellers,
        'top_sellers_by_views': top_sellers_by_views, 'subscription_stats': subscription_stats,
        'monthly_revenue': premium_count * platform.premium_monthly_price,
        'open_disputes': open_disputes_count, 'pending_payouts': pending_payouts_count,
        'open_disputes_count': open_disputes_count, 'pending_payouts_count': pending_payouts_count,
    })


@staff_member_required
def admin_sellers(request):
    sellers = Seller.objects.filter(is_staff=False, is_superuser=False).annotate(
        product_count=Count('products', filter=Q(products__is_archived=False))
    ).order_by('-created_at')
    subscription_filter = request.GET.get('subscription')
    store_mode_filter   = request.GET.get('store_mode')
    active_filter       = request.GET.get('active')
    search              = request.GET.get('search')
    if subscription_filter:
        sellers = sellers.filter(subscription_type=subscription_filter)
    if store_mode_filter == 'on':
        sellers = sellers.filter(store_mode=True)
    elif store_mode_filter == 'off':
        sellers = sellers.filter(store_mode=False)
    if active_filter == '1':
        sellers = sellers.filter(is_active=True)
    elif active_filter == '0':
        sellers = sellers.filter(is_active=False)
    if search:
        sellers = sellers.filter(
            Q(business_name__icontains=search) | Q(username__icontains=search) | Q(email__icontains=search)
        )
    open_disputes_count   = Dispute.objects.filter(status__in=['open', 'vendor_replied', 'under_review']).count()
    pending_payouts_count = Order.objects.filter(payout_triggered=False, status__in=['delivered', 'completed']).count()
    return render(request, 'admin_dashboard/sellers.html', {
        'sellers': sellers, 'open_disputes_count': open_disputes_count,
        'pending_payouts_count': pending_payouts_count,
    })


@staff_member_required
def admin_seller_detail(request, seller_id):
    seller        = get_object_or_404(Seller, id=seller_id)
    products      = Product.objects.filter(seller=seller).prefetch_related('images').order_by('-created_at')
    total_revenue = Order.objects.filter(
        seller=seller, status__in=['delivered', 'completed'], payout_triggered=True,
    ).aggregate(t=Sum('vendor_payout'))['t'] or Decimal('0')
    orders_count  = Order.objects.filter(
        seller=seller, status__in=['paid', 'shipped', 'delivered', 'completed', 'disputed']
    ).count()
    orders = Order.objects.filter(seller=seller).order_by('-created_at')[:8]
    if not seller.slug:
        seller.save()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'change_subscription':
            new_type = request.POST.get('subscription_type')
            expires  = request.POST.get('subscription_expires', '').strip()
            seller.subscription_type = new_type
            if expires:
                try:
                    seller.subscription_expires = datetime.strptime(expires, '%Y-%m-%d').replace(
                        tzinfo=timezone.get_current_timezone()
                    )
                except ValueError:
                    pass
            elif new_type == 'premium' and not seller.subscription_expires:
                seller.subscription_expires = timezone.now() + timedelta(days=30)
            seller.save()
            # ── NEW: notify seller of admin-granted premium upgrade ──
            if new_type == 'premium':
                try:
                    send_premium_upgrade_email(
                        to_email=seller.email,
                        business_name=seller.business_name,
                        expires_date=seller.subscription_expires.strftime('%B %d, %Y'),
                    )
                except Exception as e:
                    logger.error(f"Admin premium upgrade email failed: {e}")
            messages.success(request, f'Subscription updated to {new_type}.')

        elif action == 'toggle_featured':
            seller.is_featured = not seller.is_featured
            seller.save(update_fields=['is_featured'])
            messages.success(request, f'{"Featured ⭐" if seller.is_featured else "Removed from featured"}.')

        elif action == 'toggle_store_mode':
            seller.store_mode = not seller.store_mode
            if seller.store_mode and not seller.store_mode_enabled_at:
                seller.store_mode_enabled_at = timezone.now()
            seller.save(update_fields=['store_mode', 'store_mode_enabled_at'])
            messages.success(request, f'Store Mode {"enabled" if seller.store_mode else "disabled"}.')

        elif action == 'deactivate':
            seller.is_active = False
            seller.save(update_fields=['is_active'])
            messages.warning(request, f'{seller.business_name} has been banned.')

        elif action == 'activate':
            seller.is_active = True
            seller.save(update_fields=['is_active'])
            messages.success(request, f'{seller.business_name} account restored.')

        elif action == 'reset_analytics':
            seller.weekly_page_views      = 0
            seller.weekly_whatsapp_clicks = 0
            seller.last_analytics_reset   = timezone.now()
            seller.save(update_fields=['weekly_page_views', 'weekly_whatsapp_clicks', 'last_analytics_reset'])
            messages.success(request, 'Weekly analytics reset.')

        elif action == 'verify_bank':
            try:
                seller.bank_account.is_verified = True
                seller.bank_account.save(update_fields=['is_verified'])
                messages.success(request, '✅ Bank account verified.')
            except VendorBankAccount.DoesNotExist:
                messages.error(request, 'No bank account found.')

        elif action == 'unverify_bank':
            try:
                seller.bank_account.is_verified = False
                seller.bank_account.save(update_fields=['is_verified'])
                messages.warning(request, '⚠️ Bank account marked unverified.')
            except VendorBankAccount.DoesNotExist:
                messages.error(request, 'No bank account found.')

        return redirect('admin_seller_detail', seller_id=seller_id)

    open_disputes_count   = Dispute.objects.filter(status__in=['open', 'vendor_replied', 'under_review']).count()
    pending_payouts_count = Order.objects.filter(payout_triggered=False, status__in=['delivered', 'completed']).count()
    return render(request, 'admin_dashboard/seller_detail.html', {
        'seller': seller, 'products': products, 'total_revenue': total_revenue,
        'orders_count': orders_count, 'orders': orders,
        'open_disputes_count': open_disputes_count, 'pending_payouts_count': pending_payouts_count,
    })


@staff_member_required
def admin_products(request):
    products = Product.objects.select_related('seller').order_by('-created_at')
    status   = request.GET.get('status')
    search   = request.GET.get('search', '').strip()
    if status == 'sold_out':
        products = products.filter(is_sold_out=True)
    elif status == 'archived':
        products = products.filter(is_archived=True)
    elif status == 'active':
        products = products.filter(is_archived=False, is_sold_out=False)
    if search:
        products = products.filter(
            Q(description__icontains=search) | Q(seller__business_name__icontains=search)
        )
    open_disputes_count   = Dispute.objects.filter(status__in=['open', 'vendor_replied', 'under_review']).count()
    pending_payouts_count = Order.objects.filter(payout_triggered=False, status__in=['delivered', 'completed']).count()
    return render(request, 'admin_dashboard/products.html', {
        'products': products[:100], 'open_disputes_count': open_disputes_count,
        'pending_payouts_count': pending_payouts_count,
    })


@staff_member_required
def admin_analytics(request):
    last_7d   = timezone.now() - timedelta(days=7)
    last_30d  = timezone.now() - timedelta(days=30)
    platform  = PlatformSettings.get()
    premium_count         = Seller.objects.filter(subscription_type='premium', is_staff=False, is_superuser=False).count()
    total_sellers         = Seller.objects.filter(is_active=True, is_staff=False, is_superuser=False).count()
    open_disputes_count   = Dispute.objects.filter(status__in=['open', 'vendor_replied', 'under_review']).count()
    pending_payouts_count = Order.objects.filter(payout_triggered=False, status__in=['delivered', 'completed']).count()
    return render(request, 'admin_dashboard/analytics.html', {
        'new_sellers_7d':  Seller.objects.filter(created_at__gte=last_7d).count(),
        'new_sellers_30d': Seller.objects.filter(created_at__gte=last_30d).count(),
        'new_products_7d': Product.objects.filter(created_at__gte=last_7d).count(),
        'new_products_30d': Product.objects.filter(created_at__gte=last_30d).count(),
        'category_stats':  Seller.objects.values('category').annotate(count=Count('id')).order_by('-count'),
        'premium_count': premium_count, 'total_sellers': total_sellers,
        'monthly_revenue': premium_count * platform.premium_monthly_price,
        'open_disputes_count': open_disputes_count, 'pending_payouts_count': pending_payouts_count,
    })


@staff_member_required
def admin_disputes(request):
    disputes      = Dispute.objects.select_related('order', 'order__seller').order_by('-created_at')
    status_filter = request.GET.get('status', '')
    if status_filter:
        disputes = disputes.filter(status=status_filter)
    open_count            = Dispute.objects.filter(status='open').count()
    open_disputes_count   = Dispute.objects.filter(status__in=['open', 'vendor_replied', 'under_review']).count()
    pending_payouts_count = Order.objects.filter(payout_triggered=False, status__in=['delivered', 'completed']).count()
    return render(request, 'admin_dashboard/disputes.html', {
        'disputes': disputes[:100], 'status_filter': status_filter, 'open_count': open_count,
        'open_disputes_count': open_disputes_count, 'pending_payouts_count': pending_payouts_count,
    })


@staff_member_required
@require_http_methods(["POST"])
def resolve_dispute(request, dispute_id):
    dispute = get_object_or_404(Dispute, id=dispute_id)
    order   = dispute.order
    action  = request.POST.get('action')
    note    = request.POST.get('admin_note', '').strip()

    dispute.admin_note  = note
    dispute.resolved_at = timezone.now()

    if action == 'refund_buyer':
        dispute.status = 'resolved_buyer'
        order.status   = 'refunded'
        order.save()
        dispute.save()
        # ── NEW: notify buyer of refund decision ──
        try:
            send_dispute_resolved_buyer(
                to_email=order.buyer_email,
                buyer_name=order.buyer_name,
                order_ref=str(order.order_ref)[:8].upper(),
                admin_note=note,
            )
        except Exception as e:
            logger.error(f"Dispute resolved buyer email failed: {e}")
        messages.success(request, f'Dispute resolved — refund issued to buyer for order {str(order.order_ref)[:8].upper()}.')

    elif action == 'pay_vendor':
        dispute.status = 'resolved_vendor'
        dispute.save()
        order.status   = 'delivered'
        order.save()
        _trigger_payout(order)
        # ── NEW: notify vendor of payout decision ──
        try:
            send_dispute_resolved_vendor(
                to_email=order.seller.email,
                business_name=order.seller.business_name,
                order_ref=str(order.order_ref)[:8].upper(),
                admin_note=note,
            )
        except Exception as e:
            logger.error(f"Dispute resolved vendor email failed: {e}")
        messages.success(request, f'Dispute resolved — payment released to vendor for order {str(order.order_ref)[:8].upper()}.')

    elif action == 'under_review':
        dispute.status = 'under_review'
        dispute.save()
        messages.info(request, 'Dispute marked as under review.')

    else:
        messages.error(request, 'Invalid action.')

    return redirect('admin_disputes')


@staff_member_required
def admin_orders(request):
    orders        = Order.objects.select_related('seller').prefetch_related('items').order_by('-created_at')
    status_filter = request.GET.get('status', '')
    payout_filter = request.GET.get('payout', '')
    search        = request.GET.get('search', '').strip()
    if status_filter:
        orders = orders.filter(status=status_filter)
    if payout_filter == 'pending':
        orders = orders.filter(payout_triggered=False, status__in=['delivered', 'completed'])
    if search:
        orders = orders.filter(
            Q(order_ref__icontains=search) | Q(buyer_name__icontains=search)
            | Q(buyer_email__icontains=search) | Q(flutterwave_tx_ref__icontains=search)
            | Q(seller__business_name__icontains=search)
        )
    open_disputes_count   = Dispute.objects.filter(status__in=['open', 'vendor_replied', 'under_review']).count()
    pending_payouts_count = Order.objects.filter(payout_triggered=False, status__in=['delivered', 'completed']).count()
    return render(request, 'admin_dashboard/orders.html', {
        'orders': orders[:200], 'status_filter': status_filter,
        'open_disputes_count': open_disputes_count, 'pending_payouts_count': pending_payouts_count,
    })


@staff_member_required
def admin_payouts(request):
    pending_orders        = Order.objects.filter(
        payout_triggered=False, status__in=['delivered', 'completed']
    ).select_related('seller', 'seller__bank_account').order_by('delivered_at')
    recent_payouts        = Order.objects.filter(payout_triggered=True).select_related('seller').order_by('-payout_at')[:20]
    total_pending_amount  = pending_orders.aggregate(t=Sum('vendor_payout'))['t'] or Decimal('0')
    pending_payouts_count = pending_orders.count()
    open_disputes_count   = Dispute.objects.filter(status__in=['open', 'vendor_replied', 'under_review']).count()
    return render(request, 'admin_dashboard/payouts.html', {
        'pending_orders': pending_orders, 'recent_payouts': recent_payouts,
        'total_pending_amount': total_pending_amount,
        'pending_payouts_count': pending_payouts_count, 'open_disputes_count': open_disputes_count,
    })


@staff_member_required
@require_http_methods(["POST"])
def admin_trigger_payout(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if order.payout_triggered:
        messages.warning(request, f'Payout already sent for order #{str(order.order_ref)[:8].upper()}.')
        return redirect(request.META.get('HTTP_REFERER', 'admin_payouts'))
    if order.status not in ('delivered', 'completed'):
        messages.error(request, 'Can only pay out delivered or completed orders.')
        return redirect(request.META.get('HTTP_REFERER', 'admin_payouts'))
    _trigger_payout(order)
    if order.payout_triggered:
        messages.success(request, f'✅ Payout sent for order #{str(order.order_ref)[:8].upper()} → {order.seller.business_name}')
    else:
        messages.error(request, f'❌ Payout failed for order #{str(order.order_ref)[:8].upper()}. Check logs.')
    return redirect(request.META.get('HTTP_REFERER', 'admin_payouts'))


@staff_member_required
@require_http_methods(["POST"])
def admin_mark_delivered(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if order.status not in ('shipped', 'paid'):
        messages.error(request, 'Only shipped or paid orders can be marked delivered.')
        return redirect(request.META.get('HTTP_REFERER', 'admin_orders'))
    order.status       = 'delivered'
    order.delivered_at = timezone.now()
    order.save()
    _trigger_payout(order)
    messages.success(request, f'Order #{str(order.order_ref)[:8].upper()} marked as delivered. Payout triggered.')
    return redirect(request.META.get('HTTP_REFERER', 'admin_orders'))


@staff_member_required
@require_http_methods(["POST"])
def admin_mark_refunded(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if order.status == 'refunded':
        messages.info(request, 'Order is already refunded.')
        return redirect(request.META.get('HTTP_REFERER', 'admin_orders'))
    order.status = 'refunded'
    order.save()
    messages.success(request, f'Order #{str(order.order_ref)[:8].upper()} marked as refunded.')
    return redirect(request.META.get('HTTP_REFERER', 'admin_orders'))


@staff_member_required
@require_http_methods(["POST"])
def admin_product_action(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    action  = request.POST.get('action', '')
    if action == 'archive':
        product.is_archived = True
        product.save(update_fields=['is_archived'])
        messages.success(request, 'Product archived.')
    elif action == 'restore':
        product.is_archived = False
        product.is_sold_out = False
        product.save(update_fields=['is_archived', 'is_sold_out'])
        messages.success(request, 'Product restored.')
    elif action == 'sold_out':
        product.is_sold_out = True
        product.save(update_fields=['is_sold_out'])
        messages.success(request, 'Product marked as sold out.')
    elif action == 'available':
        product.is_sold_out = False
        product.save(update_fields=['is_sold_out'])
        messages.success(request, 'Product marked as available.')
    else:
        messages.error(request, 'Unknown action.')
    return redirect(request.META.get('HTTP_REFERER', 'admin_products'))


@staff_member_required
def admin_reviews(request):
    reviews         = Review.objects.select_related('order', 'seller').order_by('-created_at')
    rating_filter   = request.GET.get('rating', '')
    verified_filter = request.GET.get('verified', '')
    if rating_filter:
        reviews = reviews.filter(rating=int(rating_filter))
    if verified_filter == '1':
        reviews = reviews.filter(is_verified=True)
    elif verified_filter == '0':
        reviews = reviews.filter(is_verified=False)
    open_disputes_count   = Dispute.objects.filter(status__in=['open', 'vendor_replied', 'under_review']).count()
    pending_payouts_count = Order.objects.filter(payout_triggered=False, status__in=['delivered', 'completed']).count()
    return render(request, 'admin_dashboard/reviews.html', {
        'reviews': reviews[:200], 'rating_filter': rating_filter,
        'verified_filter': verified_filter,
        'open_disputes_count': open_disputes_count, 'pending_payouts_count': pending_payouts_count,
    })


@staff_member_required
@require_http_methods(["POST"])
def admin_delete_review(request, review_id):
    review      = get_object_or_404(Review, id=review_id)
    seller_name = review.seller.business_name
    review.delete()
    messages.success(request, f'Review deleted from {seller_name}.')
    return redirect('admin_reviews')


@staff_member_required
def admin_bank_accounts(request):
    accounts        = VendorBankAccount.objects.select_related('seller').order_by('-created_at')
    search          = request.GET.get('search', '').strip()
    verified_filter = request.GET.get('verified', '')
    if search:
        accounts = accounts.filter(
            Q(seller__business_name__icontains=search) | Q(account_name__icontains=search)
            | Q(bank_name__icontains=search) | Q(account_number__icontains=search)
        )
    if verified_filter == '1':
        accounts = accounts.filter(is_verified=True)
    elif verified_filter == '0':
        accounts = accounts.filter(is_verified=False)
    unverified_count      = VendorBankAccount.objects.filter(is_verified=False).count()
    open_disputes_count   = Dispute.objects.filter(status__in=['open', 'vendor_replied', 'under_review']).count()
    pending_payouts_count = Order.objects.filter(payout_triggered=False, status__in=['delivered', 'completed']).count()
    return render(request, 'admin_dashboard/bank_accounts.html', {
        'accounts': accounts, 'unverified_count': unverified_count,
        'open_disputes_count': open_disputes_count, 'pending_payouts_count': pending_payouts_count,
    })


@staff_member_required
@require_http_methods(["POST"])
def admin_verify_bank_account(request, account_id):
    account = get_object_or_404(VendorBankAccount, id=account_id)
    action  = request.POST.get('action', 'verify')
    if action == 'verify':
        account.is_verified = True
        account.save(update_fields=['is_verified'])
        messages.success(request, f'✅ Account verified for {account.seller.business_name}.')
    elif action == 'unverify':
        account.is_verified = False
        account.save(update_fields=['is_verified'])
        messages.warning(request, f'⚠️ Account unverified for {account.seller.business_name}.')
    return redirect(request.META.get('HTTP_REFERER', 'admin_bank_accounts'))


@staff_member_required
def admin_settings(request):
    settings_obj = PlatformSettings.get()

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'update_fee':
            raw = request.POST.get('transaction_fee_percent', '').strip()
            try:
                new_fee = Decimal(raw)
                if new_fee < 0 or new_fee > 30:
                    messages.error(request, 'Fee must be between 0% and 30%.')
                else:
                    settings_obj.transaction_fee_percent = new_fee
                    settings_obj.save()
                    messages.success(request, f'✅ Transaction fee updated to {new_fee}%.')
            except Exception:
                messages.error(request, 'Invalid fee value.')

        elif action == 'update_premium_price':
            raw = request.POST.get('premium_monthly_price', '').strip()
            try:
                new_price = Decimal(raw)
                if new_price < 0:
                    messages.error(request, 'Price cannot be negative.')
                else:
                    settings_obj.premium_monthly_price = new_price
                    settings_obj.save()
                    messages.success(request, f'✅ Premium price updated to ₦{new_price:,.0f}/month.')
            except Exception:
                messages.error(request, 'Invalid price value.')

        elif action == 'reset_all_analytics':
            updated = Seller.objects.filter(is_staff=False, is_superuser=False).update(
                weekly_page_views=0, weekly_whatsapp_clicks=0,
                last_analytics_reset=timezone.now()
            )
            messages.success(request, f'📊 Weekly analytics reset for {updated} seller(s).')

        elif action == 'run_auto_release':
            auto_release_expired_orders()
            messages.success(request, '💸 Auto-release complete.')

        else:
            messages.error(request, 'Unknown action.')

        return redirect('admin_settings')

    premium_count         = Seller.objects.filter(subscription_type='premium', is_staff=False, is_superuser=False).count()
    total_sellers         = Seller.objects.filter(is_active=True, is_staff=False, is_superuser=False).count()
    open_disputes_count   = Dispute.objects.filter(status__in=['open', 'vendor_replied', 'under_review']).count()
    pending_payouts_count = Order.objects.filter(payout_triggered=False, status__in=['delivered', 'completed']).count()
    return render(request, 'admin_dashboard/settings.html', {
        'settings': settings_obj, 'premium_count': premium_count, 'total_sellers': total_sellers,
        'monthly_revenue': premium_count * settings_obj.premium_monthly_price,
        'open_disputes_count': open_disputes_count, 'pending_payouts_count': pending_payouts_count,
    })