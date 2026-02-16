from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from .services.dynamodb_service import DynamoDBService
from .services.card_organizer import organize_cards_by_type
from .services.qr_service import QRService
from .services.voucher_service import VoucherService
from .services.scryfall_s3_service import ScryfallS3Service
from card_recommender.services.ai_recommender import DeckRecommendationAgent
from decimal import Decimal
import re

# Create your views here.

def home(request):
    decks = []
    if request.user.is_authenticated:
        db = DynamoDBService()
        decks = db.get_user_decks(str(request.user.id))
        
        # Add card count, color identity, and representative card image for each deck
        from .services.card_organizer import get_deck_metadata
        
        for deck in decks:
            cards = db.get_deck_cards(deck['deck_id'])
            deck['card_count'] = sum(c['quantity'] for c in cards)
            
            # Get deck metadata (colors and representative card)
            main_deck = [c for c in cards if not c.get('is_sideboard')]
            metadata = get_deck_metadata(main_deck)
            
            deck['color_identity'] = metadata['colors']
            deck['representative_image'] = metadata['representative_image']
    
    return render(request, 'deck_builder/home.html', {'decks': decks})

@login_required(login_url='login')
def create_deck(request):
    db = DynamoDBService()
    
    if request.method == 'POST':
        deck_list_text = request.POST.get('deck_list', '')
        deck_name = 'Untitled Deck'
        cards_data = []
        
        lines = deck_list_text.strip().split('\n')
        current_section = None

        # Default to 'deck' section if no section headers are found
        if 'deck' not in [line.strip().lower() for line in lines if line.strip().lower() in ['deck', 'sideboard']]:
            current_section = 'deck'

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.lower() == 'deck':
                current_section = 'deck'
                continue
            elif line.lower() == 'sideboard':
                current_section = 'sideboard'
                continue
            elif line.lower().startswith('name '):
                deck_name = line[5:].strip()
                continue
            elif line.lower() in ['about']:
                continue

            # Card line format: "4 Card Name"
            match = re.match(r'^(\d+)\s+(.*)', line)
            if match and current_section:
                quantity = int(match.group(1))
                card_name = match.group(2).strip()
                is_sideboard = (current_section == 'sideboard')
                
                cards_data.append({
                    'card_name': card_name,
                    'quantity': quantity,
                    'is_sideboard': is_sideboard
                })

        if cards_data:
            deck_id = db.create_deck(str(request.user.id), deck_name, cards_data)
            return redirect('deck_detail', deck_id=deck_id)

    return render(request, 'deck_builder/create_deck.html')

@login_required(login_url='login')
def deck_list(request):
    db = DynamoDBService()
    decks = db.get_user_decks(str(request.user.id))
    
    # Add card count, color identity, and representative card image for each deck
    from .services.card_organizer import get_deck_metadata
    
    for deck in decks:
        cards = db.get_deck_cards(deck['deck_id'])
        deck['card_count'] = sum(c['quantity'] for c in cards)
        
        # Get deck metadata (colors and representative card)
        main_deck = [c for c in cards if not c.get('is_sideboard')]
        metadata = get_deck_metadata(main_deck)
        
        deck['color_identity'] = metadata['colors']
        deck['representative_image'] = metadata['representative_image']
    
    return render(request, 'deck_builder/deck_list.html', {'decks': decks})

@login_required(login_url='login')
def deck_detail(request, deck_id):
    db = DynamoDBService()
    deck = db.get_deck(str(request.user.id), str(deck_id))
    
    if not deck:
        return redirect('deck_list')
    
    all_cards = db.get_deck_cards(str(deck_id))
    main_deck = [c for c in all_cards if not c.get('is_sideboard')]
    sideboard = [c for c in all_cards if c.get('is_sideboard')]
    
    # Organize main deck by type
    main_deck_organized = organize_cards_by_type(main_deck)
    
    # Keep sideboard as flat list
    sideboard_list = organize_cards_by_type(sideboard)
    sideboard_flat = []
    for cards_list in sideboard_list.values():
        sideboard_flat.extend(cards_list)
    
    
    # Calculate deck total price
    scryfall_service = ScryfallS3Service()
    # Ensure cache is loaded
    scryfall_service.get_all_cards()
    
    total_price = Decimal('0.00')
    
    # helper to get price from card name
    def get_card_price(card_name):
        card_data = scryfall_service.get_card_by_name(card_name)
        if card_data:
            prices = card_data.get('prices', {})
            usd = prices.get('usd') or prices.get('usd_foil') or prices.get('eur')
            if usd:
                return Decimal(usd)
        return Decimal('0.00')

    for card in all_cards:
        price = get_card_price(card['card_name'])
        qty = Decimal(card['quantity'])
        total_price += price * qty
        
    context = {
        'deck': deck,
        'main_deck_organized': main_deck_organized,
        'sideboard_flat': sideboard_flat,
        'main_deck_count': sum(c['quantity'] for c in main_deck),
        'sideboard_count': sum(c['quantity'] for c in sideboard),
        'total_price': total_price,
    }
    
    # Handle Voucher
    if deck.get('voucher_code'):
        # Apply 20% discount
        discount_percent = Decimal('0.20')
        discount_amount = total_price * discount_percent
        discounted_price = total_price - discount_amount
        context['discounted_price'] = round(discounted_price, 2)
        context['voucher_code'] = deck.get('voucher_code')
        
    return render(request, 'deck_builder/deck_detail.html', context)

@login_required(login_url='login')
def edit_deck(request, deck_id):
    db = DynamoDBService()
    deck = db.get_deck(str(request.user.id), str(deck_id))
    
    if request.method == 'POST':
        deck_name = request.POST.get('deck_name', deck.get('name'))
        deck_list_text = request.POST.get('deck_list', '')
        
        main_deck = []
        sideboard = []
        
        lines = deck_list_text.strip().split('\n')
        current_section = None

        # Default to 'deck' section if no section headers are found
        if 'deck' not in [line.strip().lower() for line in lines if line.strip().lower() in ['deck', 'sideboard']]:
            current_section = 'deck'

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.lower() == 'deck':
                current_section = 'deck'
                continue
            elif line.lower() == 'sideboard':
                current_section = 'sideboard'
                continue
            elif line.lower().startswith('name '):
                # Allow overriding deck name from text
                if not request.POST.get('deck_name'):
                    deck_name = line[5:].strip()
                continue
            elif line.lower() in ['about']:
                continue

            # Card line format: "4 Card Name"
            match = re.match(r'^(\d+)\s+(.*)', line)
            if match and current_section:
                quantity = int(match.group(1))
                card_name = match.group(2).strip()
                
                if current_section == 'deck':
                    main_deck.append({'quantity': quantity, 'card_name': card_name, 'is_sideboard': False})
                elif current_section == 'sideboard':
                    sideboard.append({'quantity': quantity, 'card_name': card_name, 'is_sideboard': True})

        if main_deck or sideboard:
            all_cards = main_deck + sideboard
            db.update_deck(str(request.user.id), str(deck_id), deck_name, all_cards)
            return redirect('deck_detail', deck_id=deck_id)

    # Get current deck contents for the form
    all_cards = db.get_deck_cards(str(deck_id))
    main_deck = sorted([c for c in all_cards if not c.get('is_sideboard')], key=lambda x: x['card_name'])
    sideboard = sorted([c for c in all_cards if c.get('is_sideboard')], key=lambda x: x['card_name'])
    
    # Format for textarea
    deck_text = "Deck\n"
    for card in main_deck:
        deck_text += f"{card['quantity']} {card['card_name']}\n"
    
    if sideboard:
        deck_text += "\nSideboard\n"
        for card in sideboard:
            deck_text += f"{card['quantity']} {card['card_name']}\n"
    
    context = {
        'deck': deck,
        'deck_text': deck_text,
    }
    return render(request, 'deck_builder/edit_deck.html', context)

@login_required(login_url='login')
def delete_deck(request, deck_id):
    db = DynamoDBService()
    deck = db.get_deck(str(request.user.id), str(deck_id))
    
    if request.method == 'POST':
        db.delete_deck(str(request.user.id), str(deck_id))
        return redirect('deck_list')
    
    return render(request, 'deck_builder/delete_deck.html', {'deck': deck})

@login_required(login_url='login')
def get_recommendations(request, deck_id):
    """Get AI recommendations for improving a deck and optionally add them"""
    db = DynamoDBService()
    deck = db.get_deck(str(request.user.id), str(deck_id))
    
    if not deck:
        return redirect('deck_list')
    
    # Get all cards in the main deck
    all_cards = db.get_deck_cards(str(deck_id))
    main_deck = [c for c in all_cards if not c.get('is_sideboard')]
    
    # Handle POST request to add recommended cards to deck
    if request.method == 'POST':
        card_names_to_add = request.POST.getlist('cards')
        if card_names_to_add:
            # Add each recommended card with quantity 1
            new_cards = [{'card_name': name, 'quantity': 1, 'is_sideboard': False} for name in card_names_to_add]
            updated_cards = main_deck + new_cards
            db.update_deck(str(request.user.id), str(deck_id), deck.get('name'), updated_cards)
            return redirect('deck_detail', deck_id=deck_id)
    
    # Create list of card names for the AI
    card_names = [c['card_name'] for c in main_deck]
    
    # Get recommendations from AI
    agent = DeckRecommendationAgent()
    recommendations = agent.get_deck_improvement_recommendations(card_names, format_name="standard")
    
    # Fetch card details for recommendations (use cached data)
    from .services.scryfall_s3_service import ScryfallS3Service
    scryfall_service = ScryfallS3Service()
    all_cards = scryfall_service.get_all_cards()  # Cached - loads once
    
    # Create lookup map for fast searching
    cards_by_name = {card.get('name', '').lower(): card for card in all_cards}
    
    recommendations_with_details = []
    for card_name in recommendations:
        card_data = cards_by_name.get(card_name.lower())
        if card_data:
            # Extract price
            prices = card_data.get('prices', {})
            usd_price = prices.get('usd')
            try:
                if usd_price is None or usd_price == '':
                    usd_price = 0.0
                else:
                    usd_price = float(usd_price)
            except (ValueError, TypeError):
                usd_price = 0.0
            
            recommendations_with_details.append({
                'name': card_name,
                'type_line': card_data.get('type_line', ''),
                'image_url': ScryfallS3Service.get_card_image_url(card_data, 'normal'),
                'mana_cost': card_data.get('mana_cost', ''),
                'price': usd_price,
            })
        else:
            recommendations_with_details.append({
                'name': card_name,
                'type_line': 'Unknown',
                'image_url': None,
                'mana_cost': '',
                'price': 0.0,
            })
    
    context = {
        'deck': deck,
        'recommendations': recommendations_with_details,
    }
    return render(request, 'card_recommender/recommendations.html', context)


@require_http_methods(["POST"])
@login_required(login_url='login')
def generate_qr_code(request, deck_id):
    """Generate QR code for deck sharing using external service"""
    try:
        # Build the deck URL
        deck_url = request.build_absolute_uri(f'/decks/{deck_id}/')
        
        # Generate QR code using service
        qr_code_url = QRService.get_qr_code_url(deck_id, deck_url)
            
        return JsonResponse({
            'success': True,
            'qr_code_url': qr_code_url,
            'deck_url': deck_url
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_http_methods(["POST"])
@login_required(login_url='login')
def add_voucher(request, deck_id):
    """Generate and add a voucher to the deck"""
    db = DynamoDBService()
    deck = db.get_deck(str(request.user.id), str(deck_id))
    
    if not deck:
        return redirect('deck_list')
        
    if deck.get('voucher_code'):
        # Already has voucher
        return redirect('deck_detail', deck_id=deck_id)
        
    # Generate voucher
    voucher_code = VoucherService.generate_voucher()
    
    if voucher_code:
        db.apply_voucher_to_deck(str(request.user.id), str(deck_id), voucher_code)
        
    return redirect('deck_detail', deck_id=deck_id)