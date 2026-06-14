# sellers/tasks.py
from celery import shared_task
from django.core.management import call_command
import logging

logger = logging.getLogger(__name__)


@shared_task(name='sellers.tasks.run_daily_payout')
def run_daily_payout():
    """
    Runs every night at 6 AM Lagos (WAT).
    Pays all sellers whose buyers clicked received before midnight.
    SKIPS any order where is_disputed=True — money stays locked.
    """
    logger.info("Starting daily payout task...")
    call_command('process_payouts')
    logger.info("Daily payout task complete.")


@shared_task(name='sellers.tasks.run_auto_release')
def run_auto_release():
    """
    Runs every 6 hours.
    Auto-releases shipped orders where auto_release_at has passed.
    SKIPS any order where is_disputed=True — money stays locked.
    """
    from sellers.views import auto_release_expired_orders
    auto_release_expired_orders()


@shared_task(name='sellers.tasks.reset_monthly_volumes')
def reset_monthly_volumes():
    """
    Runs at midnight on the 1st of every month.
    Resets monthly_volume_processed to 0 for all sellers.
    """
    from decimal import Decimal
    from django.utils import timezone
    from sellers.models import Seller

    today = timezone.now().date()
    updated = Seller.objects.filter(
        is_staff=False, is_superuser=False
    ).update(
        monthly_volume_processed=Decimal('0.00'),
        tier_reset_date=today,
    )
    logger.info(f"Reset monthly_volume_processed for {updated} seller(s) on {today}")
    return f"Reset {updated} seller(s)"