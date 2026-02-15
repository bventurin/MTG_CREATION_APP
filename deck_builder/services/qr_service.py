import os
import requests
import base64
import urllib.parse
import logging

logger = logging.getLogger(__name__)

class QRService:
    """Service to handle QR code generation logic."""
    
    @staticmethod
    def get_qr_code_url(deck_url):
        """
        Generate a QR code URL for the given deck URL.
        Tries to use a private service defined in env vars first,
        falls back to a public API if that fails.
        """
        # Get QR code service endpoint from environment
        qr_endpoint = os.getenv('QR_CODE_ENDPOINT')
        
        if qr_endpoint:
            try:
                # Fetch server-side to avoid browser auth/CORS issues
                response = requests.get(qr_endpoint, params={'url': deck_url}, timeout=10)
                
                if response.status_code == 200:
                    # If service returns binary image, convert to Data URI
                    content_type = response.headers.get('Content-Type', '')
                    if 'image' in content_type:
                        img_b64 = base64.b64encode(response.content).decode('utf-8')
                        # Ensure content type is valid
                        if content_type == 'application/octet-stream':
                            content_type = 'image/png'
                        return f"data:{content_type};base64,{img_b64}"
                    # If service returns text/json URL
                    else:
                        return response.text.strip()
            except Exception as e:
                logger.error(f"Error fetching from private QR service: {e}")

        # Fallback to public API if .env is missing or private service fails
        encoded_url = urllib.parse.quote(deck_url)
        return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded_url}"