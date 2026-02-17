
import os
import django
from django.conf import settings

# Manually load .env since manage.py doesn't do it by default unless using django-dotenv
# and we need to see what happens in the current environment
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("Loaded .env file manually")
except ImportError:
    print("dotenv not installed or import error")

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import connection
print(f"DATABASE ENGINE: {settings.DATABASES['default']['ENGINE']}")
print(f"DATABASE NAME: {settings.DATABASES['default']['NAME']}")
print(f"DATABASE HOST: {settings.DATABASES['default']['HOST']}")
print(f"Active Connection Vendor: {connection.vendor}")

regex = r'aws-1'
import re
if re.search(regex, settings.DATABASES['default']['HOST']):
    print("SUCCESS: Connected to Supabase host")
else:
    print("WARNING: Not connected to Supabase host")
