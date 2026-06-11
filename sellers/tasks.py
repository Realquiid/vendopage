
# sellers/tasks.py
from celery import shared_task
from django.core.management import call_command
import logging

logger = logging.getLogger(__name__)

@shared_task(name='sellers.tasks.run_daily_payout')
def run_daily_payout():
    """
    Runs every night at 2 AM Lagos (WAT).
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




# Step 5: Update your Celery config (celery.py in your project root):
#
# from celery import Celery
# import os
#
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')
#
# app = Celery('vendopage')
# app.config_from_object('django.conf:settings', namespace='CELERY')
# app.autodiscover_tasks()
#
#
# Step 6: Run the beat scheduler (in addition to your normal celery worker):
#
#   celery -A your_project beat -l info
#   celery -A your_project worker -l info
#
# Or with supervisor (recommended for production):
#
#   [program:celery-worker]
#   command=/path/to/venv/bin/celery -A your_project worker -l info
#
#   [program:celery-beat]
#   command=/path/to/venv/bin/celery -A your_project beat -l info
