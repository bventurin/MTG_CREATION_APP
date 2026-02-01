import os
import django
from django.conf import settings

# Configure minimal Django settings if not already configured
if not settings.configured:
    settings.configure(INSTALLED_APPS=['MTG_CREATION_APP'])

# Setup Django
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
# django.setup()
# actually we can just test the class directly since it only uses requests, 
# provided it doesn't import models at module level.
# references relative imports which might be tricky if run as main.
# Let's adjust imports or run as a module.

import sys
sys.path.append('/Users/brennoventurini/Magic Project')

from MTG_CREATION_APP.services.ai_recommender import CardRecommender

print("Testing CardRecommender...")
recs = CardRecommender.get_recommendations('modern', ['R', 'U'])
print(f"Found {len(recs)} recommendations.")
for card in recs:
    print(f"- {card.get('name')}")
