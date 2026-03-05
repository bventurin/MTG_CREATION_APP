"""
Service to fetch and cache Scryfall card data from S3.
Uses streaming JSON parsing (ijson) to avoid loading the entire
bulk data file into memory at once.
"""

import json
import gzip
import boto3
import ijson
import logging
import os
import requests
import unicodedata
import time
from io import BytesIO
from typing import List, Dict, Optional
from functools import lru_cache
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Fields the application actually uses — everything else is stripped to save memory.
NEEDED_FIELDS = {
    "name",
    "printed_name",
    "flavor_name",
    "type_line",
    "image_uris",
    "card_faces",
    "mana_cost",
    "oracle_text",
    "colors",
    "prices",
    "cmc",
}

# Maximum number of Scryfall API fallback calls per request
MAX_API_FALLBACKS = 50

# Initialize S3 client using AWS credentials from environment/IAM
s3_client = boto3.client(
    "s3",
    region_name=os.getenv("AWS_REGION"),
)


def _strip_card(card: Dict) -> Dict:
    """Keep only the fields the app needs, dramatically reducing memory."""
    stripped = {k: v for k, v in card.items() if k in NEEDED_FIELDS}

    # For card_faces, strip each face to only needed fields too
    if "card_faces" in stripped and stripped["card_faces"]:
        stripped["card_faces"] = [
            {k: v for k, v in face.items() if k in NEEDED_FIELDS}
            for face in stripped["card_faces"]
        ]

    return stripped


def _stream_parse_cards(content: bytes) -> List[Dict]:
    """
    Parse cards from JSON content using ijson streaming parser.
    Only keeps needed fields per card to minimize memory usage.
    """
    stream = BytesIO(content)
    cards = []

    try:
        # ijson.items parses the top-level JSON array one item at a time
        for card in ijson.items(stream, "item"):
            cards.append(_strip_card(card))
    except Exception as e:
        logger.error(f"Streaming JSON parse error: {type(e).__name__}: {e}")
        # Return whatever we managed to parse
        if cards:
            logger.warning(f"Partial parse: recovered {len(cards)} cards before error")

    return cards


@lru_cache(maxsize=1)
def _get_all_cards_cached(bucket_name: str, bulk_type: str) -> List[Dict]:
    """Fetch all cards from S3, streaming the JSON to avoid MemoryError."""
    try:
        data_key = f"scryfall/{bulk_type}/latest.json"
        logger.info(f"Loading cards from S3: s3://{bucket_name}/{data_key}")

        response = s3_client.get_object(Bucket=bucket_name, Key=data_key)

        # Stream the body in chunks to handle gzip detection
        body = response["Body"].read()

        # Check if content is gzipped
        if body[:2] == b"\x1f\x8b":  # gzip magic number
            logger.info("Decompressing gzipped S3 data...")
            body = gzip.decompress(body)

        logger.info(f"S3 data size: {len(body) / (1024*1024):.1f} MB, parsing with streaming parser...")
        cards = _stream_parse_cards(body)

        
        del body

        logger.info(f"Successfully loaded and stripped {len(cards)} cards from S3")
        return cards

    except s3_client.exceptions.NoSuchKey:
        logger.error(
            f"Card data not found at s3://{bucket_name}/scryfall/{bulk_type}/latest.json"
        )
        return []
    except MemoryError:
        logger.error("MemoryError while loading S3 data — instance has insufficient RAM")
        logger.error(f"S3 Context: Bucket={bucket_name}, Region={os.getenv('AWS_REGION')}")
        return []
    except Exception as e:
        logger.error(f"Error fetching cards from S3: {type(e).__name__}: {str(e)}")
        logger.error(f"S3 Context: Bucket={bucket_name}, Region={os.getenv('AWS_REGION')}")
        return []


# Global name index for O(1) lookups (built once)
_cards_index = None


def _build_index(cards: List[Dict]) -> Dict[str, Dict]:
    """Build a name -> card dictionary for O(1) lookups."""
    index = {}
    for card in cards:
        card_name = card.get("name", "").lower().strip()
        if card_name:
            index[card_name] = card
            if " // " in card_name:
                front_face = card_name.split(" // ")[0].strip()
                if front_face and front_face not in index:
                    index[front_face] = card

        printed_name = card.get("printed_name", "").lower().strip()
        if printed_name and printed_name not in index:
            index[printed_name] = card

        flavor_name = card.get("flavor_name", "").lower().strip()
        if flavor_name and flavor_name not in index:
            index[flavor_name] = card

    return index


def _string_similarity(a: str, b: str) -> float:
    """Simple positional character similarity score."""
    if a == b:
        return 1.0
    if len(a) == 0 or len(b) == 0:
        return 0.0
    matches = sum(1 for i, c in enumerate(a) if i < len(b) and c == b[i])
    return matches / max(len(a), len(b))


class ScryfallS3Service:
    """Service to interact with Scryfall card data stored in S3."""

    def __init__(
        self, bucket_name: Optional[str] = None, bulk_type: str = "default_cards"
    ):
        self.bucket_name = bucket_name or os.getenv(
            "AWS_S3_BUCKET_NAME", "magic-card-data"
        )
        self.bulk_type = bulk_type

    def _get_index(self) -> Dict[str, Dict]:
        """Return (and lazily build) the global name index."""
        global _cards_index
        if _cards_index is None:
            cards = self.get_all_cards()
            if not cards:
                logger.warning(
                    "Empty card list from get_all_cards, creating empty index "
                    "to prevent repeated S3 failures"
                )
                _cards_index = {}
            else:
                _cards_index = _build_index(cards)
        return _cards_index

    def get_all_cards(self) -> List[Dict]:
        """Fetch all cards from S3 with application-level caching."""
        cache_key = f"scryfall_cards_{self.bucket_name}_{self.bulk_type}"

        # Try to get from cache first
        cards = cache.get(cache_key)
        if cards is not None:
            logger.info(f"Loaded {len(cards)} cards from cache")
            return cards

        # Not in cache, fetch from S3
        logger.info(f"Cache miss for {cache_key}, fetching from S3...")
        cards = _get_all_cards_cached(self.bucket_name, self.bulk_type)

        # Store in cache for 24 hours (86400 seconds) since the Lambda only updates daily
        if cards:
            cache.set(cache_key, cards, 86400)
            logger.info(f"Cached {len(cards)} cards for 24 hours")

        return cards

    def get_card_by_name(self, name: str, allow_api_fallback: bool = True) -> Optional[Dict]:
        """Get a single card by name using O(1) index lookup.
        Falls back to: normalized chars, fuzzy match, then live Scryfall API.

        Args:
            allow_api_fallback: If False, skip the live Scryfall API call.
                Use False for bulk operations (home page, deck list) to
                avoid slow API calls for every missing card.
        """
        index = self._get_index()
        name_lower = name.lower().strip()

        if name_lower in index:
            cached = index[name_lower]
            if cached is not None:
                return cached
            if not allow_api_fallback:
                return None
        else:
            normalized = unicodedata.normalize("NFD", name_lower)
            normalized = "".join(
                c for c in normalized if unicodedata.category(c) != "Mn"
            )
            if normalized in index:
                return index[normalized]

            # Fuzzy match
            for indexed_name, card in index.items():
                if card is None:
                    continue

                if (
                    name_lower in indexed_name
                    or indexed_name in name_lower
                    or _string_similarity(name_lower, indexed_name) > 0.85
                ):
                    return card

            # Not found via fuzzy either
            if not allow_api_fallback:
                return None

        # Track fallbacks per request to prevent server timeout
        if not hasattr(self, '_api_fallback_count'):
            self._api_fallback_count = 0

        if self._api_fallback_count >= MAX_API_FALLBACKS:
            logger.warning(
                f"Exceeded maximum Scryfall API fallbacks ({MAX_API_FALLBACKS}) "
                f"for this request. Skipping '{name}' to prevent server timeout. "
                f"Please check your S3 bulk data configuration."
            )
            # Cache failure
            index[name_lower] = None
            return None

        try:
            self._api_fallback_count += 1
            # Scryfall requests 50-100ms delay between requests (max 10/sec)
            time.sleep(0.1)
            resp = requests.get(
                "https://api.scryfall.com/cards/named",
                params={"fuzzy": name},
                timeout=5,
            )
            if resp.status_code == 200:
                card_data = _strip_card(resp.json())
                # Cache it for future lookups
                index[name_lower] = card_data
                logger.info(f"Fetched '{name}' from Scryfall API (not in S3 bulk data)")
                return card_data
            elif resp.status_code == 429:
                logger.warning(f"Scryfall API rate limit (429) hit for '{name}'")
                # Don't cache None for rate limits, so we can try again next time!
                return None
            else:
                logger.warning(
                    f"Card not found in Scryfall database: {name} "
                    f"(Status: {resp.status_code})"
                )
                # Cache the failure so we don't spam the API on subsequent loops
                index[name_lower] = None

        except Exception as e:
            logger.warning(f"Scryfall API fallback failed for '{name}': {e}")
            # Cache the failure to prevent timeout delays on every request
            index[name_lower] = None

        return None

    @staticmethod
    def get_card_image_url(card: Dict, format: str = "normal") -> Optional[str]:
        """Extract image URL from card object.
        Falls back to card_faces[0] for multiface cards (DFCs, split, flip).
        """
        image_uris = card.get("image_uris")
        if not image_uris and card.get("card_faces"):
            image_uris = card["card_faces"][0].get("image_uris", {})
        return image_uris.get(format) if image_uris else None

    @staticmethod
    def get_card_price(card: Dict) -> float:
        """Extract price with fallback: usd -> usd_foil -> eur -> tix"""
        prices = card.get("prices", {})
        usd_price = (
            prices.get("usd")
            or prices.get("usd_foil")
            or prices.get("eur")
            or prices.get("tix")
        )
        try:
            return float(usd_price) if usd_price else 0.0
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def get_card_mana_cost(card: Dict) -> str:
        """Get mana_cost with card_faces fallback for multiface cards"""
        mana_cost = card.get("mana_cost", "")
        if not mana_cost and card.get("card_faces"):
            mana_cost = card["card_faces"][0].get("mana_cost", "")
        return mana_cost
