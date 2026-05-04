from django.core.management.base import BaseCommand
from django.utils import timezone
from sellers.models import Seller
from products.models import Product
from django.db.models import Count, Q
import logging
 
logger = logging.getLogger(__name__)
 
 
class Command(BaseCommand):
    help = 'Send weekly store performance summary emails to all active sellers'
 
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be sent without actually sending emails',
        )
        parser.add_argument(
            '--seller-id',
            type=int,
            help='Send only to a specific seller (for testing)',
        )
 
    def handle(self, *args, **options):
        from sellers.email import send_weekly_summary_email
 
        dry_run   = options['dry_run']
        seller_id = options.get('seller_id')
 
        sellers = Seller.objects.filter(
            is_active=True, is_staff=False, is_superuser=False
        )
        if seller_id:
            sellers = sellers.filter(id=seller_id)
 
        sent  = 0
        skipped = 0
        errors  = 0
 
        for seller in sellers:
            try:
                active_products = Product.objects.filter(
                    seller=seller, is_archived=False, is_sold_out=False
                ).count()
 
                # Skip sellers with 0 products — nothing useful to report
                if active_products == 0 and seller.weekly_page_views == 0:
                    skipped += 1
                    continue
 
                store_url = f'https://www.vendopage.com/{seller.slug}'
 
                if dry_run:
                    self.stdout.write(
                        f'[DRY RUN] Would send to {seller.email} — '
                        f'{seller.weekly_page_views} views, '
                        f'{seller.weekly_whatsapp_clicks} WA clicks, '
                        f'{active_products} products'
                    )
                    sent += 1
                    continue
 
                success = send_weekly_summary_email(
                    to_email=seller.email,
                    business_name=seller.business_name,
                    store_url=store_url,
                    page_views=seller.weekly_page_views,
                    whatsapp_clicks=seller.weekly_whatsapp_clicks,
                    active_products=active_products,
                )
 
                if success:
                    sent += 1
                    self.stdout.write(f'✅ Sent to {seller.email}')
                else:
                    errors += 1
                    self.stderr.write(f'❌ Failed for {seller.email}')
 
            except Exception as e:
                errors += 1
                logger.error(f"Weekly summary error for seller {seller.id}: {e}")
                self.stderr.write(f'❌ Error for {seller.email}: {e}')
 
        self.stdout.write(
            self.style.SUCCESS(
                f'\nDone — {sent} sent, {skipped} skipped, {errors} errors'
            )
        )
 