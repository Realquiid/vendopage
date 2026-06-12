
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
    """
    logger.info("Starting daily payout task...")
    call_command('process_payouts')
    logger.info("Daily payout task complete.")

@shared_task(name='sellers.tasks.run_auto_release')
def run_auto_release():
    """
    Runs every 6 hours.
    Auto-releases shipped orders where auto_release_at has passed.
    """
    from sellers.views import auto_release_expired_orders
    auto_release_expired_orders()

