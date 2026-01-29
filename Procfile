

release: python manage.py migrate --noinput && python create_admin.py
web: gunicorn config.wsgi --log-file -
