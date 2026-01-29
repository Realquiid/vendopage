# sellers/management/commands/create_admin.py
from django.core.management.base import BaseCommand
from sellers.models import Seller

class Command(BaseCommand):
    help = 'Create or reset admin superuser'

    def handle(self, *args, **options):
        username = 'richard'
        email = 'richardikenna61@gmail.com'
        password = 'Richard1yy1'
        
        # Delete if exists
        Seller.objects.filter(username=username).delete()
        
        # Create fresh admin
        Seller.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            business_name='VendoPage Admin',
            whatsapp_number='2347017820434',
            category='other'
        )
        
        self.stdout.write(self.style.SUCCESS(f'✅ Admin created: {username}'))