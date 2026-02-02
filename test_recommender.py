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

from card_recommender.services.ai_recommender import get_deck_recommendations

print("Testing Deck Recommendation Agent...")
recs = get_deck_recommendations("commander", ["R", "U"])
print(f"Found {len(recs)} deck recommendations.")
for deck in recs:
    print(f"- {deck.get('title')} (commander: {deck.get('commander')})")
