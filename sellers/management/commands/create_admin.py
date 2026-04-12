# sellers/management/commands/create_admin.py
from django.core.management.base import BaseCommand
from sellers.models import Seller

class Command(BaseCommand):
    help = 'Create admin superuser'

    def handle(self, *args, **kwargs):
        self.stdout.write('🚀 Creating superuser...')
        try:
            Seller.objects.filter(username='richard').delete()
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
            self.stdout.write(f'✅ Superuser created! ID: {admin.id}')
        except Exception as e:
            self.stdout.write(f'❌ Failed: {str(e)}')
            raise