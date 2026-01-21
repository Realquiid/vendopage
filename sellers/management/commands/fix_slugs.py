from django.core.management.base import BaseCommand
from sellers.models import Seller


class Command(BaseCommand):
    help = 'Fix sellers without slugs'

    def handle(self, *args, **options):
        sellers_without_slugs = Seller.objects.filter(slug='')
        count = sellers_without_slugs.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('✅ All sellers have slugs!'))
            return
        
        self.stdout.write(f'Found {count} sellers without slugs. Fixing...')
        
        for seller in sellers_without_slugs:
            old_slug = seller.slug
            seller.save()  # This triggers slug generation
            self.stdout.write(f'  ✓ {seller.business_name}: "{old_slug}" → "{seller.slug}"')
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Fixed {count} sellers!'))