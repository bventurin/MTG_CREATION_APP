import os
import boto3
from datetime import datetime
from decimal import Decimal
import uuid

class DynamoDBService:
    
    def __init__(self):
        region = os.environ.get('AWS_REGION')
        self.dynamodb = boto3.resource('dynamodb', region_name=region) if region else boto3.resource('dynamodb')
        self.table_name = os.environ.get('DYNAMODB_TABLE_NAME', 'decks-db')
        self.table = self.dynamodb.Table(self.table_name)
    
    def create_deck(self, user_id, deck_name, cards_data):
        
        #Create a new deck
       
        deck_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        # Create deck item
        deck_item = {
            'pk': f'USER#{user_id}',
            'sk': f'DECK#{deck_id}',
            'type': 'deck',
            'deck_id': deck_id,
            'name': deck_name,
            'created_at': timestamp,
            'updated_at': timestamp
        }
        self.table.put_item(Item=deck_item)
        
        # Create card items
        for card in cards_data:
            card_item = {
                'pk': f'DECK#{deck_id}',
                'sk': f'CARD#{card["card_name"]}#{card.get("is_sideboard", False)}',
                'type': 'card',
                'deck_id': deck_id,
                'card_name': card['card_name'],
                'quantity': card['quantity'],
                'is_sideboard': card.get('is_sideboard', False)
            }
            self.table.put_item(Item=card_item)
        
        return deck_id
    
    def get_user_decks(self, user_id):
        # Get all decks for a user
        response = self.table.query(
            KeyConditionExpression='pk = :pk AND begins_with(sk, :sk)',
            ExpressionAttributeValues={
                ':pk': f'USER#{user_id}',
                ':sk': 'DECK#'
            }
        )
        return response.get('Items', [])
    
    def get_deck(self, user_id, deck_id):
        # Get a specific deck
        response = self.table.get_item(
            Key={
                'pk': f'USER#{user_id}',
                'sk': f'DECK#{deck_id}'
            }
        )
        return response.get('Item')
    
    def get_deck_cards(self, deck_id, is_sideboard=None):
        # Get all cards for a deck
        response = self.table.query(
            KeyConditionExpression='pk = :pk AND begins_with(sk, :sk)',
            ExpressionAttributeValues={
                ':pk': f'DECK#{deck_id}',
                ':sk': 'CARD#'
            }
        )
        
        items = response.get('Items', [])
        
        # Filter by sideboard if specified
        if is_sideboard is not None:
            items = [item for item in items if item.get('is_sideboard') == is_sideboard]
        
        return items
    
    def update_deck(self, user_id, deck_id, deck_name, cards_data):
        # Update a deck (name and all cards)
        timestamp = datetime.now().isoformat()
        
        # Update deck item
        self.table.update_item(
            Key={
                'pk': f'USER#{user_id}',
                'sk': f'DECK#{deck_id}'
            },
            UpdateExpression='SET #name = :name, updated_at = :updated',
            ExpressionAttributeNames={
                '#name': 'name'
            },
            ExpressionAttributeValues={
                ':name': deck_name,
                ':updated': timestamp
            }
        )
        
        # Delete old cards
        old_cards = self.get_deck_cards(deck_id)
        for card in old_cards:
            self.table.delete_item(
                Key={
                    'pk': card['pk'],
                    'sk': card['sk']
                }
            )
        
        # Add new cards
        for card in cards_data:
            card_item = {
                'pk': f'DECK#{deck_id}',
                'sk': f'CARD#{card["card_name"]}#{card.get("is_sideboard", False)}',
                'type': 'card',
                'deck_id': deck_id,
                'card_name': card['card_name'],
                'quantity': card['quantity'],
                'is_sideboard': card.get('is_sideboard', False)
            }
            self.table.put_item(Item=card_item)
        
        return True
    
    def delete_deck(self, user_id, deck_id):
        # Delete deck item 
        self.table.delete_item(
            Key={
                'pk': f'USER#{user_id}',
                'sk': f'DECK#{deck_id}'
            }
        )
        
        # Delete all cards
        cards = self.get_deck_cards(deck_id)
        for card in cards:
            self.table.delete_item(
                Key={
                    'pk': card['pk'],
                    'sk': card['sk']
                }
            )
        
        return True
    
    def apply_voucher_to_deck(self, user_id, deck_id, voucher_code):
        # Apply a voucher to a deck.
        timestamp = datetime.now().isoformat()
        
        self.table.update_item(
            Key={
                'pk': f'USER#{user_id}',
                'sk': f'DECK#{deck_id}'
            },
        # Sets voucher_code and voucher_discount (20%) on the deck item.
            UpdateExpression='SET voucher_code = :code, voucher_discount = :discount, updated_at = :updated',
            ExpressionAttributeValues={
                ':code': voucher_code,
                ':discount': Decimal('20'),  # 20% discount
                ':updated': timestamp
            }
        )
        return True
