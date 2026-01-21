from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from products.models import Product

class Command(BaseCommand):
    help = 'Archive products older than 30 days'

    def handle(self, *args, **options):
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        updated = Product.objects.filter(
            created_at__lt=thirty_days_ago,
            is_archived=False
        ).update(is_archived=True)
        
        self.stdout.write(
            self.style.SUCCESS(f'Archived {updated} products')
        )