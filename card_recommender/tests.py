"""Tests for the card_recommender app."""

from unittest.mock import MagicMock, patch
from django.test import TestCase

from card_recommender.services.ai_recommender import DeckRecommendationAgent


class DeckRecommendationAgentTests(TestCase):
    """Test cases for the DeckRecommendationAgent."""

    @patch.dict("os.environ", {}, clear=True)
    def test_init_without_api_key_sets_client_to_none(self):
        """Test that agent initializes with no client when API key is missing."""
        agent = DeckRecommendationAgent()
        self.assertIsNone(agent._client)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key-123"})
    @patch("card_recommender.services.ai_recommender.genai.Client")
    def test_init_with_gemini_api_key(self, mock_client):
        """Test that agent initializes with GEMINI_API_KEY."""
        DeckRecommendationAgent()
        mock_client.assert_called_once_with(api_key="test-key-123")

    @patch.dict("os.environ", {"GOOGLE_API_KEY": "google-key-456"}, clear=True)
    @patch("card_recommender.services.ai_recommender.genai.Client")
    def test_init_with_google_api_key_fallback(self, mock_client):
        """Test that agent falls back to GOOGLE_API_KEY."""
        DeckRecommendationAgent()
        mock_client.assert_called_once_with(api_key="google-key-456")

    @patch.dict("os.environ", {"GEMINI_API_KEY": "gemini-key", "GOOGLE_API_KEY": "google-key"})
    @patch("card_recommender.services.ai_recommender.genai.Client")
    def test_init_prefers_gemini_over_google_key(self, mock_client):
        """Test that GEMINI_API_KEY takes precedence over GOOGLE_API_KEY."""
        DeckRecommendationAgent()
        mock_client.assert_called_once_with(api_key="gemini-key")

    def test_get_response_text_from_candidates(self):
        """Test extracting text from response candidates."""
        agent = DeckRecommendationAgent()
        agent._client = None  # Don't need real client for this test

        # Mock response with candidates
        mock_part = MagicMock()
        mock_part.text = "Test response text"

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        result = agent._get_response_text(mock_response)
        self.assertEqual(result, "Test response text")

    def test_get_response_text_multiple_parts(self):
        """Test extracting and joining text from multiple parts."""
        agent = DeckRecommendationAgent()
        agent._client = None

        mock_part1 = MagicMock()
        mock_part1.text = "Part 1"
        mock_part2 = MagicMock()
        mock_part2.text = " Part 2"

        mock_content = MagicMock()
        mock_content.parts = [mock_part1, mock_part2]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        result = agent._get_response_text(mock_response)
        self.assertEqual(result, "Part 1 Part 2")

    def test_get_response_text_fallback_to_text_attribute(self):
        """Test fallback to response.text when candidates not available."""
        agent = DeckRecommendationAgent()
        agent._client = None

        mock_response = MagicMock()
        mock_response.candidates = []
        mock_response.text = "Fallback text"

        result = agent._get_response_text(mock_response)
        self.assertEqual(result, "Fallback text")

    def test_get_response_text_returns_none_when_no_text(self):
        """Test returns None when no text is available."""
        agent = DeckRecommendationAgent()
        agent._client = None

        mock_response = MagicMock()
        mock_response.candidates = []
        mock_response.text = None

        result = agent._get_response_text(mock_response)
        self.assertIsNone(result)

    def test_parse_recommendations_valid_json(self):
        """Test parsing valid JSON recommendations."""
        agent = DeckRecommendationAgent()
        agent._client = None

        text = '{"cards": ["Lightning Bolt", "Counterspell", "Dark Ritual"]}'
        result = agent._parse_recommendations(text)

        self.assertEqual(len(result), 3)
        self.assertIn("Lightning Bolt", result)
        self.assertIn("Counterspell", result)

    def test_parse_recommendations_json_with_markdown(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        agent = DeckRecommendationAgent()
        agent._client = None

        text = '```json\n{"cards": ["Card A", "Card B", "Card C"]}\n```'
        result = agent._parse_recommendations(text)

        self.assertEqual(len(result), 3)
        self.assertIn("Card A", result)

    def test_parse_recommendations_generic_markdown(self):
        """Test parsing JSON in generic markdown blocks."""
        agent = DeckRecommendationAgent()
        agent._client = None

        text = '```\n{"cards": ["Card X", "Card Y"]}\n```'
        result = agent._parse_recommendations(text)

        self.assertEqual(len(result), 2)

    def test_parse_recommendations_json_with_extra_text(self):
        """Test parsing JSON with surrounding text."""
        agent = DeckRecommendationAgent()
        agent._client = None

        text = 'Here are some recommendations: {"cards": ["Bolt", "Shock"]} - Hope this helps!'
        result = agent._parse_recommendations(text)

        self.assertEqual(len(result), 2)
        self.assertIn("Bolt", result)

    def test_parse_recommendations_empty_string(self):
        """Test parsing empty string returns empty list."""
        agent = DeckRecommendationAgent()
        agent._client = None

        result = agent._parse_recommendations("")
        self.assertEqual(result, [])

    def test_parse_recommendations_none_returns_empty_list(self):
        """Test parsing None returns empty list."""
        agent = DeckRecommendationAgent()
        agent._client = None

        result = agent._parse_recommendations(None)
        self.assertEqual(result, [])

    def test_parse_recommendations_invalid_json(self):
        """Test parsing invalid JSON returns empty list."""
        agent = DeckRecommendationAgent()
        agent._client = None

        text = '{"cards": [invalid json}'
        result = agent._parse_recommendations(text)

        self.assertEqual(result, [])

    def test_parse_recommendations_no_cards_key(self):
        """Test parsing JSON without 'cards' key returns empty list."""
        agent = DeckRecommendationAgent()
        agent._client = None

        text = '{"recommendations": ["A", "B"]}'
        result = agent._parse_recommendations(text)

        self.assertEqual(result, [])

    def test_parse_recommendations_no_json_braces(self):
        """Test parsing text with no JSON braces returns empty list."""
        agent = DeckRecommendationAgent()
        agent._client = None

        text = "Just some plain text with no JSON"
        result = agent._parse_recommendations(text)

        self.assertEqual(result, [])

    def test_get_deck_improvement_recommendations_no_client(self):
        """Test that recommendations return empty list when client is None."""
        agent = DeckRecommendationAgent()
        agent._client = None

        result = agent.get_deck_improvement_recommendations(["Lightning Bolt", "Mountain"])
        self.assertEqual(result, [])

    def test_get_deck_improvement_recommendations_empty_deck(self):
        """Test that empty deck returns empty recommendations."""
        agent = DeckRecommendationAgent()
        agent._client = MagicMock()

        result = agent.get_deck_improvement_recommendations([])
        self.assertEqual(result, [])

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("card_recommender.services.ai_recommender.genai.Client")
    def test_get_deck_improvement_recommendations_success(self, mock_client_class):
        """Test successful recommendation generation."""
        # Setup mock client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Setup mock response
        mock_part = MagicMock()
        mock_part.text = '{"cards": ["Shock", "Lava Spike", "Rift Bolt"]}'

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_client.models.generate_content.return_value = mock_response

        agent = DeckRecommendationAgent()
        result = agent.get_deck_improvement_recommendations(["Lightning Bolt"] * 4 + ["Mountain"] * 20)

        self.assertEqual(len(result), 3)
        self.assertIn("Shock", result)
        self.assertIn("Lava Spike", result)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("card_recommender.services.ai_recommender.genai.Client")
    def test_get_deck_improvement_recommendations_with_format(self, mock_client_class):
        """Test that format is included in prompt."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_part = MagicMock()
        mock_part.text = '{"cards": ["A", "B", "C"]}'

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_client.models.generate_content.return_value = mock_response

        agent = DeckRecommendationAgent()
        agent.get_deck_improvement_recommendations(["Forest", "Llanowar Elves"], format_name="modern")

        # Check that format was used
        call_args = mock_client.models.generate_content.call_args
        self.assertIn("modern", call_args[1]["contents"])

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("card_recommender.services.ai_recommender.genai.Client")
    def test_get_deck_improvement_recommendations_truncates_long_deck(self, mock_client_class):
        """Test that long deck lists are truncated in prompt."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.candidates = []
        mock_response.text = None

        mock_client.models.generate_content.return_value = mock_response

        agent = DeckRecommendationAgent()
        # Create deck with more than 20 cards
        long_deck = [f"Card {i}" for i in range(30)]
        agent.get_deck_improvement_recommendations(long_deck)

        # Check that prompt was truncated
        call_args = mock_client.models.generate_content.call_args
        prompt = call_args[1]["contents"]
        self.assertIn("(10 more)", prompt)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("card_recommender.services.ai_recommender.genai.Client")
    def test_get_deck_improvement_recommendations_handles_exception(self, mock_client_class):
        """Test that exceptions during generation are handled gracefully."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_client.models.generate_content.side_effect = Exception("API Error")

        agent = DeckRecommendationAgent()
        result = agent.get_deck_improvement_recommendations(["Mountain", "Lightning Bolt"])

        self.assertEqual(result, [])

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("card_recommender.services.ai_recommender.genai.Client")
    def test_get_deck_improvement_recommendations_no_response_text(self, mock_client_class):
        """Test handling when response has no extractable text."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.candidates = []
        mock_response.text = None

        mock_client.models.generate_content.return_value = mock_response

        agent = DeckRecommendationAgent()
        result = agent.get_deck_improvement_recommendations(["Forest"])

        self.assertEqual(result, [])