import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from sellers.models import Seller

try:
    Seller.objects.filter(username='richard').delete()
    print("🗑️ Deleted existing richard account")

    admin = Seller.objects.create_superuser(
        username='richard',
        email='richardikenna61@gmail.com',
        password='Richard1yy1',
        business_name='VendoPage Admin',
        whatsapp_number='2347017820434',
        category='other',
        country_code='+234',
        currency_code='NGN',
        currency_symbol='₦',
    )

    print("✅ Superuser created successfully!")
    print(f"   Username: richard")
    print(f"   Email: richardikenna61@gmail.com")

except Exception as e:
    print(f"❌ Failed: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()
    raise