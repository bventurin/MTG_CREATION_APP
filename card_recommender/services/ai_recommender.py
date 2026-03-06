import os
import json
from google import genai
from google.genai import types


class DeckRecommendationAgent:
    # Agent that analyzes decks and recommends cards for improvement
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            self._client = None
            return

        self._client = genai.Client(api_key=api_key)

    def _extract_text_from_candidates(self, response) -> str:
        """Join text parts from the first Gemini candidate."""
        candidates = getattr(response, "candidates", None)
        if not candidates:
            return ""
        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", []) if content else []
        return "".join(p.text for p in parts if getattr(p, "text", None))

    def _get_response_text(self, response):
        """Extract JSON from Gemini API response."""
        text = self._extract_text_from_candidates(response)
        if text:
            return text
        # Fallback to response.text
        return getattr(response, "text", None) or None

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Remove markdown code fences from model output."""
        if "```json" in text:
            return text.split("```json")[1].split("```")[0].strip()
        if "```" in text:
            return text.split("```")[1].split("```")[0].strip()
        return text

    def _parse_recommendations(self, text):
        """Parse JSON from model output, which may be wrapped in markdown."""
        if not text:
            return []

        try:
            text = self._strip_markdown(text)
            start_index = text.find("{")
            end_index = text.rfind("}")
            if start_index == -1 or end_index == -1:
                return []

            data = json.loads(text[start_index : end_index + 1])
            return data.get("cards", [])
        except json.JSONDecodeError:
            return []
        except Exception as e:
            print(f"DeckRecommendationAgent: Parse error: {e}")
            return []

    def get_deck_improvement_recommendations(self, deck_cards, format_name="standard"):
        # Analyze an existing deck and recommend 3 cards that would improve it
        if not self._client:
            print("DeckRecommendationAgent: No API client (check GEMINI_API_KEY).")
            return []

        if not deck_cards:
            return []

        # Create a concise deck summary
        deck_list = ", ".join(deck_cards[:20])
        if len(deck_cards) > 20:
            deck_list += f"... ({len(deck_cards) - 20} more)"

        prompt = (
            f"Analyze this {format_name} MTG deck: {deck_list}. "
            "Recommend 3 cards to improve synergy, fill gaps, or strengthen strategy. "
            "Cards must be legal in the format and complement the deck's theme. "
            "Return ONLY raw JSON, no markdown, no explanation. "
            'JSON format: {"cards": ["Card Name", "Card Name", "Card Name"]}'
        )

        generation_config = types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=1024,
        )

        try:
            response = self._client.models.generate_content(
                model="gemini-2.5-flash", contents=prompt, config=generation_config
            )

            response_text = self._get_response_text(response)
            if not response_text:
                return []

            return self._parse_recommendations(response_text)
        except Exception as e:
            print(f"DeckRecommendationAgent: AI generation failed. Error: {e}")
            return []
