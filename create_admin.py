# create_admin.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from sellers.models import Seller

# Change these credentials
ADMIN_USERNAME = 'richard'
ADMIN_EMAIL = 'richardikenna61@gmail.com'
ADMIN_PASSWORD = 'Richard1yy1'  # CHANGE THIS!

if not Seller.objects.filter(username=ADMIN_USERNAME).exists():
    Seller.objects.create_superuser(
        username=ADMIN_USERNAME,
        email=ADMIN_EMAIL,
        password=ADMIN_PASSWORD,
        business_name='VendoPage Admin',
        phone_number='08132903002',
        whatsapp_number='08132903002',
    )
    print('✅ Superuser created successfully!')
    print(f'Username: {ADMIN_USERNAME}')
    print(f'Email: {ADMIN_EMAIL}')
else:
    print('ℹ️ Superuser already exists!')

