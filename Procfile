web: gunicorn app:server --workers 4
worker-default: celery -A app:celery_app worker --loglevel=INFO --concurrency=2
worker-beat: celery -A app:celery_app beat --loglevel=INFO