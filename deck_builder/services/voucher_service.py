import os
import requests
import re
import logging
from datetime import datetime
from pathlib import Path
import uuid
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class VoucherService:
    @staticmethod
    def generate_voucher():

        # Calls the external Voucher API to generate a new voucher code.

        url = os.environ.get("VOUCHER_SERVICE_ENDPOINT")
        if not url:
            logger.error("VOUCHER_SERVICE_ENDPOINT environment variable not set")
            return None

        try:
            # The API expects a POST request with an empty JSON body
            response = requests.post(url, json={}, timeout=10)
            response.raise_for_status()

            response_text = response.text

            # Extract ID
            match = re.search(r"voucher ID is '([^']+)'", response_text)
            if match:
                return match.group(1)
            else:
                logger.error(
                    f"Could not extract voucher ID from response: {response_text}"
                )
                return None

        except requests.RequestException as e:
            logger.error(f"Error calling Voucher API: {str(e)}")
            return None

    @classmethod
    def _fileconvert_base_url(cls):
        url = os.environ.get("FILECONVERT_API_BASE_URL")
        if not url:
            raise ValueError("FILECONVERT_API_BASE_URL environment variable not set")
        return url.rstrip("/")

    @staticmethod
    def _load_font(size):
        """Load a scalable font when available, fallback to PIL default."""
        try:
            return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
        except OSError:
            return ImageFont.load_default()

    @staticmethod
    def _build_voucher_image(voucher_code):
        """Create a local JPEG voucher image and return file path + mime type."""
        temp_dir = Path(os.environ.get("VOUCHER_IMAGE_TEMP_DIR", "/tmp"))
        temp_dir.mkdir(parents=True, exist_ok=True)

        filename = f"voucher_{voucher_code}_{uuid.uuid4().hex[:8]}.jpg"
        file_path = temp_dir / filename

        width, height = 1200, 630
        image = Image.new("RGB", (width, height), color=(24, 24, 27))
        draw = ImageDraw.Draw(image)

        title_font = VoucherService._load_font(48)
        body_font = VoucherService._load_font(30)
        code_font = VoucherService._load_font(64)

        draw.text((60, 70), "Magic Deck Voucher", fill=(255, 255, 255), font=title_font)
        draw.rectangle(
            (60, 180, width - 60, 380),
            fill=(34, 197, 94),
            outline=(16, 185, 129),
            width=4,
        )
        draw.text((90, 210), "Voucher Code", fill=(20, 20, 20), font=body_font)
        draw.text((90, 275), voucher_code, fill=(0, 0, 0), font=code_font)
        draw.text(
            (60, 460),
            f"Generated at {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}",
            fill=(163, 163, 163),
            font=body_font,
        )
        draw.text(
            (60, 510),
            "Use this voucher to get 20% off your deck total.",
            fill=(214, 211, 209),
            font=body_font,
        )

        image.save(file_path, format="JPEG", quality=92)
        return str(file_path), "image/jpeg"

    @classmethod
    def _get_upload_url(cls, filename, content_type):
        """Step 1: request presigned upload URL."""
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

        payload = response.json()
        required_fields = ["upload_url", "download_url", "file_key"]
        missing = [field for field in required_fields if field not in payload]
        if missing:
            raise ValueError(
                f"Upload API response missing fields: {', '.join(missing)}"
            )

        return payload

    @staticmethod
    def _upload_binary_file(upload_url, file_path, content_type):
        """Step 2: upload raw binary to the presigned S3 URL with PUT."""
        with open(file_path, "rb") as file_obj:
            put_response = requests.put(
                upload_url,
                data=file_obj,
                headers={"Content-Type": content_type},
                timeout=60,
            )
        put_response.raise_for_status()

    @classmethod
    def _convert_image_to_png(cls, image_url):
        """Step 3: call conversion endpoint to convert uploaded image to PNG."""
        base_url = cls._fileconvert_base_url()
        endpoint = f"{base_url}/ConvertImage/"

        response = requests.post(
            endpoint,
            json={
                "image_url": image_url,
                "target_format": "png",
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()

        payload = response.json()
        if "url" not in payload:
            raise ValueError("ConvertImage response missing 'url'")
        return payload

    @classmethod
    def generate_and_convert_voucher_image(cls, voucher_code):
        """Generate local voucher image, upload it, and convert it to PNG.

        Returns:
            dict | None: {
                'source_download_url': str,
                'converted_url': str,
                'converted_key': str | None,
                'source_file_key': str,
            }
        """
        local_file_path = None

        try:
            local_file_path, source_content_type = cls._build_voucher_image(
                voucher_code
            )
            upload_meta = cls._get_upload_url(
                filename=Path(local_file_path).name,
                content_type=source_content_type,
            )

            cls._upload_binary_file(
                upload_url=upload_meta["upload_url"],
                file_path=local_file_path,
                content_type=source_content_type,
            )

            conversion_result = cls._convert_image_to_png(upload_meta["download_url"])

            return {
                "source_download_url": upload_meta["download_url"],
                "source_file_key": upload_meta["file_key"],
                "converted_url": conversion_result.get("url"),
                "converted_key": conversion_result.get("key"),
            }
        except (requests.RequestException, ValueError, OSError) as exc:
            logger.error("Voucher image upload/convert flow failed: %s", exc)
            return None
        finally:
            if local_file_path:
                try:
                    os.remove(local_file_path)
                except OSError:
                    logger.warning(
                        "Could not delete temporary voucher image: %s", local_file_path
                    )
