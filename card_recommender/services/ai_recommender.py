import os
import json
from google import genai
from google.genai import types


COLOR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}


class DeckRecommendationAgent:
    """
    Agent that recommends decks based on the format (e.g. Commander) and colors
    the user picks.
    """

    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            self._client = None
            return

        self._client = genai.Client(api_key=api_key)
        self._cache = {}

    def get_deck_recommendations(self, format_name, colors):
        """
        Recommend cards based on format and selected colors.
        Returns a list of card names.
        """
        if not self._client:
            print("DeckRecommendationAgent: No API client (check GEMINI_API_KEY).")
            return []

        format_name = format_name or "standard"
        colors = colors or []
        color_str = ", ".join(COLOR_NAMES.get(c, c) for c in colors) or "any"

        # Check cache to avoid repeated API calls
        cache_key = (format_name, tuple(sorted(colors)))
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt = (
            f"Recommend 3 MTG cards for {format_name} format, {color_str} colors. "
            "Current meta, affordable, legal cards only. "
            "Return ONLY raw JSON, no markdown formatting, no conversational text. "
            "JSON format: {\"cards\": [\"Card Name\", ...]}"
        )

        generation_config = types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema={
                "type": "object",
                "properties": {
                    "cards": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["cards"]
            }
        )

        try:
            response = self._client.models.generate_content(
                model="gemini-2.5-flash", 
                contents=prompt,
                config=generation_config
            )
            
            # Get text from response
            response_text = None
            if hasattr(response, 'text') and response.text:
                response_text = response.text
            elif hasattr(response, 'candidates') and response.candidates:
                response_text = response.candidates[0].content.parts[0].text
            
            if not response_text:
                print("DeckRecommendationAgent: Empty response from API")
                return []
            
            cards = self._parse_recommendations(response_text)
            if cards:
                self._cache[cache_key] = cards
            return cards
        except Exception as e:
            print(f"DeckRecommendationAgent: AI generation failed. Error: {e}")
            return []

    def _parse_recommendations(self, text):
        """
        Parse JSON from model output, which may be wrapped in markdown or have a preamble.
        """
        try:
            # Strip markdown code blocks if present
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            # Find the start of the JSON content
            start_index = text.find('{')
            if start_index == -1:
                # If no '{' found, there's no JSON object.
                print(f"DeckRecommendationAgent: No JSON object found. Text: {text[:100]}...")
                return []
            
            # Find the matching '}' for the found '{'
            end_index = text.rfind('}')
            if end_index == -1:
                print(f"DeckRecommendationAgent: No closing '}}' for JSON object. Text: {text[:100]}...")
                return []
            
            json_text = text[start_index : end_index + 1]
            data = json.loads(json_text)
            return data.get("cards", [])
        except json.JSONDecodeError as e:
            print(f"DeckRecommendationAgent: JSON parse error. Text: {json_text[:100]}...")
            return []

# keep a single agent instance and a function compatible with existing views
_agent = None


def get_deck_recommendations(format_name, colors):
    """Get deck recommendations from the agent (format + colors)."""
    global _agent
    if _agent is None:
        _agent = DeckRecommendationAgent()
    return _agent.get_deck_recommendations(format_name, colors)
