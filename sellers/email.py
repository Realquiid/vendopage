# sellers/email.py
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from django.conf import settings


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
            sender={"email": "support@vendopage.com", "name": "Vendopage"},
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


def send_password_reset_email(to_email, business_name, reset_code):
    html_content = f'''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;background:#f5f5f7;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f7;padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,.08);">
        <tr>
          <td style="background:#00C853;padding:32px 40px;text-align:center;">
            <h1 style="margin:0;color:#ffffff;font-size:28px;font-weight:800;letter-spacing:-0.5px;">Vendopage</h1>
            <p style="margin:6px 0 0;color:rgba(255,255,255,.75);font-size:13px;">WhatsApp Product Catalog</p>
          </td>
        </tr>
        <tr>
          <td style="padding:36px 40px;">
            <h2 style="margin:0 0 12px;color:#0A0A0A;font-size:20px;font-weight:700;">Password Reset</h2>
            <p style="margin:0 0 24px;color:#6b7280;font-size:15px;line-height:1.6;">Hi {business_name}, use the code below to reset your password.</p>
            <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
              <tr>
                <td align="center" style="background:#f0fff5;border:1.5px solid #bbf7d0;border-radius:10px;padding:28px;">
                  <p style="margin:0 0 6px;color:#6b7280;font-size:12px;text-transform:uppercase;letter-spacing:1.5px;font-weight:600;">Your Reset Code</p>
                  <p style="margin:0;color:#00a844;font-size:44px;font-weight:800;letter-spacing:10px;font-family:'Courier New',monospace;">{reset_code}</p>
                </td>
              </tr>
            </table>
            <p style="margin:0 0 8px;color:#6b7280;font-size:13px;line-height:1.6;">This code expires in <strong>10 minutes</strong>.</p>
            <p style="margin:0;color:#6b7280;font-size:13px;line-height:1.6;">If you didn't request this, you can safely ignore this email.</p>
          </td>
        </tr>
        <tr>
          <td style="background:#f9fafb;padding:20px 40px;border-top:1px solid #e5e7eb;">
            <p style="margin:0;color:#9ca3af;font-size:12px;text-align:center;">© 2026 Vendopage · support@vendopage.com</p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
    '''
    return send_email_via_brevo(
        to_email=to_email,
        subject='Vendopage — Your Password Reset Code',
        html_content=html_content
    )