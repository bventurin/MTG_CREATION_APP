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
    def get_commanders_for_colors(colors):
        """
        Get legendary creatures (potential commanders) for the given color identity.
        Returns a list of card dicts, each with at least 'name', 'type_line', 'oracle_text'.
        """
        if not colors:
            return []
        color_chars = "".join(colors).upper()
        # Scryfall: is:commander or (type:legendary type:creature) with color identity
        query = f"id<={color_chars} (is:commander OR (t:legendary t:creature))"
        try:
            encoded = urllib.parse.quote(query)
            url = f"{ScryfallService.BASE_URL}/cards/search?q={encoded}&order=edhrec&dir=desc"
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])[:15]  # top 15 by EDHREC rank
        except requests.exceptions.RequestException as e:
            print(f"Error fetching commanders from Scryfall: {e}")
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
