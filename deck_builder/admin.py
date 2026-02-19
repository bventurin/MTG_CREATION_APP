from django.contrib import admin
from .models import Deck, DeckCard


# Register your models here.
class DeckCardInline(admin.TabularInline):
    model = DeckCard
    extra = 0


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "created_at", "updated_at")
    inlines = [DeckCardInline]
    search_fields = ("name", "user__username")


@admin.register(DeckCard)
class DeckCardAdmin(admin.ModelAdmin):
    list_display = ("card_name", "quantity", "deck", "is_sideboard")
    list_filter = ("is_sideboard", "deck__user")
    search_fields = ("card_name", "deck__name")
