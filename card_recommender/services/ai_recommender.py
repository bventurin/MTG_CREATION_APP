from .scryfall import ScryfallService
import random

class CardRecommender:
    """
    A simple rule-based recommender that suggests cards based on format and colors.
    """
    
    @staticmethod
    def get_recommendations(format_name, colors):
        """
        Get card recommendations based on format and selected colors.
        
        :param format_name: str, e.g., 'standard', 'modern', 'commander'
        :param colors: list of str, e.g., ['W', 'U', 'B', 'R', 'G']
        :return: list of card data objects
        """
        if not format_name:
            format_name = 'standard'
            
        # Construct a Scryfall query
        # c:RUB means colors are Red, Blue, Black (or subset depending on operator)
        # c=RUB means exactly these colors
        # id:RUB means color identity (better for commander)
        
        color_query = ""
        if colors:
            color_chars = "".join(colors)
            if format_name.lower() == 'commander':
                color_query = f"id<={color_chars}" # Allow subset or equal identity
            else:
                color_query = f"c:{color_chars}" # Cards that share these colors
        
        # Add basic filters to get "good" cards (e.g., popular or high casting cost as a proxy for 'impact')
        # We can sort by EDHREC rank for Commander, or just popularity in general.
        # sort:edhrec is good for popularity.
        
        query = f"f:{format_name} {color_query} year>=2020"
        
        # Use Scryfall service to get cards
        # We append a sort order to get 'relevant' cards
        query += " sort:edhrec" 
        
        cards = ScryfallService.search_cards(query)
        
        # Return a subset, maybe random 5 or top 5
        return cards[:5] if cards else []
