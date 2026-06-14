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
    # ── Payout: 6 AM Monday–Friday only ──────────────────────────────────────
    # Flutterwave does not settle on weekends. Saturday/Sunday transactions
    # settle on Monday. Running on weekdays only means:
    #   - We never accidentally pay sellers from our own 5% revenue pool
    #   - Monday 6AM picks up ALL queued orders from Fri/Sat/Sun at once
    'daily-payout-6am-weekdays': {
        'task': 'sellers.tasks.run_daily_payout',
        'schedule': crontab(minute=0, hour=6, day_of_week='1-5'),  # Mon–Fri
    },

    # ── Auto-release: every 6 hours, all week ────────────────────────────────
    # This just moves shipped→RECEIVED when 72h timer expires.
    # No money moves here — safe to run on weekends.
    'auto-release-check': {
        'task': 'sellers.tasks.run_auto_release',
        'schedule': crontab(minute=0, hour='*/6'),
    },

    # ── Weekly seller summary: Monday 6 AM ───────────────────────────────────
    'weekly-summary': {
        'task': 'sellers.tasks.send_weekly_summaries',
        'schedule': crontab(hour=6, minute=0, day_of_week=1),
    },

    # ── Re-engagement emails: 9 AM daily ─────────────────────────────────────
    'reengagement-check': {
        'task': 'sellers.tasks.send_reengagement_emails',
        'schedule': crontab(hour=9, minute=0),
    },

    # ── Premium expiry warnings: 10 AM daily ─────────────────────────────────
    'premium-expiry-check': {
        'task': 'sellers.tasks.send_premium_expiry_warnings',
        'schedule': crontab(hour=10, minute=0),
    },

    # ── Reset monthly volumes: midnight on 1st of each month ─────────────────
    'reset-monthly-volumes': {
        'task': 'sellers.tasks.reset_monthly_volumes',
        'schedule': crontab(minute=0, hour=0, day_of_month='1'),
    },
}

celery = app