
"""
sellers/flutterwave.py

Flutterwave integration for VendoPage.
Handles:
  - Subscription payments (existing)
  - Order payments: both escrow and direct-pay flows
  - Webhook signature verification (fixed)
  - Payout / transfer to vendor bank account
  - Multi-currency support 
"""

import hashlib
import hmac
import logging
import requests
from decimal import Decimal
from django.conf import settings

logger = logging.getLogger(__name__)


# ── Currency config ──────────────────────────────────────────
# Maps seller.currency_code → Flutterwave currency string
SUPPORTED_CURRENCIES = {
    'NGN': 'NGN',
    'GHS': 'GHS',
    'KES': 'KES',
    'ZAR': 'ZAR',
    'USD': 'USD',
    'GBP': 'GBP',
    'EUR': 'EUR',
}

DEFAULT_CURRENCY = 'NGN'


def resolve_currency(currency_code: str) -> str:
    """Return a Flutterwave-supported currency string, falling back to NGN."""
    return SUPPORTED_CURRENCIES.get((currency_code or '').upper(), DEFAULT_CURRENCY)


# ── Main client ──────────────────────────────────────────────
class FlutterwavePayment:
    BASE_URL = "https://api.flutterwave.com/v3"

    def __init__(self):
        self.public_key = settings.FLUTTERWAVE_PUBLIC_KEY
        self.secret_key = settings.FLUTTERWAVE_SECRET_KEY
        # Secret hash set in Flutterwave dashboard → Settings → Webhooks
        self.webhook_secret_hash = getattr(settings, 'FLW_SECRET_HASH', '')

    # ── Headers helper ───────────────────────────────────────
    def _headers(self):
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    # ── Subscription payment init ────────────────────────────
    def initialize_payment(
        self,
        email: str,
        amount,
        tx_ref: str,
        redirect_url: str,
        customer_name: str,
        currency: str = 'NGN',
        
        title: str = "VendoPage Premium Subscription",
        description: str = "Monthly premium subscription",
    ) -> dict:
        """Initialize a Flutterwave hosted-payment page."""
        url = f"{self.BASE_URL}/payments"
        currency = resolve_currency(currency)

        payload = {
            "tx_ref": tx_ref,
            "amount": str(amount),
            "currency": currency,
            "redirect_url": redirect_url,
            "customer": {
                "email": email,
                "name": customer_name,
            },
            "customizations": {
                "title": title,
                "description": description,
                "logo": getattr(settings, 'SITE_LOGO_URL', ''),
            },
        }

        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error("FLW initialize_payment error: %s", e)
            return {"status": "error", "message": str(e)}

    # ── Order / escrow payment init ──────────────────────────
    def initialize_order_payment(
        self,
        order,          # sellers.models.Order instance
        redirect_url: str,
    ) -> dict:
        """
        Initialize a payment for a buyer order.
        Works for both escrow and direct payment types —
        the payment page is identical; the difference is in the webhook handler.
        """
        currency = resolve_currency(order.currency)
        title = f"Order from {order.seller.business_name}"
        description = (
            f"{'Protected' if order.payment_type == 'escrow' else 'Direct'} payment "
            f"— {order.items.count()} item(s)"
        )

        return self.initialize_payment(
            email=order.buyer_email,
            amount=order.subtotal,
            tx_ref=order.flutterwave_tx_ref,
            redirect_url=redirect_url,
            customer_name=order.buyer_name,
            currency=currency,
            title=title,
            description=description,
        )

    # ── Verify a transaction by ID ───────────────────────────
    def verify_payment(self, transaction_id) -> dict:
        """Verify a payment transaction by Flutterwave transaction ID."""
        url = f"{self.BASE_URL}/transactions/{transaction_id}/verify"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error("FLW verify_payment error: %s", e)
            return {"status": "error", "message": str(e)}

    # ── Verify a transaction by tx_ref ───────────────────────
    def verify_by_tx_ref(self, tx_ref: str) -> dict:
        """Verify by the transaction reference we generated."""
        url = f"{self.BASE_URL}/transactions/verify_by_reference"
        try:
            resp = requests.get(
                url, params={"tx_ref": tx_ref}, headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error("FLW verify_by_tx_ref error: %s", e)
            return {"status": "error", "message": str(e)}

    # ── Webhook signature verification (FIXED) ───────────────
    def verify_webhook_signature(self, request_signature: str, payload_body: bytes) -> bool:
        """
        Verify Flutterwave webhook using the secret hash method.

        Flutterwave sends the secret hash in the 'verif-hash' header.
        Simply compare the incoming header value to your stored FLW_SECRET_HASH.

        NOTE: Flutterwave does NOT use HMAC for webhook verification —
        it sends the raw secret hash as a plain header value.
        The old HMAC approach was incorrect and always failed.
        """
        if not self.webhook_secret_hash:
            logger.warning("FLW_SECRET_HASH not configured — webhook verification skipped")
            return False

        return hmac.compare_digest(
            request_signature.strip(),
            self.webhook_secret_hash.strip(),
        )

    # ── Process webhook event ────────────────────────────────
    def process_order_webhook(self, event_data: dict) -> dict:
        """
        Parse a charge.completed webhook and return an action dict.

        Returns:
            {
                'action':     'escrow_hold' | 'direct_payout' | 'ignore',
                'tx_ref':     str,
                'tx_id':      str | None,
                'amount':     Decimal,
                'currency':   str,
                'status':     str,
            }
        """
        event = event_data.get('event', '')
        data  = event_data.get('data', {})

        if event != 'charge.completed':
            return {'action': 'ignore', 'reason': f'unhandled event: {event}'}

        if data.get('status') != 'successful':
            return {'action': 'ignore', 'reason': 'payment not successful'}

        tx_ref   = data.get('tx_ref', '')
        tx_id    = str(data.get('id', ''))
        amount   = Decimal(str(data.get('amount', 0)))
        currency = data.get('currency', 'NGN')

        # Determine action by looking up the order's payment_type
        from sellers.models import Order  # local import to avoid circular
        try:
            order = Order.objects.get(flutterwave_tx_ref=tx_ref)
        except Order.DoesNotExist:
            return {'action': 'ignore', 'reason': f'order not found for tx_ref={tx_ref}'}

        if order.payment_verified:
            return {'action': 'ignore', 'reason': 'already processed'}

        action = 'direct_payout' if order.payment_type == 'direct' else 'escrow_hold'

        return {
            'action':   action,
            'order':    order,
            'tx_ref':   tx_ref,
            'tx_id':    tx_id,
            'amount':   amount,
            'currency': currency,
            'status':   'successful',
        }

    # ── Trigger vendor payout (transfer) ────────────────────
    def transfer_to_vendor(self, order) -> dict:
        """
        Send vendor_payout to seller's bank account via Flutterwave Transfers.
        Requires order.seller.bank_account to exist.

        Returns the raw Flutterwave API response dict.
        """
        try:
            bank = order.seller.bank_account
        except Exception:
            logger.error("No bank account for seller %s", order.seller.business_name)
            return {"status": "error", "message": "Seller has no bank account configured"}

        currency = resolve_currency(order.currency)
        url      = f"{self.BASE_URL}/transfers"

        payload = {
            "account_bank":   bank.bank_code,
            "account_number": bank.account_number,
            "amount":         float(order.vendor_payout),
            "narration":      f"VendoPage payout — Order {order.order_ref}",
            "currency":       currency,
            "reference":      f"payout-{order.order_ref}",
            "beneficiary_name": bank.account_name,
            "meta": {
                "order_ref":   order.order_ref,
                "seller_id":   order.seller.id,
                "payment_type": order.payment_type,
            },
        }

        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            result = resp.json()
            logger.info(
                "FLW transfer initiated for order %s: %s",
                order.order_ref, result.get('data', {}).get('id')
            )
            return result
        except requests.exceptions.RequestException as e:
            logger.error("FLW transfer_to_vendor error for order %s: %s", order.order_ref, e)
            return {"status": "error", "message": str(e)}

    # ── Get list of supported banks ──────────────────────────
    def get_banks(self, country: str = 'NG') -> list:
        """Fetch list of banks for a given country code."""
        url = f"{self.BASE_URL}/banks/{country}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get('data', [])
        except requests.exceptions.RequestException as e:
            logger.error("FLW get_banks error: %s", e)
            return []

    # ── Verify bank account number ───────────────────────────
    def verify_bank_account(self, account_number: str, bank_code: str) -> dict:
        """Resolve an account number to an account name."""
        url = f"{self.BASE_URL}/accounts/resolve"
        payload = {
            "account_number": account_number,
            "account_bank":   bank_code,
        }
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error("FLW verify_bank_account error: %s", e)
            return {"status": "error", "message": str(e)}


# ── Convenience singleton ────────────────────────────────────
flw = FlutterwavePayment()
