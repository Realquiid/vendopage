"""
sellers/paystack.py
Paystack integration for VendoPage.
Handles subscription payments, order payments, webhook verification, and payouts.
"""

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
    'USD': 'USD',
    'ZAR': 'ZAR',
}
DEFAULT_CURRENCY = 'NGN'

def resolve_currency(currency_code: str) -> str:
    return SUPPORTED_CURRENCIES.get((currency_code or '').upper(), DEFAULT_CURRENCY)


class PaystackPayment:
    BASE_URL = "https://api.paystack.co"

    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

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
        """Initialize a Paystack payment. Returns dict with authorization_url."""
        currency = resolve_currency(currency)
        # Paystack amount is in kobo (multiply by 100)
        amount_kobo = int(Decimal(str(amount)) * 100)

        payload = {
            "email":        email,
            "amount":       amount_kobo,
            "currency":     currency,
            "reference":    tx_ref,
            "callback_url": redirect_url,
            "metadata": {
                "custom_fields": [
                    {
                        "display_name":  "Customer Name",
                        "variable_name": "customer_name",
                        "value":         customer_name,
                    },
                    {
                        "display_name":  "Order Description",
                        "variable_name": "description",
                        "value":         description,
                    },
                ]
            },
        }

        try:
            resp = requests.post(
                f"{self.BASE_URL}/transaction/initialize",
                json=payload, headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            # Normalize to same shape as Flutterwave response
            if data.get('status'):
                return {
                    "status": "success",
                    "data": {
                        "link": data["data"]["authorization_url"],
                        "reference": data["data"]["reference"],
                    }
                }
            return {"status": "error", "message": data.get("message", "Unknown error")}
        except requests.exceptions.RequestException as e:
            logger.error("Paystack initialize_payment error: %s", e)
            return {"status": "error", "message": str(e)}

    def verify_payment(self, reference) -> dict:
        """Verify a payment by reference. Returns normalized dict."""
        try:
            resp = requests.get(
                f"{self.BASE_URL}/transaction/verify/{reference}",
                headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get('status') and data['data'].get('status') == 'success':
                tx = data['data']
                return {
                    "status": "success",
                    "data": {
                        "status":   "successful",
                        "tx_ref":   tx["reference"],
                        "amount":   Decimal(str(tx["amount"])) / 100,  # kobo → naira
                        "currency": tx["currency"],
                        "id":       tx["id"],
                    }
                }
            return {"status": "error", "message": "Payment not successful"}
        except requests.exceptions.RequestException as e:
            logger.error("Paystack verify_payment error: %s", e)
            return {"status": "error", "message": str(e)}

    def verify_webhook_signature(self, request_body: bytes, signature: str) -> bool:
        """Paystack uses HMAC-SHA512."""
        if not signature:
            return False
        expected = hmac.new(
            self.secret_key.encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def transfer_to_vendor(self, order) -> dict:
        """
        Send payout to vendor bank account via Paystack Transfers.
        Requires a recipient_code on the bank account.
        """
        try:
            bank = order.seller.bank_account
        except Exception:
            logger.error("No bank account for seller %s", order.seller.business_name)
            return {"status": "error", "message": "No bank account configured"}

        # If no recipient code yet, create one first
        if not bank.recipient_code:
            result = self.create_transfer_recipient(bank)
            if result.get('status') != 'success':
                return result

        amount_kobo = int(Decimal(str(order.vendor_payout)) * 100)

        payload = {
            "source":    "balance",
            "amount":    amount_kobo,
            "recipient": bank.recipient_code,
            "reason":    f"Vendopage payout — Order {str(order.order_ref)[:8].upper()}",
            "reference": f"VDP-PAY-{order.order_ref}",
        }

        try:
            resp = requests.post(
                f"{self.BASE_URL}/transfer",
                json=payload, headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error("Paystack transfer error for order %s: %s", order.order_ref, e)
            return {"status": False, "message": str(e)}

    def create_transfer_recipient(self, bank_account) -> dict:
        """Create a Paystack transfer recipient for a bank account."""
        payload = {
            "type":           "nuban",
            "name":           bank_account.account_name,
            "account_number": bank_account.account_number,
            "bank_code":      bank_account.bank_code,
            "currency":       "NGN",
        }
        try:
            resp = requests.post(
                f"{self.BASE_URL}/transferrecipient",
                json=payload, headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get('status'):
                recipient_code = data['data']['recipient_code']
                bank_account.recipient_code = recipient_code
                bank_account.save(update_fields=['recipient_code'])
                return {"status": "success", "recipient_code": recipient_code}
            return {"status": "error", "message": data.get("message")}
        except requests.exceptions.RequestException as e:
            logger.error("Paystack create_recipient error: %s", e)
            return {"status": "error", "message": str(e)}

    def get_banks(self, country: str = 'nigeria') -> list:
        try:
            resp = requests.get(
                f"{self.BASE_URL}/bank?country={country}&perPage=100",
                headers=self._headers(), timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get('data', [])
        except requests.exceptions.RequestException as e:
            logger.error("Paystack get_banks error: %s", e)
            return []

    def verify_bank_account(self, account_number: str, bank_code: str) -> dict:
        try:
            resp = requests.get(
                f"{self.BASE_URL}/bank/resolve",
                params={"account_number": account_number, "bank_code": bank_code},
                headers=self._headers(), timeout=15
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error("Paystack verify_bank_account error: %s", e)
            return {"status": False, "message": str(e)}


# Singleton
paystack = PaystackPayment()