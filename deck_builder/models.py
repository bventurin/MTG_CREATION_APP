from django.db import models
from django.contrib.auth.models import User

# Create your models here.
class Deck(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='decks')
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class DeckCard(models.Model):
    deck = models.ForeignKey(Deck, on_delete=models.CASCADE, related_name='cards')
    card_name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    is_sideboard = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.quantity}x {self.card_name}"
