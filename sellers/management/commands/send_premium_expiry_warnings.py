
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from sellers.models import Seller
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send expiry warning emails to premium sellers expiring within N days'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=3,
            help='Warn sellers expiring within this many days (default: 3)',
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
        from sellers.email import send_premium_expiry_warning

        days      = options['days']
        dry_run   = options['dry_run']
        seller_id = options.get('seller_id')

        now        = timezone.now()
        warn_until = now + timedelta(days=days)

        # Find premium sellers whose subscription expires within the warning window
        # but hasn't already expired
        sellers = Seller.objects.filter(
            is_active=True,
            is_staff=False,
            is_superuser=False,
            subscription_type='premium',
            subscription_expires__gt=now,        # not yet expired
            subscription_expires__lte=warn_until, # expiring within N days
        )

        if seller_id:
            sellers = sellers.filter(id=seller_id)

        sent   = 0
        errors = 0

        for seller in sellers:
            try:
                days_left    = (seller.subscription_expires - now).days
                expires_date = seller.subscription_expires.strftime('%B %d, %Y')

                if dry_run:
                    self.stdout.write(
                        f'[DRY RUN] Would warn {seller.email} — '
                        f'expires {expires_date} ({days_left} days left)'
                    )
                    sent += 1
                    continue

                success = send_premium_expiry_warning(
                    to_email=seller.email,
                    business_name=seller.business_name,
                    expires_date=expires_date,
                    days_left=days_left,
                )

                if success:
                    sent += 1
                    self.stdout.write(
                        f'✅ Warned {seller.email} — expires {expires_date} ({days_left} days)'
                    )
                else:
                    errors += 1
                    self.stderr.write(f'❌ Failed for {seller.email}')

            except Exception as e:
                errors += 1
                logger.error(f"Premium expiry warning error for seller {seller.id}: {e}")
                self.stderr.write(f'❌ Error for {seller.email}: {e}')

        self.stdout.write(
            self.style.SUCCESS(
                f'\nDone — {sent} sent, {errors} errors'
            )
        )