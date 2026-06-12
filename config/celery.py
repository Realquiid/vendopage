
from celery import Celery
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('vendopage')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


# Add this line so Celery Beat doesn't throw an attribute error
celery = app

from celery import Celery
from celery.schedules import crontab
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('vendopage')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.timezone = 'Africa/Lagos'
app.conf.enable_utc = False

app.conf.beat_schedule = {
    'payout-check-every-6h': {
        'task': 'sellers.tasks.run_daily_payout',
        'schedule': crontab(minute=0, hour='*/6'),
    },
    'auto-release-check': {
        'task': 'sellers.tasks.run_auto_release',
        'schedule': crontab(minute=0, hour='*/6'),
    },
    'weekly-summary': {
        'task': 'sellers.tasks.send_weekly_summaries',
        'schedule': crontab(hour=6, minute=0, day_of_week=1),
    },
    'reengagement-check': {
        'task': 'sellers.tasks.send_reengagement_emails',
        'schedule': crontab(hour=9, minute=0),
    },
    'premium-expiry-check': {
        'task': 'sellers.tasks.send_premium_expiry_warnings',
        'schedule': crontab(hour=10, minute=0),
    },
}

celery = app