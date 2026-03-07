from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from .services.dynamodb_service import DynamoDBService
from .services.card_organizer import organize_cards_by_type, get_deck_metadata
from .services.qr_service import QRService
from .services.voucher_service import VoucherService
from .services.scryfall_s3_service import ScryfallS3Service
from .services.plot_service import PlotService
from card_recommender.services.ai_recommender import DeckRecommendationAgent
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.cache import cache
import re
import logging

logger = logging.getLogger(__name__)


def parse_deck_list(text):
    """Parse a deck list text into a deck name and list of card dicts.

    Returns:
        tuple: (deck_name, cards_data) where cards_data is a list of dicts
               with keys: card_name, quantity, is_sideboard
    """
    deck_name = None
    # Use a dict to group identical cards and sum their quantities
    # Key: (card_name, is_sideboard) -> Value: quantity
    grouped_cards = {}
    lines = text.strip().split("\n")
    current_section = None

    # Default to 'deck' section if no section headers are found
    if "deck" not in [
        line.strip().lower()
        for line in lines
        if line.strip().lower() in ["deck", "sideboard"]
    ]:
        current_section = "deck"

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.lower() == "deck":
            current_section = "deck"
            continue
        elif line.lower() == "sideboard":
            current_section = "sideboard"
            continue
        elif line.lower().startswith("name "):
            deck_name = line[5:].strip()
            continue
        elif line.lower() in ["about"]:
            continue

        # Card line format: "4 Card Name"
        match = re.match(r"^(\d+)\s+(.*)", line)
        if match and current_section:
            quantity = int(match.group(1))
            card_name = match.group(2).strip()
            is_sideboard = current_section == "sideboard"
            
            # Group cards that have the same name and section, sum their quantities
            key = (card_name, is_sideboard)
            grouped_cards[key] = grouped_cards.get(key, 0) + quantity

    # Convert grouped dict back to the list of dictionaries format
    cards_data = [
        {
            "card_name": name,
            "quantity": qty,
            "is_sideboard": is_side_board,
        }
        for (name, is_side_board), qty in grouped_cards.items()
    ]

    return deck_name, cards_data


def home(request):
    decks = []
    if request.user.is_authenticated:
        try:
            db = DynamoDBService()
            decks = db.get_user_decks(str(request.user.id))

            for deck in decks:
                cards = db.get_deck_cards(deck["deck_id"])
                deck["card_count"] = sum(c["quantity"] for c in cards)

                main_deck = [c for c in cards if not c.get("is_sideboard")]
                try:
                    metadata = get_deck_metadata(main_deck)
                    deck["color_identity"] = metadata["colors"]
                    deck["representative_image"] = metadata["representative_image"]
                except Exception:
                    logger.exception("Failed to load metadata for deck %s", deck.get("deck_id"))
                    deck["color_identity"] = []
                    deck["representative_image"] = None
        except Exception:
            logger.exception("Failed to load decks for user %s", request.user.id)
            decks = []

    return render(request, "deck_builder/home.html", {"decks": decks})


@login_required(login_url="login")
def create_deck(request):
    db = DynamoDBService()

    if request.method == "POST":
        deck_list_text = request.POST.get("deck_list", "")
        deck_name, cards_data = parse_deck_list(deck_list_text)
        deck_name = deck_name or "Untitled Deck"

        if cards_data:
            deck_id = db.create_deck(str(request.user.id), deck_name, cards_data)
            return redirect("deck_detail", deck_id=deck_id)

    return render(request, "deck_builder/create_deck.html")


@login_required(login_url="login")
def deck_list(request):
    try:
        db = DynamoDBService()
        decks = db.get_user_decks(str(request.user.id))

        for deck in decks:
            cards = db.get_deck_cards(deck["deck_id"])
            deck["card_count"] = sum(c["quantity"] for c in cards)

            main_deck = [c for c in cards if not c.get("is_sideboard")]
            try:
                metadata = get_deck_metadata(main_deck)
                deck["color_identity"] = metadata["colors"]
                deck["representative_image"] = metadata["representative_image"]
            except Exception:
                logger.exception("Failed to load metadata for deck %s", deck.get("deck_id"))
                deck["color_identity"] = []
                deck["representative_image"] = None
    except Exception:
        logger.exception("Failed to load deck list for user %s", request.user.id)
        decks = []

    return render(request, "deck_builder/deck_list.html", {"decks": decks})


def _get_or_generate_mana_curve(deck, deck_id, main_deck, card_data_cache):
    """Generate or retrieve cached mana curve plot URL."""
    updated_at = deck.get("updated_at", "unknown")
    plot_cache_key = f"mana_curve_{deck_id}_{updated_at}"

    mana_curve_url = cache.get(plot_cache_key)

    if not mana_curve_url:
        logger.info(f"Generating new mana curve plot for deck {deck_id}")

        # Create a mock scryfall service that uses our pre-fetched cache
        class MockScryfallService:
            @staticmethod
            def get_card_by_name(name, *args, **kwargs):
                return card_data_cache.get(name)

        mock_service = MockScryfallService()
        mana_curve_url = PlotService.generate_mana_curve_plot(main_deck, mock_service)

        # Cache for 24 hours if generation succeeded
        if mana_curve_url:
            cache.set(plot_cache_key, mana_curve_url, 86400)
    else:
        logger.info(f"Using cached mana curve plot for deck {deck_id}")

    return mana_curve_url


@login_required(login_url="login")
def deck_detail(request, deck_id):
    db = DynamoDBService()
    deck = db.get_deck(str(request.user.id), str(deck_id))

    if not deck:
        return redirect("deck_list")

    all_cards = db.get_deck_cards(str(deck_id))
    main_deck = [c for c in all_cards if not c.get("is_sideboard")]
    sideboard = [c for c in all_cards if c.get("is_sideboard")]

    # Organize main deck by type
    try:
        main_deck_organized = organize_cards_by_type(main_deck)
    except Exception:
        logger.exception("Failed to organize main deck for deck %s", deck_id)
        main_deck_organized = {}

    # Keep sideboard as flat list
    try:
        sideboard_list = organize_cards_by_type(sideboard)
    except Exception:
        logger.exception("Failed to organize sideboard for deck %s", deck_id)
        sideboard_list = {}
    sideboard_flat = []
    for cards_list in sideboard_list.values():
        sideboard_flat.extend(cards_list)

    # Pre-fetch all unique card data concurrently to avoid sequential API fallbacks
    scryfall_service = ScryfallS3Service()
    unique_card_names = {c["card_name"] for c in all_cards}
    
    card_data_cache = {}
    
    def fetch_card_data(card_name):
        return card_name, scryfall_service.get_card_by_name(card_name)
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_card = {executor.submit(fetch_card_data, name): name for name in unique_card_names}
        for future in as_completed(future_to_card):
            try:
                card_name, data = future.result()
                card_data_cache[card_name] = data
            except Exception as e:
                logger.exception(f"Failed to fetch data for card {future_to_card[future]}: {e}")
                card_data_cache[future_to_card[future]] = None

    # Calculate deck total price using pre-fetched data
    total_price = Decimal("0.00")

    def get_card_price(card_name):
        card_data = card_data_cache.get(card_name)
        if card_data:
            return Decimal(str(ScryfallS3Service.get_card_price(card_data)))
        return Decimal("0.00")

    for card in all_cards:
        price = get_card_price(card["card_name"])
        qty = Decimal(card["quantity"])
        total_price += price * qty
        
    # Generate Mana Curve Plot (with caching to avoid FileConvert API calls every time)
    mana_curve_url = _get_or_generate_mana_curve(deck, deck_id, main_deck, card_data_cache)

    context = {
        "deck": deck,
        "main_deck_organized": main_deck_organized,
        "sideboard_flat": sideboard_flat,
        "main_deck_count": sum(c["quantity"] for c in main_deck),
        "sideboard_count": sum(c["quantity"] for c in sideboard),
        "total_price": total_price,
        "mana_curve_url": mana_curve_url,
    }

    # Handle Voucher
    if deck.get("voucher_code"):
        # Apply 20% discount
        discount_percent = Decimal("0.20")
        discount_amount = total_price * discount_percent
        discounted_price = total_price - discount_amount
        context["discounted_price"] = round(discounted_price, 2)
        context["voucher_code"] = deck.get("voucher_code")
        context["voucher_image_url"] = deck.get("voucher_image_url")

    # Handle QR code from session
    qr_session_key = f"qr_code_{deck_id}"
    if qr_session_key in request.session:
        context["qr_code_url"] = request.session[qr_session_key]

    return render(request, "deck_builder/deck_detail.html", context)


@login_required(login_url="login")
def edit_deck(request, deck_id):
    db = DynamoDBService()
    deck = db.get_deck(str(request.user.id), str(deck_id))

    if request.method == "POST":
        deck_list_text = request.POST.get("deck_list", "")
        parsed_name, cards_data = parse_deck_list(deck_list_text)

        # Use form field deck_name if provided, else parsed name, else existing name
        deck_name = request.POST.get("deck_name") or parsed_name or deck.get("name")

        if cards_data:
            db.update_deck(str(request.user.id), str(deck_id), deck_name, cards_data)
            return redirect("deck_detail", deck_id=deck_id)

    # Get current deck contents for the form
    all_cards = db.get_deck_cards(str(deck_id))
    main_deck = sorted(
        [c for c in all_cards if not c.get("is_sideboard")],
        key=lambda x: x["card_name"],
    )
    sideboard = sorted(
        [c for c in all_cards if c.get("is_sideboard")], key=lambda x: x["card_name"]
    )

    # Format for textarea
    deck_text = "Deck\n"
    for card in main_deck:
        deck_text += f"{card['quantity']} {card['card_name']}\n"

    if sideboard:
        deck_text += "\nSideboard\n"
        for card in sideboard:
            deck_text += f"{card['quantity']} {card['card_name']}\n"

    context = {
        "deck": deck,
        "deck_text": deck_text,
    }
    return render(request, "deck_builder/edit_deck.html", context)


@login_required(login_url="login")
def delete_deck(request, deck_id):
    db = DynamoDBService()
    deck = db.get_deck(str(request.user.id), str(deck_id))

    if request.method == "POST":
        db.delete_deck(str(request.user.id), str(deck_id))
        return redirect("deck_list")

    return render(request, "deck_builder/delete_deck.html", {"deck": deck})


@login_required(login_url="login")
def get_recommendations(request, deck_id):
    """Get AI recommendations for improving a deck and optionally add them"""
    db = DynamoDBService()
    deck = db.get_deck(str(request.user.id), str(deck_id))

    if not deck:
        return redirect("deck_list")

    # Get all cards in the main deck
    all_cards = db.get_deck_cards(str(deck_id))
    main_deck = [c for c in all_cards if not c.get("is_sideboard")]

    # Handle POST request to add recommended cards to deck
    if request.method == "POST":
        card_names_to_add = request.POST.getlist("cards")
        if card_names_to_add:
            new_cards = [
                {"card_name": name, "quantity": 1, "is_sideboard": False}
                for name in card_names_to_add
            ]
            updated_cards = main_deck + new_cards
            db.update_deck(
                str(request.user.id), str(deck_id), deck.get("name"), updated_cards
            )
            return redirect("deck_detail", deck_id=deck_id)

    # Create list of card names for the AI
    card_names = [c["card_name"] for c in main_deck]

    # Get recommendations from AI
    agent = DeckRecommendationAgent()
    recommendations = agent.get_deck_improvement_recommendations(
        card_names, format_name="standard"
    )

    # Fetch card details using the existing cached service with parallelization
    scryfall_service = ScryfallS3Service()

    def fetch_card_details(card_name):
        """Fetch details for a single card (executed in parallel)"""
        card_data = scryfall_service.get_card_by_name(card_name)
        if card_data:
            return {
                "name": card_name,
                "type_line": card_data.get("type_line", ""),
                "image_url": ScryfallS3Service.get_card_image_url(card_data, "normal"),
                "mana_cost": ScryfallS3Service.get_card_mana_cost(card_data),
                "price": ScryfallS3Service.get_card_price(card_data),
            }
        else:
            return {
                "name": card_name,
                "type_line": "Unknown",
                "image_url": None,
                "mana_cost": "",
                "price": 0.0,
            }

    # Fetch all card details in parallel (max 5 workers to respect rate limits)
    recommendations_with_details = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all tasks
        future_to_card = {
            executor.submit(fetch_card_details, card_name): card_name
            for card_name in recommendations
        }
        # Collect results as they complete
        for future in as_completed(future_to_card):
            try:
                result = future.result()
                recommendations_with_details.append(result)
            except Exception as e:
                card_name = future_to_card[future]
                logger.exception(f"Failed to fetch details for card '{card_name}': {e}")
                # Add fallback entry for failed card
                recommendations_with_details.append({
                    "name": card_name,
                    "type_line": "Unknown",
                    "image_url": None,
                    "mana_cost": "",
                    "price": 0.0,
                })

    context = {
        "deck": deck,
        "recommendations": recommendations_with_details,
    }
    return render(request, "card_recommender/recommendations.html", context)


@require_http_methods(["POST"])
@login_required(login_url="login")
def generate_qr_code(request, deck_id):
    """Generate QR code for deck sharing and redirect back."""
    db = DynamoDBService()
    deck = db.get_deck(str(request.user.id), str(deck_id))

    if not deck:
        return redirect("deck_list")

    try:
        deck_url = request.build_absolute_uri(f"/decks/{deck_id}/")
        qr_code_url = QRService.get_qr_code_url(deck_id, deck_url)
        request.session[f"qr_code_{deck_id}"] = qr_code_url
    except Exception as e:
        logger.error(f"QR code generation failed: {e}")
    return redirect("deck_detail", deck_id=deck_id)


@require_http_methods(["POST"])
@login_required(login_url="login")
def add_voucher(request, deck_id):
    """Generate and add a voucher to the deck"""
    db = DynamoDBService()
    deck = db.get_deck(str(request.user.id), str(deck_id))

    if not deck:
        return redirect("deck_list")

    if deck.get("voucher_code"):
        # Already has voucher
        return redirect("deck_detail", deck_id=deck_id)

    # Generate voucher
    voucher_code = VoucherService.generate_voucher()

    if voucher_code:
        db.apply_voucher_to_deck(
            str(request.user.id),
            str(deck_id),
            voucher_code
        )

    return redirect("deck_detail", deck_id=deck_id)
