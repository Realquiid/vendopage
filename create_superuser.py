import os
import sys
import django

print("🚀 Starting superuser creation script...")
sys.stdout.flush()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
print("✅ Django setup complete")
sys.stdout.flush()

from sellers.models import Seller

try:
    count = Seller.objects.filter(username='richard').count()
    print(f"Found {count} existing richard accounts")
    sys.stdout.flush()
    
    Seller.objects.filter(username='richard').delete()
    print("🗑️ Deleted existing accounts")
    sys.stdout.flush()

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
    print(f"✅ Superuser created! ID: {admin.id}, Slug: {admin.slug}")
    sys.stdout.flush()

except Exception as e:
    print(f"❌ FAILED: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.stdout.flush()
    sys.exit(1)  # exit code 1 stops the release phase so you see it in logs