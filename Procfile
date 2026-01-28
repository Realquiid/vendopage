

release: python manage.py migrate --noinput && python create_admin.py
web: gunicorn config.wsgi --log-file -
worker: celery -A config worker --loglevel=info
beat: celery -A config beat --loglevel=info