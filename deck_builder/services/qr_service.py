import requests
import os
import logging
import base64

logger = logging.getLogger(__name__)


class QRService:
    # Service to handle QR code generation logic

    @staticmethod
    def _download_as_base64(url: str) -> str | None:
        """Download an image URL and return a data-URI string, or None on failure."""
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                return None
            img_b64 = base64.b64encode(resp.content).decode("utf-8")
            content_type = resp.headers.get("Content-Type", "image/png")
            return f"data:{content_type};base64,{img_b64}"
        except Exception as e:
            logger.warning(f"Could not download QR image from URL: {e}")
            return None

    @staticmethod
    def get_qr_code_url(deck_id, deck_url):
        """Generate a QR code URL for the given deck URL."""
        qr_endpoint = os.getenv("QR_CODE_ENDPOINT")
        if not qr_endpoint:
            raise Exception("QR_CODE_ENDPOINT environment variable not set")

        try:
            payload = {"deck_id": str(deck_id), "url": deck_url}
            response = requests.post(qr_endpoint, json=payload, timeout=10)

            if response.status_code != 200:
                logger.error(f"QR Service failed: {response.status_code} - {response.text}")
                raise Exception(f"External service returned {response.status_code}")

            # Parse QR URL from response
            try:
                data = response.json()
                qr_url = data.get("qrcode_image_url") or data.get("url")
            except ValueError:
                qr_url = response.text.strip()

            # Prefer embedded base64 over a raw HTTPS URL
            if qr_url and qr_url.startswith("https"):
                embedded = QRService._download_as_base64(qr_url)
                if embedded:
                    return embedded

            return qr_url
        except Exception as e:
            logger.error(f"Error fetching from private QR service: {e}")
            raise e
