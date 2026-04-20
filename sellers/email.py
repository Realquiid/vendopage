# sellers/email.py
import os
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from django.conf import settings

SITE_URL = 'https://vendopage.com'
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

    # Only inject the tip row when views are low
    if page_views < 20:
        low_views_tip = '''
  <tr>
    <td style="padding:16px 48px 0;">
      <p style="margin:0;font-size:15px;color:#444444;line-height:1.7;">
        <strong style="color:#111111;">Tip:</strong> Sellers who share their store link on WhatsApp Status every week see 2x more visitors. Try it today — it takes 30 seconds.
      </p>
    </td>
  </tr>'''
    else:
        low_views_tip = ''

    html = _render('weekly_summary.html', {
        'business_name': business_name,
        'store_url': store_url,
        'page_views': page_views,
        'whatsapp_clicks': whatsapp_clicks,
        'active_products': active_products,
        'trend': trend,
        'trend_color': trend_color,
        'low_views_tip': low_views_tip,
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f'Your Vendopage week: {page_views} views, {whatsapp_clicks} WhatsApp clicks',
        html_content=html,
    )


# ─────────────────────────────────────────────
# 6. RE-ENGAGEMENT (5 days inactive)
# ─────────────────────────────────────────────
def send_reengagement_email(to_email, business_name, store_url, days_inactive=5):
    html = _render('reengagement.html', {
        'business_name': business_name,
        'store_url': store_url,
        'days_inactive': days_inactive,
    })
    return send_email_via_brevo(
        to_email=to_email,
        subject=f"{business_name}, your store hasn't been updated in {days_inactive} days",
        html_content=html,
    )