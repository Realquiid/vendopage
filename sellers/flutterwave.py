# sellers/flutterwave.py

# Flutterwave integration for VendoPage.
# Handles:
#   - Subscription payments
#   - Order payments (escrow and direct)
#   - Webhook signature verification
#   - Payout via Transfer API (requires static IP whitelisted in FLW dashboard)
#   - Bank account verification
# """

import hmac
import hashlib
import logging
import requests
from decimal import Decimal
from django.conf import settings

logger = logging.getLogger(__name__)

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
    return SUPPORTED_CURRENCIES.get((currency_code or '').upper(), DEFAULT_CURRENCY)


class FlutterwavePayment:
    BASE_URL = "https://api.flutterwave.com/v3"

    def __init__(self):
        self.public_key          = settings.FLUTTERWAVE_PUBLIC_KEY
        self.secret_key          = settings.FLUTTERWAVE_SECRET_KEY
        self.webhook_secret_hash = getattr(settings, 'FLW_SECRET_HASH', '')

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type":  "application/json",
        }

    # ── Payment initialization ───────────────────────────────────
    def initialize_payment(
        self,
        email: str,
        amount,
        tx_ref: str,
        redirect_url: str,
        customer_name: str = '',
        currency: str = 'NGN',
        title: str = "VendoPage Payment",
        description: str = "",
    ) -> dict:
        currency = resolve_currency(currency)
        payload  = {
            "tx_ref":       tx_ref,
            "amount":       str(amount),
            "currency":     currency,
            "redirect_url": redirect_url,
            "customer": {
                "email": email,
                "name":  customer_name,
            },
            "customizations": {
                "title":       title,
                "description": description,
                "logo":        getattr(settings, 'SITE_LOGO_URL', ''),
            },
        }
        try:
            resp = requests.post(
                f"{self.BASE_URL}/payments",
                json=payload, headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error("FLW initialize_payment error: %s", e)
            return {"status": "error", "message": str(e)}

    # ── Verify by transaction ID ─────────────────────────────────
    def verify_payment(self, transaction_id) -> dict:
        try:
            resp = requests.get(
                f"{self.BASE_URL}/transactions/{transaction_id}/verify",
                headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error("FLW verify_payment error: %s", e)
            return {"status": "error", "message": str(e)}

    # ── Verify by tx_ref ─────────────────────────────────────────
    def verify_by_tx_ref(self, tx_ref: str) -> dict:
        try:
            resp = requests.get(
                f"{self.BASE_URL}/transactions/verify_by_reference",
                params={"tx_ref": tx_ref},
                headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error("FLW verify_by_tx_ref error: %s", e)
            return {"status": "error", "message": str(e)}

    # ── Webhook signature verification ───────────────────────────
    def verify_webhook_signature(self, request_signature: str, payload_body) -> bool:
        """
        Flutterwave sends the secret hash as a plain header value in 'verif-hash'.
        Compare it directly — no HMAC needed.
        """
        if not self.webhook_secret_hash:
            logger.warning("FLW_SECRET_HASH not configured — webhook verification skipped")
            return False
        return hmac.compare_digest(
            request_signature.strip(),
            self.webhook_secret_hash.strip(),
        )

    # ── Transfer to vendor bank account ──────────────────────────
    def transfer_to_vendor(self, order) -> dict:
        """
        Send vendor payout via Flutterwave Transfer API.
        Requires your server IP to be whitelisted in FLW dashboard.
        """
        try:
            bank = order.seller.bank_account
        except Exception:
            logger.error("No bank account for seller %s", order.seller.business_name)
            return {"status": "error", "message": "No bank account configured"}

        if not bank.bank_code:
            logger.error(
                "bank_code is empty for %s — seller must re-save payout account",
                order.seller.business_name
            )
            return {"status": "error", "message": "Bank code missing — seller must re-save payout account"}

        payload = {
            "account_bank":     bank.bank_code,
            "account_number":   bank.account_number,
            "amount":           float(order.vendor_payout),
            "currency":         resolve_currency(order.currency),
            "narration":        f"Vendopage payout — Order {str(order.order_ref)[:8].upper()}",
            "reference":        f"VDP-PAY-{str(order.order_ref)[:16]}",
            "beneficiary_name": bank.account_name,
            "meta": {
                "order_ref":    str(order.order_ref),
                "seller_id":    order.seller.id,
            },
        }

        logger.info(
            "[FLW TRANSFER] Sending ₦%s to %s (%s %s) for order %s",
            order.vendor_payout,
            bank.account_name,
            bank.bank_name,
            bank.account_number[-4:],
            str(order.order_ref)[:8].upper(),
        )

        try:
            resp = requests.post(
                f"{self.BASE_URL}/transfers",
                json=payload, headers=self._headers(), timeout=30
            )
            logger.info("[FLW TRANSFER] HTTP %s — %s", resp.status_code, resp.text)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error("FLW transfer_to_vendor error for order %s: %s", order.order_ref, e)
            return {"status": "error", "message": str(e)}

    # ── Get banks ────────────────────────────────────────────────
    def get_banks(self, country: str = 'NG') -> list:
        try:
            resp = requests.get(
                f"{self.BASE_URL}/banks/{country}",
                headers=self._headers(), timeout=15
            )
            resp.raise_for_status()
            return resp.json().get('data', [])
        except requests.exceptions.RequestException as e:
            logger.error("FLW get_banks error: %s", e)
            return []

    # ── Verify bank account ──────────────────────────────────────
    def verify_bank_account(self, account_number: str, bank_code: str) -> dict:
        try:
            resp = requests.post(
                f"{self.BASE_URL}/accounts/resolve",
                json={"account_number": account_number, "account_bank": bank_code},
                headers=self._headers(), timeout=15
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error("FLW verify_bank_account error: %s", e)
            return {"status": "error", "message": str(e)}


# Singleton
flw = FlutterwavePayment()