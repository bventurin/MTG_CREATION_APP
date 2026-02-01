import requests
import urllib.parse

class ScryfallService:
    BASE_URL = "https://api.scryfall.com"

    @staticmethod
    def search_cards(query):
        """
        Search for cards on Scryfall API based on a query string.
        """
        encoded_query = urllib.parse.quote(query)
        url = f"{ScryfallService.BASE_URL}/cards/search?q={encoded_query}"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get('data', [])
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data from Scryfall: {e}")
            return []

    @staticmethod
    def get_card_by_name(name):
        """
        Get a specific card by exact name.
        """
        encoded_name = urllib.parse.quote(name)
        url = f"{ScryfallService.BASE_URL}/cards/named?exact={encoded_name}"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching card {name}: {e}")
            return None
