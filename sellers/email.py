# sellers/email.py
import os
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from django.conf import settings

SITE_URL = 'https://www.vendopage.com'
SUPPORT_EMAIL = 'support@vendopage.com'

# Templates directory — sits next to this file: sellers/email_templates/
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'email_templates')


def _load_template(filename):
    path = os.path.join(TEMPLATE_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _render(filename, context):
    """Simple {{key}} → value replacement. No Django template engine needed."""
    html = _load_template(filename)
    for key, value in context.items():
        html = html.replace('{{' + key + '}}', str(value))
    return html


def send_email_via_brevo(to_email, subject, html_content, text_content=None):
    try:
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = settings.BREVO_API_KEY

        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )

        if not text_content:
            from django.utils.html import strip_tags
            text_content = strip_tags(html_content)

        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": to_email}],
            sender={"email": SUPPORT_EMAIL, "name": "Vendopage"},
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

        response = api_instance.send_transac_email(send_smtp_email)
        print(f"✅ Email sent to {to_email} (ID: {response.message_id})")
        return True

    except ApiException as e:
        print(f"❌ Brevo API error: {e}")
        return False
    except Exception as e:
        print(f"❌ Email error: {type(e).__name__}: {str(e)}")
        return False


def _build_order_items_html(items, currency=''):
    """Render order items as clean inline HTML rows for email templates."""
    rows = ''
    for item in items:
        try:
            line_total = f"{currency}{float(item.price) * item.quantity:,.0f}"
        except Exception:
            line_total = ''
        rows += f'''
            <tr>
              <td style="padding:10px 0;border-bottom:1px solid #eeeeee;">
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td>
                      <p style="margin:0;font-size:14px;font-weight:600;color:#0A0A0A;">{item.product_name}</p>
                      <p style="margin:2px 0 0;font-size:12px;color:#999999;">Qty: {item.quantity}</p>
                    </td>
                    <td align="right">
                      <p style="margin:0;font-size:14px;font-weight:700;color:#0A0A0A;">{line_total}</p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>'''
    return rows


# ─────────────────────────────────────────────
# 1. PASSWORD RESET
# ─────────────────────────────────────────────
def send_password_reset_email(to_email, business_name, reset_code):
    html = _render('password_reset.html', {
        'business_name': business_name,
        'reset_code': reset_code,
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject='Your Vendopage password reset code',
        html_content=html,
    )


# ─────────────────────────────────────────────
# 2. WELCOME
# ─────────────────────────────────────────────
def send_welcome_email(to_email, business_name, store_url):
    html = _render('welcome.html', {
        'business_name': business_name,
        'store_url': store_url,
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f'{business_name}, your Vendopage store is live!',
        html_content=html,
    )


# ─────────────────────────────────────────────
# 3. FIRST PRODUCT UPLOADED
# ─────────────────────────────────────────────
def send_first_product_email(to_email, business_name, store_url):
    html = _render('first_product.html', {
        'business_name': business_name,
        'store_url': store_url,
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject='Your product is live — keep going!',
        html_content=html,
    )


# ─────────────────────────────────────────────
# 4. FIRST WHATSAPP CLICK
# ─────────────────────────────────────────────
def send_first_whatsapp_click_email(to_email, business_name, store_url):
    html = _render('first_whatsapp_click.html', {
        'business_name': business_name,
        'store_url': store_url,
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject='Someone just clicked to order from you on Vendopage!',
        html_content=html,
    )


# ─────────────────────────────────────────────
# 5. WEEKLY SUMMARY
# ─────────────────────────────────────────────
def send_weekly_summary_email(to_email, business_name, store_url,
                               page_views, whatsapp_clicks, active_products,
                               prev_page_views=0):
    views_change = page_views - prev_page_views
    if views_change > 0:
        trend = f'+{views_change} from last week'
        trend_color = '#16a34a'
    elif views_change < 0:
        trend = f'{views_change} from last week'
        trend_color = '#dc2626'
    else:
        trend = 'same as last week'
        trend_color = '#888888'

    if page_views < 20:
        low_views_tip = '''
  <tr>
    <td style="padding:0 0 32px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="background:#f7f7f7;border-left:3px solid #0A0A0A;border-radius:0 8px 8px 0;padding:18px 22px;">
            <p style="margin:0 0 5px;font-size:11px;font-weight:700;color:#0A0A0A;text-transform:uppercase;letter-spacing:.8px;">Tip</p>
            <p style="margin:0;font-size:14px;color:#555555;line-height:1.6;">
              Sellers who share their store link on WhatsApp Status every week see 2x more visitors. Try it today — it takes 30 seconds.
            </p>
          </td>
        </tr>
      </table>
    </td>
  </tr>'''
    else:
        low_views_tip = ''

    html = _render('weekly_summary.html', {
        'business_name':   business_name,
        'store_url':       store_url,
        'page_views':      page_views,
        'whatsapp_clicks': whatsapp_clicks,
        'active_products': active_products,
        'trend':           trend,
        'trend_color':     trend_color,
        'low_views_tip':   low_views_tip,
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f'Your Vendopage week: {page_views} views, {whatsapp_clicks} WhatsApp clicks',
        html_content=html,
    )


# ─────────────────────────────────────────────
# 6. RE-ENGAGEMENT
# ─────────────────────────────────────────────
def send_reengagement_email(to_email, business_name, store_url, days_inactive=5):
    html = _render('reengagement.html', {
        'business_name': business_name,
        'store_url':     store_url,
        'days_inactive': days_inactive,
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f"{business_name}, your store hasn't been updated in {days_inactive} days",
        html_content=html,
    )


# ─────────────────────────────────────────────
# 7. ORDER CONFIRMED — BUYER
# ─────────────────────────────────────────────

def send_order_confirmed_buyer(to_email, buyer_name, order_ref, seller_name,
                                items, subtotal, currency, payment_type='escrow'):
    order_items_html = _build_order_items_html(items, currency)

    if payment_type == 'direct':
        payment_notice = '''
        <tr>
          <td style="padding-bottom:36px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#fefce8;border-left:3px solid #f59e0b;border-radius:0 8px 8px 0;padding:18px 22px;">
                  <p style="margin:0 0 5px;font-size:11px;font-weight:700;color:#92400e;text-transform:uppercase;letter-spacing:.8px;">⚡ Direct Payment</p>
                  <p style="margin:0;font-size:14px;color:#555555;line-height:1.6;">
                    Your payment has gone directly to the seller. They will contact you shortly to arrange delivery.
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>'''
    else:
        payment_notice = '''
        <tr>
          <td style="padding-bottom:36px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#f7f7f7;border-left:3px solid #0A0A0A;border-radius:0 8px 8px 0;padding:18px 22px;">
                  <p style="margin:0 0 5px;font-size:11px;font-weight:700;color:#0A0A0A;text-transform:uppercase;letter-spacing:.8px;">Your money is safe</p>
                  <p style="margin:0;font-size:14px;color:#555555;line-height:1.6;">
                    Your funds are held in escrow. They are only released to the seller after you confirm delivery. If anything goes wrong, you can raise a dispute.
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>'''

    html = _render('order_confirmed_buyer.html', {
        'buyer_name':       buyer_name,
        'order_ref':        order_ref,
        'seller_name':      seller_name,
        'currency':         currency,
        'subtotal':         f'{float(subtotal):,.0f}',
        'order_items_html': order_items_html,
        'payment_notice':   payment_notice,
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f'Order #{order_ref} confirmed — {seller_name}',
        html_content=html,
    )

# ─────────────────────────────────────────────
# 8. NEW ORDER — VENDOR
# ─────────────────────────────────────────────
def send_new_order_vendor(to_email, business_name, buyer_name, order_ref,
                           items, subtotal, currency, dashboard_url):
    """Sent to vendor when a new paid order comes in."""
    order_items_html = _build_order_items_html(items, currency)
    html = _render('new_order_vendor.html', {
        'business_name':    business_name,
        'buyer_name':       buyer_name,
        'order_ref':        order_ref,
        'currency':         currency,
        'subtotal':         f'{float(subtotal):,.0f}',
        'order_items_html': order_items_html,
        'dashboard_url':    dashboard_url,
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f'New order #{order_ref} — {currency}{float(subtotal):,.0f}',
        html_content=html,
    )


# ─────────────────────────────────────────────
# 9. ORDER SHIPPED — BUYER
# ─────────────────────────────────────────────
def send_order_shipped_buyer(to_email, buyer_name, order_ref, seller_name,
                              tracking_info, courier_name, order_url):
    """Sent to buyer when vendor marks order as shipped."""
    html = _render('order_shipped_buyer.html', {
        'buyer_name':    buyer_name,
        'order_ref':     order_ref,
        'seller_name':   seller_name,
        'tracking_info': tracking_info or '—',
        'courier_name':  courier_name or '—',
        'order_url':     order_url,
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f'Your order #{order_ref} has been shipped',
        html_content=html,
    )


# ─────────────────────────────────────────────
# 10. PAYOUT SENT — VENDOR
# ─────────────────────────────────────────────
def send_payment_sent_vendor(to_email, business_name, amount, currency,
                              order_ref, bank_name, account_number):
    """Sent to vendor when payout is triggered."""
    html = _render('payout_sent_vendor.html', {
        'business_name': business_name,
        'order_ref':     order_ref,
        'currency':      currency,
        'amount':        f'{float(amount):,.0f}',
        'bank_name':     bank_name,
        'account_last4': str(account_number)[-4:],
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f'Payment sent — {currency}{float(amount):,.0f} for order #{order_ref}',
        html_content=html,
    )


# ─────────────────────────────────────────────
# 11 & 12. DISPUTE OPENED — VENDOR + BUYER
# ─────────────────────────────────────────────
def send_dispute_opened(vendor_email, buyer_email, order_ref, reason,
                         buyer_name='there'):
    """Sent to both parties when a dispute is raised."""
    vendor_html = _render('dispute_opened_vendor.html', {
        'order_ref': order_ref,
        'reason':    reason,
    })
    send_email_via_brevo(
        to_email=vendor_email,
        subject=f'Dispute opened on order #{order_ref}',
        html_content=vendor_html,
    )

    buyer_html = _render('dispute_opened_buyer.html', {
        'buyer_name': buyer_name,
        'order_ref':  order_ref,
        'reason':     reason,
    })
    send_email_via_brevo(
        to_email=buyer_email,
        subject=f'Your dispute on order #{order_ref} has been received',
        html_content=buyer_html,
    )


# ─────────────────────────────────────────────
# 13. DISPUTE RESOLVED — BUYER (refund)
# ─────────────────────────────────────────────
def send_dispute_resolved_buyer(to_email, buyer_name, order_ref, admin_note=''):
    """Sent to buyer when admin resolves dispute in their favour."""
    html = _render('dispute_resolved_buyer.html', {
        'buyer_name': buyer_name,
        'order_ref':  order_ref,
        'admin_note': admin_note or 'Our team reviewed the case and resolved it in your favour.',
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f'Dispute resolved — refund issued for order #{order_ref}',
        html_content=html,
    )


# ─────────────────────────────────────────────
# 14. DISPUTE RESOLVED — VENDOR (paid out)
# ─────────────────────────────────────────────
def send_dispute_resolved_vendor(to_email, business_name, order_ref, admin_note=''):
    """Sent to vendor when admin resolves dispute in their favour."""
    html = _render('dispute_resolved_vendor.html', {
        'business_name': business_name,
        'order_ref':     order_ref,
        'admin_note':    admin_note or 'Our team reviewed the case and resolved it in your favour.',
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f'Dispute resolved — payment released for order #{order_ref}',
        html_content=html,
    )


# ─────────────────────────────────────────────
# 15. PREMIUM UPGRADE CONFIRMED
# ─────────────────────────────────────────────
def send_premium_upgrade_email(to_email, business_name, expires_date):
    """Sent to seller immediately after successful premium payment."""
    html = _render('premium_upgrade.html', {
        'business_name': business_name,
        'expires_date':  expires_date,
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f'{business_name}, you are now Premium ⭐',
        html_content=html,
    )


# ─────────────────────────────────────────────
# 16. PREMIUM EXPIRY WARNING
# ─────────────────────────────────────────────
def send_premium_expiry_warning(to_email, business_name, expires_date, days_left):
    """Sent 3 days before premium subscription expires. Call from a management command."""
    html = _render('premium_expiry_warning.html', {
        'business_name': business_name,
        'expires_date':  expires_date,
        'days_left':     days_left,
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f'Your Vendopage Premium expires in {days_left} days',
        html_content=html,
    )


# ─────────────────────────────────────────────
# 17. ORDER AUTO-RELEASED — BUYER
# ─────────────────────────────────────────────
def send_order_auto_released_buyer(to_email, buyer_name, order_ref, seller_name):
    """Sent to buyer when 72-hour window passes and funds auto-release to vendor."""
    html = _render('order_auto_released_buyer.html', {
        'buyer_name':  buyer_name,
        'order_ref':   order_ref,
        'seller_name': seller_name,
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f'Your order #{order_ref} has been completed',
        html_content=html,
    )


# ─────────────────────────────────────────────
# 18. REVIEW RECEIVED — VENDOR
# ─────────────────────────────────────────────
def send_review_received_vendor(to_email, business_name, order_ref,
                                 rating, comment):
    """Sent to vendor when a buyer submits a review."""
    stars_display = ('★' * rating) + ('☆' * (5 - rating))
    html = _render('review_received_vendor.html', {
        'business_name': business_name,
        'order_ref':     order_ref,
        'rating':        rating,
        'stars_display': stars_display,
        'comment':       comment or 'No comment left.',
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f'New {rating}★ review on your store',
        html_content=html,
    )