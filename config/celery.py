
from celery import Celery
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('vendopage')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Add this line so Celery Beat doesn't throw an attribute error
celery = app
