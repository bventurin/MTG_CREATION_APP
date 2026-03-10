import os
import requests
import logging
from pathlib import Path
import uuid
import time
import threading
from django.core.cache import cache

logger = logging.getLogger(__name__)

class PlotService:
    @classmethod
    def _fileconvert_base_url(cls):
        url = os.environ.get("FILECONVERT_API_BASE_URL")
        if not url:
            logger.error("FILECONVERT_API_BASE_URL environment variable not set")
            # Fallback to the public URL if env is missing locally
            return "https://nzaxqvcb3d.execute-api.us-east-1.amazonaws.com/Prod"
        return url.rstrip("/")

    @classmethod
    def _get_upload_url(cls, filename, content_type="text/csv"):
        """Step 1: Request presigned upload URL with retry logic."""
        base_url = cls._fileconvert_base_url()
        endpoint = f"{base_url}/UploadBucket/"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    endpoint,
                    params={
                        "filename": filename,
                        "content_type": content_type,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(f"Upload URL request failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Upload URL request failed after {max_retries} attempts: {e}")
                    raise

    @staticmethod
    def _upload_data(upload_url, data_string, content_type="text/csv"):
        """Step 2: Upload the raw CSV string to S3 with retry logic."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                put_response = requests.put(
                    upload_url,
                    data=data_string.encode('utf-8'),
                    headers={"Content-Type": content_type},
                    timeout=60,
                )
                put_response.raise_for_status()
                return
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Data upload failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Data upload failed after {max_retries} attempts: {e}")
                    raise

    @classmethod
    def _generate_plot(cls, data_url, plot_type="bar"):
        """Step 3: Call the ConvertData endpoint to generate a plot with retry logic."""
        base_url = cls._fileconvert_base_url()
        endpoint = f"{base_url}/ConvertData/"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    endpoint,
                    json={
                        "data_url": data_url,
                        "action": "plot",
                        "plot_type": plot_type
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=45,
                )
                response.raise_for_status()

                payload = response.json()
                if "url" not in payload:
                    raise ValueError("ConvertData response missing 'url'")
                return payload.get("url")
            except (requests.exceptions.RequestException, ValueError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Plot generation failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Plot generation failed after {max_retries} attempts: {e}")
                    raise

    @classmethod
    def generate_mana_curve_plot(cls, main_deck, scryfall_service):
        """
        Takes the main_deck list and generates a bar chart URL of the mana curve.
        """
        try:
            logger.info(f"Starting mana curve plot generation for deck with {len(main_deck)} cards")

            # Calculate Mana Curve
            mana_curve = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0} # 6 represents 6+

            for card in main_deck:
                qty = int(card.get("quantity", 1))
                card_data = scryfall_service.get_card_by_name(card["card_name"])

                # Default to 0 if not found
                cmc = 0
                if card_data:
                    cmc = int(card_data.get("cmc", 0))

                    # Ignore lands for the curve chart to make it cleaner
                    if "land" in str(card_data.get("type_line", "")).lower():
                        continue

                if cmc >= 6:
                    mana_curve[6] += qty
                else:
                    mana_curve[cmc] += qty

            # If the deck has no spells (only contained lands before), don't chart it
            if sum(mana_curve.values()) == 0:
                logger.info("Deck has no non-land spells, skipping mana curve plot")
                return None

            # 2. Build CSV string
            csv_data = "Mana Value,Cards\n"
            for cmc in range(0, 7):
                label = f"{cmc}+" if cmc == 6 else str(cmc)
                csv_data += f"{label},{mana_curve[cmc]}\n"

            # 3. Upload and Plot via API
            filename = f"curve_{uuid.uuid4().hex[:8]}.csv"
            logger.info(f"Requesting upload URL for {filename}")
            upload_meta = cls._get_upload_url(filename)

            # Upload the CSV string
            logger.info(f"Uploading CSV data to S3")
            cls._upload_data(upload_meta["upload_url"], csv_data)

            # Generate the plot
            logger.info(f"Requesting plot generation from FileConvert API")
            plot_url = cls._generate_plot(upload_meta["download_url"], "bar")

            logger.info(f"Successfully generated mana curve plot: {plot_url}")
            return plot_url

        except Exception as e:
            logger.error(f"Failed to generate mana curve plot after all retries: {e}", exc_info=True)
            return None

    @classmethod
    def generate_mana_curve_plot_async(cls, deck_id, main_deck, scryfall_service, cache_key):
        """
        Generate mana curve plot in a background thread and store in cache when ready.
        This allows the page to load immediately without waiting for plot generation.
        """
        def _generate_in_background():
            try:
                logger.info(f"Background plot generation started for deck {deck_id}")
                plot_url = cls.generate_mana_curve_plot(main_deck, scryfall_service)

                if plot_url:
                    # Store in cache for 24 hours
                    try:
                        cache.set(cache_key, plot_url, 86400)
                        logger.info(f"Background plot generation completed for deck {deck_id}, cached at key: {cache_key}")
                    except Exception as e:
                        logger.error(f"Failed to cache plot for deck {deck_id}: {e}")
                else:
                    logger.warning(f"Background plot generation returned None for deck {deck_id}")

            except Exception as e:
                logger.error(f"Background plot generation failed for deck {deck_id}: {e}", exc_info=True)

        # Start the background thread
        thread = threading.Thread(target=_generate_in_background, daemon=True)
        thread.start()
        logger.info(f"Background thread started for deck {deck_id} plot generation")
