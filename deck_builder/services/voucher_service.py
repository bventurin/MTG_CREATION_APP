import os
import requests
import re
import logging

logger = logging.getLogger(__name__)

class VoucherService:
    @staticmethod
    def generate_voucher():
        
        #Calls the external Voucher API to generate a new voucher code.
        
        url = os.environ.get('VOUCHER_SERVICE_ENDPOINT')
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
                logger.error(f"Could not extract voucher ID from response: {response_text}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Error calling Voucher API: {str(e)}")
            return None
