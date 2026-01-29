

release: python manage.py migrate --noinput && python create_admin.py && python manage.py collectstatic
web: gunicorn config.wsgi --log-file -
