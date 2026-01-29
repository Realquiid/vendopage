# create_superuser.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from sellers.models import Seller

# Delete if exists
Seller.objects.filter(username='richard').delete()

# Create fresh superuser
admin = Seller.objects.create_superuser(
    username='richard',
    email='richardikenna61@gmail.com',
    password='Richard1yy1',
    business_name='VendoPage Admin',
    whatsapp_number='2347017820434',
    category='other'
)

print("✅ Superuser created successfully!")
print(f"Username: richard")
print(f"Email: richardikenna61@gmail.com")
print(f"Password: Richard1yy1")
print(f"Login at: http://localhost:8000/admin/")