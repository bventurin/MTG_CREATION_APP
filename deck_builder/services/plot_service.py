import os
import requests
import logging
from pathlib import Path
import uuid

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
        """Step 1: Request presigned upload URL."""
        base_url = cls._fileconvert_base_url()
        endpoint = f"{base_url}/UploadBucket/"

        response = requests.get(
            endpoint,
            params={
                "filename": filename,
                "content_type": content_type,
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _upload_data(upload_url, data_string, content_type="text/csv"):
        """Step 2: Upload the raw CSV string to S3."""
        put_response = requests.put(
            upload_url,
            data=data_string.encode('utf-8'),
            headers={"Content-Type": content_type},
            timeout=60,
        )
        put_response.raise_for_status()

    @classmethod
    def _generate_plot(cls, data_url, plot_type="bar"):
        """Step 3: Call the ConvertData endpoint to generate a plot."""
        base_url = cls._fileconvert_base_url()
        endpoint = f"{base_url}/ConvertData/"

        response = requests.post(
            endpoint,
            json={
                "data_url": data_url,
                "action": "plot",
                "plot_type": plot_type
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()

        payload = response.json()
        if "url" not in payload:
            raise ValueError("ConvertData response missing 'url'")
        return payload.get("url")

    @classmethod
    def generate_mana_curve_plot(cls, main_deck, scryfall_service):
        """
        Takes the main_deck list and generates a bar chart URL of the mana curve.
        """
        try:
            # 1. Calculate Mana Curve
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
                return None

            # 2. Build CSV string
            csv_data = "Mana Value,Cards\n"
            for cmc in range(0, 7):
                label = f"{cmc}+" if cmc == 6 else str(cmc)
                csv_data += f"{label},{mana_curve[cmc]}\n"

            # 3. Upload and Plot via API
            filename = f"curve_{uuid.uuid4().hex[:8]}.csv"
            upload_meta = cls._get_upload_url(filename)
            
            # Upload the CSV string
            cls._upload_data(upload_meta["upload_url"], csv_data)
            
            # Generate the plot
            plot_url = cls._generate_plot(upload_meta["download_url"], "bar")
            
            return plot_url

        except Exception as e:
            logger.error(f"Failed to generate mana curve plot: {e}")
            return None
