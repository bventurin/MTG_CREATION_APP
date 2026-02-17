"""
Service to fetch and cache Scryfall card data from S3.
"""

import json
import gzip
import boto3
import logging
import os
import requests
import unicodedata
from io import BytesIO
from typing import List, Dict, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# Initialize S3 client using AWS credentials from environment/IAM
s3_client = boto3.client(
    's3',
    region_name=os.getenv('AWS_REGION'),
)


@lru_cache(maxsize=1)
def _get_all_cards_cached(bucket_name: str, bulk_type: str) -> List[Dict]:
    # Cached function to fetch all cards from S3 (only loads once per bucket/type combo).
    try:
        data_key = f"scryfall/{bulk_type}/latest.json"
        logger.info(f"Loading cards from S3: s3://{bucket_name}/{data_key}")
        
        response = s3_client.get_object(Bucket=bucket_name, Key=data_key)
        content = response['Body'].read()
        
        # Check if content is gzipped
        if content[:2] == b'\x1f\x8b':  # gzip magic number
            content = gzip.decompress(content)
        
        cards = json.loads(content)
        logger.info(f"Successfully loaded {len(cards)} cards from S3")
        return cards
        
    except s3_client.exceptions.NoSuchKey:
        logger.error(f"Card data not found at s3://{bucket_name}/scryfall/{bulk_type}/latest.json")
        return []
    except Exception as e:
        logger.error(f"Error fetching cards from S3: {str(e)}")
        return []


# Global name index for O(1) lookups (built once)
_cards_index = None


def _build_index(cards: List[Dict]) -> Dict[str, Dict]:
    # Build a name -> card dictionary for O(1) lookups.
    index = {}
    for card in cards:
        card_name = card.get('name', '').lower().strip()
        if card_name:
            index[card_name] = card
            if ' // ' in card_name:
                front_face = card_name.split(' // ')[0].strip()
                if front_face and front_face not in index:
                    index[front_face] = card

        printed_name = card.get('printed_name', '').lower().strip()
        if printed_name and printed_name not in index:
            index[printed_name] = card

        flavor_name = card.get('flavor_name', '').lower().strip()
        if flavor_name and flavor_name not in index:
            index[flavor_name] = card

    return index


def _string_similarity(a: str, b: str) -> float:
    # Simple positional character similarity score.
    if a == b:
        return 1.0
    if len(a) == 0 or len(b) == 0:
        return 0.0
    matches = sum(1 for i, c in enumerate(a) if i < len(b) and c == b[i])
    return matches / max(len(a), len(b))


class ScryfallS3Service:
    # Service to interact with Scryfall card data stored in S3.
    
    def __init__(self, bucket_name: Optional[str] = None, bulk_type: str = 'default_cards'):
        self.bucket_name = bucket_name or os.getenv('AWS_S3_BUCKET_NAME', 'magic-card-data')
        self.bulk_type = bulk_type
    
    def _get_index(self) -> Dict[str, Dict]:
        # Return (and lazily build) the global name index.
        global _cards_index
        if _cards_index is None:
            _cards_index = _build_index(self.get_all_cards())
        return _cards_index
    
    def get_sync_metadata(self) -> Dict:
        # Fetch metadata about the latest sync from Lambda.
        try:
            metadata_key = f"scryfall/{self.bulk_type}/sync_metadata.json"
            response = s3_client.get_object(Bucket=self.bucket_name, Key=metadata_key)
            metadata = json.loads(response['Body'].read())
            return metadata
        except s3_client.exceptions.NoSuchKey:
            logger.warning(f"Sync metadata not found at {metadata_key}")
            return None
        except Exception as e:
            logger.error(f"Error fetching metadata: {str(e)}")
            return None
    
    def get_all_cards(self) -> List[Dict]:
        # Fetch all cards from the latest bulk data file in S3. 
        return _get_all_cards_cached(self.bucket_name, self.bulk_type)
    
    def search_cards(self, query: str) -> List[Dict]:
        # Search cards by name, type, or oracle text.
        cards = self.get_all_cards()
        query_lower = query.lower()
        
        results = []
        for card in cards:
            if query_lower in card.get('name', '').lower():
                results.append(card)
            elif query_lower in card.get('type_line', '').lower():
                results.append(card)
            elif query_lower in card.get('oracle_text', '').lower():
                results.append(card)
        
        return results
    
    def get_card_by_name(self, name: str) -> Optional[Dict]:
        # Get a single card by name using O(1) index lookup.
        # Falls back to: normalized chars, fuzzy match, then live Scryfall API.
        index = self._get_index()
        name_lower = name.lower().strip()
        
        # O(1) exact match
        if name_lower in index:
            return index[name_lower]
        
        # Try without accented characters (e.g. "Æ" -> "A")
        normalized = unicodedata.normalize('NFD', name_lower)
        normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        if normalized in index:
            return index[normalized]
        
        # Fuzzy match
        for indexed_name, card in index.items():
            if (name_lower in indexed_name or indexed_name in name_lower or
                _string_similarity(name_lower, indexed_name) > 0.85):
                return card
        
        # Final fallback: live Scryfall API
        try:
            resp = requests.get(
                'https://api.scryfall.com/cards/named',
                params={'fuzzy': name},
                timeout=5
            )
            if resp.status_code == 200:
                card_data = resp.json()
                # Cache it for future lookups
                index[name_lower] = card_data
                logger.info(f"Fetched '{name}' from Scryfall API (not in S3 bulk data)")
                return card_data
        except Exception as e:
            logger.warning(f"Scryfall API fallback failed for '{name}': {e}")
        
        return None
    
    def get_card_by_scryfall_id(self, scryfall_id: str) -> Optional[Dict]:
        # Get a single card by Scryfall ID.
        cards = self.get_all_cards()
        for card in cards:
            if card.get('id') == scryfall_id:
                return card
        return None
    
    @staticmethod
    def get_card_image_url(card: Dict, format: str = 'normal') -> Optional[str]:
        # Extract image URL from card object.
        # Falls back to card_faces[0] for multiface cards (DFCs, split, flip).
        image_uris = card.get('image_uris')
        if not image_uris and card.get('card_faces'):
            image_uris = card['card_faces'][0].get('image_uris', {})
        return image_uris.get(format) if image_uris else None
    
    @staticmethod
    def format_card_for_display(card: Dict) -> Dict:
        # Format card data for frontend display.
        # Pulls mana_cost and oracle_text from card_faces[0] for multiface cards.
        mana_cost = card.get('mana_cost', '')
        oracle_text = card.get('oracle_text', '')
        if not mana_cost and card.get('card_faces'):
            mana_cost = card['card_faces'][0].get('mana_cost', '')
        if not oracle_text and card.get('card_faces'):
            oracle_text = card['card_faces'][0].get('oracle_text', '')
        
        return {
            'id': card.get('id'),
            'name': card.get('name'),
            'mana_cost': mana_cost,
            'type_line': card.get('type_line'),
            'oracle_text': oracle_text,
            'power': card.get('power'),
            'toughness': card.get('toughness'),
            'colors': card.get('colors', []),
            'color_identity': card.get('color_identity', []),
            'set': card.get('set'),
            'released_at': card.get('released_at'),
            'image_url': ScryfallS3Service.get_card_image_url(card, 'normal'),
            'image_url_large': ScryfallS3Service.get_card_image_url(card, 'large'),
        }
    
    @staticmethod
    def clear_index():
        # Clear the global index (useful for testing or manual refresh).
        global _cards_index
        _cards_index = None
