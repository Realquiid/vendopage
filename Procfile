
release: python manage.py migrate --noinput && python manage.py create_admin && python manage.py collectstatic --noinput
web: gunicorn config.wsgi --log-file -