import requests
import os
import logging
import base64

logger = logging.getLogger(__name__)


class QRService:
    # Service to handle QR code generation logic

    @staticmethod
    def get_qr_code_url(deck_id, deck_url):
        # Generate a QR code URL for the given deck URL.
        qr_endpoint = os.getenv("QR_CODE_ENDPOINT")

        if not qr_endpoint:
            raise Exception("QR_CODE_ENDPOINT environment variable not set")

        try:
            # Use POST to trigger the Lambda function
            # Sending JSON payload with deck_id and url
            payload = {"deck_id": str(deck_id), "url": deck_url}

            response = requests.post(qr_endpoint, json=payload, timeout=10)

            if response.status_code == 200:
                # Expecting the Lambda to return the S3 URL in JSON format
                qr_url = None
                try:
                    data = response.json()
                    qr_url = data.get("qrcode_image_url") or data.get("url")
                except ValueError:
                    qr_url = response.text.strip()

                # Download the image and convert to base64
                if qr_url and qr_url.startswith("https"):
                    try:
                        img_response = requests.get(qr_url, timeout=10)
                        if img_response.status_code == 200:
                            img_b64 = base64.b64encode(img_response.content).decode(
                                "utf-8"
                            )
                            content_type = img_response.headers.get(
                                "Content-Type", "image/png"
                            )
                            return f"data:{content_type};base64,{img_b64}"
                    except Exception as e:
                        logger.warning(f"Could not download QR image from URL: {e}")

                return qr_url
            else:
                # Log the specific error from API Gateway/Lambda
                logger.error(
                    f"QR Service failed: {response.status_code} - {response.text}"
                )
                raise Exception(f"External service returned {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching from private QR service: {e}")
            # Re-raise exception so the view knows it failed
            raise e
