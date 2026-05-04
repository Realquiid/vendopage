

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from sellers.models import Seller
from products.models import Product
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send re-engagement emails to sellers inactive for N days'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=5,
            help='Number of days without a product upload to trigger the email (default: 5)',
        )
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
        from sellers.email import send_reengagement_email

        days      = options['days']
        dry_run   = options['dry_run']
        seller_id = options.get('seller_id')

        cutoff = timezone.now() - timedelta(days=days)

        # Find sellers whose most recent product upload is older than cutoff
        # We use a subquery approach: get seller IDs who have at least one product
        # but none uploaded after the cutoff date.
        sellers = Seller.objects.filter(
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )

        if seller_id:
            sellers = sellers.filter(id=seller_id)

        sent    = 0
        skipped = 0
        errors  = 0

        for seller in sellers:
            try:
                # Check if they have any products at all
                total_products = Product.objects.filter(seller=seller).count()
                if total_products == 0:
                    # Brand new seller — skip, welcome email already handled this
                    skipped += 1
                    continue

                # Check if their most recent upload is older than the cutoff
                latest_product = Product.objects.filter(
                    seller=seller
                ).order_by('-created_at').first()

                if not latest_product or latest_product.created_at > cutoff:
                    # Uploaded recently — not inactive
                    skipped += 1
                    continue

                days_inactive = (timezone.now() - latest_product.created_at).days
                store_url     = f'https://www.vendopage.com/{seller.slug}'

                if dry_run:
                    self.stdout.write(
                        f'[DRY RUN] Would send to {seller.email} — '
                        f'inactive for {days_inactive} days '
                        f'(last upload: {latest_product.created_at.strftime("%Y-%m-%d")})'
                    )
                    sent += 1
                    continue

                success = send_reengagement_email(
                    to_email=seller.email,
                    business_name=seller.business_name,
                    store_url=store_url,
                    days_inactive=days_inactive,
                )

                if success:
                    sent += 1
                    self.stdout.write(f'✅ Sent to {seller.email} ({days_inactive} days inactive)')
                else:
                    errors += 1
                    self.stderr.write(f'❌ Failed for {seller.email}')

            except Exception as e:
                errors += 1
                logger.error(f"Re-engagement email error for seller {seller.id}: {e}")
                self.stderr.write(f'❌ Error for {seller.email}: {e}')

        self.stdout.write(
            self.style.SUCCESS(
                f'\nDone — {sent} sent, {skipped} skipped, {errors} errors'
            )
        )