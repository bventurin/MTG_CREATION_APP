from django.db import models
from django.contrib.auth.models import User
import uuid

# Create your models here.

class Card(models.Model):
    """Model to store Magic: The Gathering card information from Scryfall."""
    scryfall_id = models.UUIDField(unique=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    mana_cost = models.CharField(max_length=50, blank=True)
    type_line = models.CharField(max_length=255, blank=True, db_index=True)
    oracle_text = models.TextField(blank=True)
    image_url = models.URLField(blank=True)
    set_code = models.CharField(max_length=10, db_index=True)
    color_identity = models.CharField(max_length=20, blank=True)  # e.g., "UBR"
    power = models.CharField(max_length=10, blank=True)
    toughness = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['name', 'set_code']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.set_code})"


class Deck(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='decks')
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class DeckCard(models.Model):
    deck = models.ForeignKey(Deck, on_delete=models.CASCADE, related_name='cards')
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name='deck_cards')
    quantity = models.PositiveIntegerField()
    is_sideboard = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.quantity}x {self.card.name}"
