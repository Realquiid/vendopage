
# ==========================================
# STEP 4: Create sellers/flutterwave.py
# ==========================================

import requests
import hashlib
import hmac
from django.conf import settings
from decimal import Decimal

class FlutterwavePayment:
    BASE_URL = "https://api.flutterwave.com/v3"
    
    def __init__(self):
        self.public_key = settings.FLUTTERWAVE_PUBLIC_KEY
        self.secret_key = settings.FLUTTERWAVE_SECRET_KEY
    
    def initialize_payment(self, email, amount, tx_ref, redirect_url, customer_name):
        """Initialize a Flutterwave payment"""
        url = f"{self.BASE_URL}/payments"
        
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "tx_ref": tx_ref,
            "amount": str(amount),
            "currency": "NGN",
            "redirect_url": redirect_url,
            "customer": {
                "email": email,
                "name": customer_name
            },
            "customizations": {
                "title": "VendoPage Premium Subscription",
                "description": "Monthly premium subscription",
                "logo": "https://your-domain.com/static/logo.png"
            }
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"status": "error", "message": str(e)}
    
    def verify_payment(self, transaction_id):
        """Verify a payment transaction"""
        url = f"{self.BASE_URL}/transactions/{transaction_id}/verify"
        
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"status": "error", "message": str(e)}
    
    def verify_webhook_signature(self, signature, payload):
        """Verify webhook signature from Flutterwave"""
        hash = hmac.new(
            self.secret_key.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return hash == signature

