import os
import json
import re
from google import genai
from google.genai import types
from .scryfall import ScryfallService


# Map WUBRG to full names for prompts
COLOR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}


class DeckRecommendationAgent:
    """
    Agent that recommends decks based on the format (e.g. Commander) and colors
    the user picks. Uses Gemini to suggest deck themes, commanders, and key cards.
    """

    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self._client = genai.Client(api_key=api_key) if api_key else None
        self._model = "gemini-2.0-flash"

    def get_deck_recommendations(self, format_name, colors):
        """
        Recommend decks based on format and selected colors.

        :param format_name: str, e.g. 'commander', 'standard', 'modern'
        :param colors: list of str, e.g. ['W', 'U', 'B', 'R', 'G']
        :return: list of dicts with keys: title, description, commander (optional), key_cards, theme
        """
        if not self._client:
            return self._fallback_recommendations(format_name, colors)

        format_name = (format_name or "commander").strip().lower()
        colors = [c.upper() for c in colors] if colors else []
        color_str = ", ".join(COLOR_NAMES.get(c, c) for c in colors) or "any"

        # For Commander, fetch real commander options from Scryfall to ground the agent
        commander_context = ""
        if format_name == "commander" and colors:
            commanders = ScryfallService.get_commanders_for_colors(colors)
            if commanders:
                names = [c.get("name") for c in commanders if c.get("name")]
                commander_context = (
                    "\n\nPopular commanders in these colors (use these when relevant): "
                    + ", ".join(names[:12])
                )

        system_instruction = (
            "You are an expert Magic: The Gathering deck advisor. "
            "Given a format and color choice, recommend 2–3 distinct deck ideas. "
            "For Commander, always suggest a specific commander and a short theme (e.g. tokens, spellslinger, reanimator). "
            "For other formats, suggest an archetype and a few key card names. "
            "Reply with valid JSON only, no markdown or extra text. Use this exact structure:\n"
            '{"recommendations": [{"title": "...", "theme": "...", "description": "...", "commander": "..." or null, "key_cards": ["...", "..."]}]}'
        )

        user_prompt = (
            f"Format: {format_name}. Colors: {color_str}.{commander_context}\n"
            "Give 2–3 deck recommendations as JSON (recommendations array with title, theme, description, commander if Commander, key_cards list)."
        )

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.4,
                    max_output_tokens=1024,
                ),
            )
            text = (response.text or "").strip()
            return self._parse_recommendations(text, format_name)
        except Exception as e:
            print(f"DeckRecommendationAgent Gemini error: {e}")
            return self._fallback_recommendations(format_name, colors)

    def _parse_recommendations(self, text, format_name):
        """Parse JSON from model output; fall back to empty or simple list on error."""
        # Remove markdown code fences if present
        if "```" in text:
            text = re.sub(r"```(?:json)?\s*", "", text)
            text = re.sub(r"```\s*$", "", text)
        text = text.strip()
        try:
            data = json.loads(text)
            recs = data.get("recommendations", data if isinstance(data, list) else [])
            if isinstance(recs, list):
                return [self._normalize_deck_rec(r, format_name) for r in recs]
        except json.JSONDecodeError:
            pass
        return self._fallback_recommendations(format_name, [])

    def _normalize_deck_rec(self, r, format_name):
        """Ensure each recommendation has title, theme, description, commander, key_cards."""
        if not isinstance(r, dict):
            r = {}
        return {
            "title": r.get("title") or "Deck idea",
            "theme": r.get("theme") or "",
            "description": r.get("description") or "",
            "commander": r.get("commander") if format_name == "commander" else None,
            "key_cards": isinstance(r.get("key_cards"), list)
            and r["key_cards"]
            or [],
        }

    def _fallback_recommendations(self, format_name, colors):
        """When API is missing or fails, return Scryfall-based suggestions."""
        format_name = (format_name or "commander").strip().lower()
        recs = []

        if format_name == "commander" and colors:
            commanders = ScryfallService.get_commanders_for_colors(colors)
            for c in commanders[:3]:
                name = c.get("name")
                if name:
                    recs.append({
                        "title": name,
                        "theme": "Commander",
                        "description": (c.get("oracle_text") or "")[:200],
                        "commander": name,
                        "key_cards": [],
                    })

        if not recs:
            color_str = ", ".join(COLOR_NAMES.get(c.upper(), c) for c in colors) or "multi"
            recs.append({
                "title": f"{color_str} {format_name} deck",
                "theme": "General",
                "description": f"Build a {format_name} deck with {color_str} colors. Add GEMINI_API_KEY to .env for AI suggestions.",
                "commander": None,
                "key_cards": [],
            })

        return recs


# Convenience: keep a single agent instance and a function compatible with existing views
_agent = None


def get_deck_recommendations(format_name, colors):
    """Get deck recommendations from the agent (format + colors)."""
    global _agent
    if _agent is None:
        _agent = DeckRecommendationAgent()
    return _agent.get_deck_recommendations(format_name, colors)
