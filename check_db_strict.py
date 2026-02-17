
import os
import django
from django.conf import settings

# Do NOT load dotenv here, to simulate manage.py behavior
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

print(f"DATABASE ENGINE: {settings.DATABASES['default']['ENGINE']}")
print(f"DATABASE NAME: {settings.DATABASES['default']['NAME']}")
print(f"DATABASE HOST: {settings.DATABASES['default']['HOST']}")
