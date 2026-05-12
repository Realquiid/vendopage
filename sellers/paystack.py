"""
sellers/paystack.py  —  Final correct implementation
=====================================================

ARCHITECTURE:
  - Buyer pays → 100% lands in YOUR Paystack Transfer Balance
    (requires Manual Payouts enabled — email support@paystack.com once)
  - Escrow order  → funds sit in your balance until buyer confirms
  - Direct order  → Transfer API fires immediately after payment
  - Buyer confirms delivery → Transfer API sends 95% to seller
  - Dispute + refund buyer  → Refund API sends 100% back to buyer
  - Dispute + pay seller    → Transfer API sends 95% to seller
  - Your 5% stays in your balance automatically

WHY NOT SUBACCOUNTS FOR ESCROW:
  Paystack subaccount manual settlement has no instant-release API.
  Switching manual → auto only queues for next settlement run (up to 24h).
  Transfer API is instant and gives you full control.

PREREQUISITE:
  Email support@paystack.com: "Please enable Manual Payouts on my account
  so collected funds stay in my Transfer Balance instead of auto-settling."
  This is free and standard for marketplace businesses.
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
            "Content-Type":  "application/json",
        }

    # ─────────────────────────────────────────────────────────────
    # PAYMENT INITIALIZATION
    # ─────────────────────────────────────────────────────────────

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
        """
        Initialize a Paystack payment. Full amount goes to your main account.
        Your Transfer Balance accumulates → you disburse to sellers manually
        via transfer_to_vendor() after delivery confirmation.
        """
        currency    = resolve_currency(currency)
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

            if data.get('status'):
                return {
                    "status": "success",
                    "data": {
                        "link":      data["data"]["authorization_url"],
                        "reference": data["data"]["reference"],
                    }
                }
            return {"status": "error", "message": data.get("message", "Unknown error")}

        except requests.exceptions.RequestException as e:
            logger.error("Paystack initialize_payment error: %s", e)
            return {"status": "error", "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # PAYMENT VERIFICATION
    # ─────────────────────────────────────────────────────────────

    def verify_payment(self, reference: str) -> dict:
        """Verify a payment by reference."""
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
                        "amount":   Decimal(str(tx["amount"])) / 100,
                        "currency": tx["currency"],
                        "id":       str(tx["id"]),
                    }
                }
            return {"status": "error", "message": "Payment not successful"}

        except requests.exceptions.RequestException as e:
            logger.error("Paystack verify_payment error: %s", e)
            return {"status": "error", "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # TRANSFER — send seller their payout
    # ─────────────────────────────────────────────────────────────

    # def transfer_to_vendor(self, order) -> dict:
    #     """
    #     Send the seller their cut (vendor_payout) from your Transfer Balance.
    #     Called after:
    #       - Buyer confirms delivery (escrow)
    #       - Direct payment order confirmed (immediate)
    #       - 72hr auto-release fires
    #       - Admin resolves dispute in seller's favour

    #     Requires:
    #       - Manual Payouts enabled on your Paystack account
    #       - Seller has a VendorBankAccount with bank_code saved
    #     """
    #     try:
    #         bank = order.seller.bank_account
    #     except Exception:
    #         logger.error(
    #             "No bank account for seller %s — payout skipped",
    #             order.seller.business_name
    #         )
    #         return {"status": "error", "message": "No bank account configured"}

    #     # Create recipient code if missing
    #     if not bank.recipient_code:
    #         result = self.create_transfer_recipient(bank)
    #         if result.get('status') != 'success':
    #             logger.error(
    #                 "Could not create transfer recipient for %s: %s",
    #                 order.seller.business_name, result
    #             )
    #             return result

    #     amount_kobo = int(Decimal(str(order.vendor_payout)) * 100)

    #     payload = {
    #         "source":    "balance",
    #         "amount":    amount_kobo,
    #         "recipient": bank.recipient_code,
    #         "reason":    f"Vendopage payout — Order #{str(order.order_ref)[:8].upper()}",
    #         "reference": f"VDP-PAY-{str(order.order_ref)[:16]}",
    #     }

    #     try:
    #         resp = requests.post(
    #             f"{self.BASE_URL}/transfer",
    #             json=payload, headers=self._headers(), timeout=30
    #         )
    #         resp.raise_for_status()
    #         data = resp.json()
    #         logger.info(
    #             "Transfer API response for order %s: status=%s message=%s",
    #             order.order_ref, data.get('status'), data.get('message')
    #         )
    #         return data

    #     except requests.exceptions.RequestException as e:
    #         logger.error(
    #             "Paystack transfer error for order %s: %s",
    #             order.order_ref, e
    #         )
    #         return {"status": False, "message": str(e)}


    def transfer_to_vendor(self, order) -> dict:
        try:
            bank = order.seller.bank_account
        except Exception as e:
            return {"status": "error", "message": f"No bank account: {e}"}
 
        if not bank.recipient_code:
            result = self.create_transfer_recipient(bank)
            if result.get('status') != 'success':
                return result
 
        amount_kobo = int(Decimal(str(order.vendor_payout)) * 100)
        reference   = f"VDP-PAY-{str(order.order_ref)[:16]}"
 
        payload = {
            "source":    "balance",
            "amount":    amount_kobo,
            "recipient": bank.recipient_code,
            "reason":    f"Vendopage payout — Order #{str(order.order_ref)[:8].upper()}",
            "reference": reference,
        }
 
        logger.info(
            f"[TRANSFER API] POST /transfer — "
            f"amount_kobo={amount_kobo} "
            f"recipient={bank.recipient_code} "
            f"reference={reference}"
        )
 
        try:
            resp = requests.post(
                f"{self.BASE_URL}/transfer",
                json=payload, headers=self._headers(), timeout=30
            )
 
            logger.info(
                f"[TRANSFER API] HTTP {resp.status_code} — {resp.text}"
            )
 
            data = resp.json()
            return data
 
        except requests.exceptions.RequestException as e:
            logger.error(f"[TRANSFER API] RequestException — {e}")
            return {"status": False, "message": str(e)}
 
    def create_transfer_recipient(self, bank_account) -> dict:
        payload = {
            "type":           "nuban",
            "name":           bank_account.account_name,
            "account_number": bank_account.account_number,
            "bank_code":      bank_account.bank_code,
            "currency":       "NGN",
        }
        logger.error(f"CREATING RECIPIENT — payload: {payload}")  # ← add

        try:
            resp = requests.post(
                f"{self.BASE_URL}/transferrecipient",
                json=payload, headers=self._headers(), timeout=30
            )
            logger.error(f"RECIPIENT RESPONSE: {resp.status_code} | {resp.text}")  # ← add
            resp.raise_for_status()
            data = resp.json()

            if data.get('status'):
                recipient_code = data['data']['recipient_code']
                bank_account.recipient_code = recipient_code
                bank_account.save(update_fields=['recipient_code'])
                return {"status": "success", "recipient_code": recipient_code}

            return {"status": "error", "message": data.get("message", "Unknown")}

        except requests.exceptions.RequestException as e:
            logger.error("Paystack create_recipient error: %s", e)
            return {"status": "error", "message": str(e)}

    # def create_transfer_recipient(self, bank_account) -> dict:
    #     """
    #     Register a seller's bank account as a Paystack transfer recipient.
    #     Saves the recipient_code back to the bank_account model.
    #     """
    #     payload = {
    #         "type":           "nuban",
    #         "name":           bank_account.account_name,
    #         "account_number": bank_account.account_number,
    #         "bank_code":      bank_account.bank_code,
    #         "currency":       "NGN",
    #     }

    #     try:
    #         resp = requests.post(
    #             f"{self.BASE_URL}/transferrecipient",
    #             json=payload, headers=self._headers(), timeout=30
    #         )
    #         resp.raise_for_status()
    #         data = resp.json()

    #         if data.get('status'):
    #             recipient_code = data['data']['recipient_code']
    #             bank_account.recipient_code = recipient_code
    #             bank_account.save(update_fields=['recipient_code'])
    #             logger.info(
    #                 "Transfer recipient created for %s: %s",
    #                 bank_account.seller.business_name, recipient_code
    #             )
    #             return {"status": "success", "recipient_code": recipient_code}

    #         return {"status": "error", "message": data.get("message", "Unknown")}

    #     except requests.exceptions.RequestException as e:
    #         logger.error("Paystack create_recipient error: %s", e)
    #         return {"status": "error", "message": str(e)}

    def check_balance(self) -> dict:
        """
        Check your Paystack Transfer Balance.
        Use this before initiating transfers to ensure funds are available.
        Returns balance in NGN (converted from kobo).
        """
        try:
            resp = requests.get(
                f"{self.BASE_URL}/balance",
                headers=self._headers(), timeout=15
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get('status'):
                balances = data.get('data', [])
                ngn_balance = next(
                    (b for b in balances if b.get('currency') == 'NGN'), None
                )
                if ngn_balance:
                    return {
                        "status":  "success",
                        "balance": Decimal(str(ngn_balance['balance'])) / 100,
                        "currency": "NGN",
                    }
            return {"status": "error", "message": "Could not read balance"}

        except requests.exceptions.RequestException as e:
            logger.error("Paystack check_balance error: %s", e)
            return {"status": "error", "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # REFUND — send buyer their money back
    # ─────────────────────────────────────────────────────────────

    def refund_transaction(
        self,
        transaction_reference: str,
        amount: Decimal = None
    ) -> dict:
        """
        Refund a buyer's payment back to their original payment method.
        Called when admin resolves dispute in buyer's favour.

        transaction_reference: the original tx_ref (flutterwave_tx_ref field)
        amount: Decimal in NGN. None = full refund.

        Paystack handles returning money to the buyer's card/bank automatically.
        Full refund reverses the entire transaction including your 5% cut.
        This is normal — your fee covers the risk of occasional refunds.

        Refund timeline: 5–10 business days to buyer's account.
        """
        payload = {"transaction": transaction_reference}

        if amount is not None:
            payload["amount"] = int(Decimal(str(amount)) * 100)  # kobo

        try:
            resp = requests.post(
                f"{self.BASE_URL}/refund",
                json=payload, headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status"):
                refund_data = data.get("data", {})
                logger.info(
                    "Refund initiated — tx_ref: %s | refund_id: %s | status: %s",
                    transaction_reference,
                    refund_data.get("id"),
                    refund_data.get("status"),
                )
                return {
                    "status":           "success",
                    "refund_id":        str(refund_data.get("id", "")),
                    "refund_status":    refund_data.get("status", "pending"),
                    "message":          data.get("message", "Refund initiated"),
                }

            return {
                "status":  "error",
                "message": data.get("message", "Refund request failed"),
            }

        except requests.exceptions.RequestException as e:
            logger.error(
                "Paystack refund_transaction error for %s: %s",
                transaction_reference, e
            )
            return {"status": "error", "message": str(e)}

    # ─────────────────────────────────────────────────────────────
    # WEBHOOK VERIFICATION
    # ─────────────────────────────────────────────────────────────

    def verify_webhook_signature(self, request_body: bytes, signature: str) -> bool:
        """Verify Paystack webhook using HMAC-SHA512."""
        if not signature:
            return False
        expected = hmac.new(
            self.secret_key.encode('utf-8'),
            msg=request_body,
            digestmod=hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    # ─────────────────────────────────────────────────────────────
    # UTILITY
    # ─────────────────────────────────────────────────────────────

    def get_banks(self, country: str = 'nigeria') -> list:
        try:
            resp = requests.get(
                f"{self.BASE_URL}/bank?country={country}&perPage=100",
                headers=self._headers(), timeout=15
            )
            resp.raise_for_status()
            return resp.json().get('data', [])
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