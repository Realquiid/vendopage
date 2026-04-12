
release: python manage.py migrate --noinput && python create_superuser.py && python manage.py collectstatic --noinput
web: gunicorn config.wsgi --log-file -