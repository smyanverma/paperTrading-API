import os
from celery import Celery

# Tell Celery where to find Django's settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'paperTrading.settings')

# 'paperTrading' here should match your project name
app = Celery('paperTrading')

# Read all CELERY_* settings from Django's settings.py automatically
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks.py in all installed apps
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')