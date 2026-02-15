"""
Service to fetch and cache Scryfall card data from S3.
"""

import json
import gzip
import boto3
import logging
import os
from io import BytesIO
from typing import List, Dict, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)

# Initialize S3 client using AWS credentials from environment/IAM
s3_client = boto3.client(
    's3',
    region_name=os.getenv('AWS_REGION'),
)


class ScryfallS3Service:
    """Service to interact with Scryfall card data stored in S3."""
    
    def __init__(self, bucket_name: Optional[str] = None, bulk_type: str = 'default_cards'):
        self.bucket_name = bucket_name or os.getenv('AWS_S3_BUCKET_NAME', 'magic-card-data')
        self.bulk_type = bulk_type
    
    def get_sync_metadata(self) -> Dict:
        """
        Fetch metadata about the latest sync from Lambda.
        
        Returns:
            Dict with sync info or None if not found
        """
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
        """
        Fetch all cards from the latest bulk data file in S3.
        
        Returns:
            List of card objects
        """
        try:
            # Fetch from the S3 location where Lambda stores the data
            data_key = f"scryfall/{self.bulk_type}/latest.json"
            logger.info(f"Fetching cards from S3: s3://{self.bucket_name}/{data_key}")
            
            # Download the file
            response = s3_client.get_object(Bucket=self.bucket_name, Key=data_key)
            content = response['Body'].read()
            
            # Check if content is gzipped
            if content[:2] == b'\x1f\x8b':  # gzip magic number
                content = gzip.decompress(content)
            
            cards = json.loads(content)
            
            logger.info(f"Successfully loaded {len(cards)} cards from S3")
            return cards
            
        except s3_client.exceptions.NoSuchKey:
            logger.error(f"Card data not found at s3://{self.bucket_name}/scryfall/{self.bulk_type}/latest.json")
            logger.info("Lambda will populate this data on its weekly sync")
            return []
        except Exception as e:
            logger.error(f"Error fetching cards from S3: {str(e)}")
            return []
    
    def search_cards(self, query: str) -> List[Dict]:
        """
        Search cards by name or features.
        
        Args:
            query: Search term (card name, type, etc.)
        
        Returns:
            List of matching cards
        """
        cards = self.get_all_cards()
        query_lower = query.lower()
        
        results = []
        for card in cards:
            # Search by name
            if query_lower in card.get('name', '').lower():
                results.append(card)
            # Search by type
            elif query_lower in card.get('type_line', '').lower():
                results.append(card)
            # Search by oracle text
            elif query_lower in card.get('oracle_text', '').lower():
                results.append(card)
        
        return results
    
    def get_card_by_name(self, name: str) -> Optional[Dict]:
        """
        Get a single card by exact name match.
        
        Args:
            name: Card name
        
        Returns:
            Card object or None
        """
        cards = self.get_all_cards()
        for card in cards:
            if card.get('name', '').lower() == name.lower():
                return card
        return None
    
    def get_card_by_scryfall_id(self, scryfall_id: str) -> Optional[Dict]:
        """
        Get a single card by Scryfall ID.
        
        Args:
            scryfall_id: Scryfall UUID
        
        Returns:
            Card object or None
        """
        cards = self.get_all_cards()
        for card in cards:
            if card.get('id') == scryfall_id:
                return card
        return None
    
    @staticmethod
    def get_card_image_url(card: Dict, format: str = 'normal') -> Optional[str]:
        """
        Extract image URL from card object.
        
        Args:
            card: Card object from Scryfall
            format: Image format - 'png', 'border_crop', 'art_crop', 'large', 'normal', 'small'
        
        Returns:
            Image URL or None
        """
        image_uris = card.get('image_uris', {})
        return image_uris.get(format)
    
    @staticmethod
    def format_card_for_display(card: Dict) -> Dict:
        """
        Format card data for frontend display.
        
        Args:
            card: Raw card object from Scryfall
        
        Returns:
            Formatted card data
        """
        return {
            'id': card.get('id'),
            'name': card.get('name'),
            'mana_cost': card.get('mana_cost', ''),
            'type_line': card.get('type_line'),
            'oracle_text': card.get('oracle_text', ''),
            'power': card.get('power'),
            'toughness': card.get('toughness'),
            'colors': card.get('colors', []),
            'color_identity': card.get('color_identity', []),
            'set': card.get('set'),
            'released_at': card.get('released_at'),
            'image_url': ScryfallS3Service.get_card_image_url(card, 'normal'),
            'image_url_large': ScryfallS3Service.get_card_image_url(card, 'large'),
        }
