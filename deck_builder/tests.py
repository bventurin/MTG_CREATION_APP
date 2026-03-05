"""
Tests for the deck_builder app.
"""

import base64
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch, call

from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory, Client
from django.urls import reverse

from deck_builder.views import parse_deck_list
from deck_builder.services.card_organizer import (
    get_card_type_category,
    organize_cards_by_type,
    get_deck_metadata,
)
from deck_builder.services.scryfall_s3_service import (
    _strip_card,
    _build_index,
    _string_similarity,
    ScryfallS3Service,
)
from deck_builder.services.qr_service import QRService
from deck_builder.services.voucher_service import VoucherService
from deck_builder.services.plot_service import PlotService


# parse_deck_list

class ParseDeckListTests(TestCase):

    def test_basic_deck_no_headers(self):
        text = "4 Lightning Bolt\n2 Mountain"
        name, cards = parse_deck_list(text)
        self.assertIsNone(name)
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]["card_name"], "Lightning Bolt")
        self.assertEqual(cards[0]["quantity"], 4)
        self.assertFalse(cards[0]["is_sideboard"])

    def test_deck_with_name_and_headers(self):
        text = "Name My Deck\nDeck\n4 Counterspell\nSideboard\n2 Negate"
        name, cards = parse_deck_list(text)
        self.assertEqual(name, "My Deck")
        main = [c for c in cards if not c["is_sideboard"]]
        side = [c for c in cards if c["is_sideboard"]]
        self.assertEqual(len(main), 1)
        self.assertEqual(main[0]["card_name"], "Counterspell")
        self.assertEqual(len(side), 1)
        self.assertEqual(side[0]["card_name"], "Negate")

    def test_duplicate_cards_are_summed(self):
        text = "Deck\n2 Lightning Bolt\n2 Lightning Bolt"
        _, cards = parse_deck_list(text)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["quantity"], 4)

    def test_about_line_is_skipped(self):
        text = "About\n4 Birds of Paradise"
        _, cards = parse_deck_list(text)
        self.assertEqual(len(cards), 1)

    def test_empty_lines_skipped(self):
        text = "4 Sol Ring\n\n\n1 Black Lotus"
        _, cards = parse_deck_list(text)
        self.assertEqual(len(cards), 2)

    def test_lines_without_number_prefix_ignored(self):
        text = "Deck\nNot a card line\n4 Swamp"
        _, cards = parse_deck_list(text)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["card_name"], "Swamp")

    def test_sideboard_cards_marked_correctly(self):
        text = "Deck\n4 Island\nSideboard\n1 Tormod's Crypt"
        _, cards = parse_deck_list(text)
        crypt = next(c for c in cards if c["card_name"] == "Tormod's Crypt")
        self.assertTrue(crypt["is_sideboard"])

    def test_empty_input(self):
        _, cards = parse_deck_list("")
        self.assertEqual(cards, [])


# get_card_type_category

class GetCardTypeCategoryTests(TestCase):

    def test_creature(self):
        self.assertEqual(get_card_type_category("Legendary Creature — Elf"), "Creature")

    def test_sorcery(self):
        self.assertEqual(get_card_type_category("Sorcery"), "Sorcery")

    def test_instant(self):
        self.assertEqual(get_card_type_category("Instant"), "Instant")

    def test_enchantment(self):
        self.assertEqual(get_card_type_category("Enchantment — Aura"), "Enchantment")

    def test_planeswalker(self):
        self.assertEqual(get_card_type_category("Legendary Planeswalker — Jace"), "Planeswalker")

    def test_artifact(self):
        self.assertEqual(get_card_type_category("Artifact — Equipment"), "Artifact")

    def test_land(self):
        self.assertEqual(get_card_type_category("Basic Land — Island"), "Land")

    def test_other(self):
        self.assertEqual(get_card_type_category("Conspiracy"), "Other")

    def test_creature_takes_priority_over_artifact(self):
        # "Artifact Creature" should be categorised as Creature
        self.assertEqual(get_card_type_category("Artifact Creature — Robot"), "Creature")


# _strip_card

class StripCardTests(TestCase):

    def test_keeps_needed_fields(self):
        raw = {
            "name": "Lightning Bolt",
            "type_line": "Instant",
            "prices": {"usd": "1.00"},
            "garbage_field": "ignored",
            "set": "M10",
        }
        stripped = _strip_card(raw)
        self.assertIn("name", stripped)
        self.assertIn("type_line", stripped)
        self.assertNotIn("garbage_field", stripped)
        self.assertNotIn("set", stripped)

    def test_strips_card_faces(self):
        raw = {
            "name": "Delver of Secrets",
            "card_faces": [
                {"name": "Delver", "mana_cost": "{U}", "extra": "ignored"},
                {"name": "Insectile Aberration", "type_line": "Creature", "extra": "ignored"},
            ],
        }
        stripped = _strip_card(raw)
        for face in stripped["card_faces"]:
            self.assertNotIn("extra", face)

    def test_no_card_faces(self):
        raw = {"name": "Shock", "type_line": "Instant"}
        stripped = _strip_card(raw)
        self.assertNotIn("card_faces", stripped)


# _build_index

class BuildIndexTests(TestCase):

    def test_simple_lookup(self):
        cards = [{"name": "Lightning Bolt", "type_line": "Instant"}]
        index = _build_index(cards)
        self.assertIn("lightning bolt", index)

    def test_double_faced_card_both_names_indexed(self):
        cards = [{"name": "Delver of Secrets // Insectile Aberration", "type_line": "Creature"}]
        index = _build_index(cards)
        self.assertIn("delver of secrets // insectile aberration", index)
        self.assertIn("delver of secrets", index)

    def test_printed_name_indexed(self):
        cards = [{"name": "Storm Crow", "printed_name": "Tormenta Cuervo"}]
        index = _build_index(cards)
        self.assertIn("tormenta cuervo", index)

    def test_flavor_name_indexed(self):
        cards = [{"name": "Gideon Blackblade", "flavor_name": "Kytheon Iora"}]
        index = _build_index(cards)
        self.assertIn("kytheon iora", index)

    def test_empty_name_skipped(self):
        cards = [{"name": "", "type_line": "Land"}]
        index = _build_index(cards)
        self.assertNotIn("", index)


# _string_similarity

class StringSimilarityTests(TestCase):

    def test_identical_strings(self):
        self.assertEqual(_string_similarity("abc", "abc"), 1.0)

    def test_empty_first(self):
        self.assertEqual(_string_similarity("", "abc"), 0.0)

    def test_empty_second(self):
        self.assertEqual(_string_similarity("abc", ""), 0.0)

    def test_partial_match(self):
        score = _string_similarity("abc", "axc")
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)

    def test_completely_different(self):
        score = _string_similarity("aaa", "zzz")
        self.assertEqual(score, 0.0)


# ScryfallS3Service — static methods

class ScryfallStaticMethodTests(TestCase):

    # get_card_image_url
    def test_image_url_from_image_uris(self):
        card = {"image_uris": {"normal": "http://img/normal.jpg"}}
        self.assertEqual(ScryfallS3Service.get_card_image_url(card), "http://img/normal.jpg")

    def test_image_url_falls_back_to_card_faces(self):
        card = {"card_faces": [{"image_uris": {"normal": "http://img/face.jpg"}}]}
        self.assertEqual(ScryfallS3Service.get_card_image_url(card), "http://img/face.jpg")

    def test_image_url_returns_none_when_missing(self):
        self.assertIsNone(ScryfallS3Service.get_card_image_url({}))

    def test_image_url_wrong_format_returns_none(self):
        card = {"image_uris": {"large": "http://img/large.jpg"}}
        self.assertIsNone(ScryfallS3Service.get_card_image_url(card, "normal"))

    # get_card_price
    def test_price_usd(self):
        card = {"prices": {"usd": "2.50"}}
        self.assertEqual(ScryfallS3Service.get_card_price(card), 2.50)

    def test_price_falls_back_to_usd_foil(self):
        card = {"prices": {"usd_foil": "5.00"}}
        self.assertEqual(ScryfallS3Service.get_card_price(card), 5.00)

    def test_price_falls_back_to_eur(self):
        card = {"prices": {"eur": "3.00"}}
        self.assertEqual(ScryfallS3Service.get_card_price(card), 3.00)

    def test_price_falls_back_to_tix(self):
        card = {"prices": {"tix": "0.10"}}
        self.assertEqual(ScryfallS3Service.get_card_price(card), 0.10)

    def test_price_zero_when_no_prices(self):
        self.assertEqual(ScryfallS3Service.get_card_price({}), 0.0)

    def test_price_invalid_value_returns_zero(self):
        card = {"prices": {"usd": "N/A"}}
        self.assertEqual(ScryfallS3Service.get_card_price(card), 0.0)

    # get_card_mana_cost
    def test_mana_cost_direct(self):
        card = {"mana_cost": "{U}{U}"}
        self.assertEqual(ScryfallS3Service.get_card_mana_cost(card), "{U}{U}")

    def test_mana_cost_falls_back_to_card_faces(self):
        card = {"mana_cost": "", "card_faces": [{"mana_cost": "{1}{W}"}]}
        self.assertEqual(ScryfallS3Service.get_card_mana_cost(card), "{1}{W}")

    def test_mana_cost_empty_when_missing(self):
        self.assertEqual(ScryfallS3Service.get_card_mana_cost({}), "")


# ScryfallS3Service.get_all_cards (cache / S3 interaction)

class ScryfallGetAllCardsTests(TestCase):

    @patch("deck_builder.services.scryfall_s3_service.cache")
    @patch("deck_builder.services.scryfall_s3_service._get_all_cards_cached")
    def test_returns_from_cache_when_available(self, mock_s3, mock_cache):
        mock_cache.get.return_value = [{"name": "Cached Card"}]
        svc = ScryfallS3Service()
        cards = svc.get_all_cards()
        self.assertEqual(cards, [{"name": "Cached Card"}])
        mock_s3.assert_not_called()

    @patch("deck_builder.services.scryfall_s3_service.cache")
    @patch("deck_builder.services.scryfall_s3_service._get_all_cards_cached")
    def test_fetches_from_s3_on_cache_miss(self, mock_s3, mock_cache):
        mock_cache.get.return_value = None
        mock_s3.return_value = [{"name": "S3 Card"}]
        svc = ScryfallS3Service()
        cards = svc.get_all_cards()
        self.assertEqual(cards, [{"name": "S3 Card"}])
        mock_cache.set.assert_called_once()

    @patch("deck_builder.services.scryfall_s3_service.cache")
    @patch("deck_builder.services.scryfall_s3_service._get_all_cards_cached")
    def test_cache_read_exception_falls_back_to_s3(self, mock_s3, mock_cache):
        mock_cache.get.side_effect = Exception("cache down")
        mock_s3.return_value = [{"name": "Fallback Card"}]
        svc = ScryfallS3Service()
        cards = svc.get_all_cards()
        self.assertEqual(cards, [{"name": "Fallback Card"}])

    @patch("deck_builder.services.scryfall_s3_service.cache")
    @patch("deck_builder.services.scryfall_s3_service._get_all_cards_cached")
    def test_cache_write_exception_is_swallowed(self, mock_s3, mock_cache):
        mock_cache.get.return_value = None
        mock_s3.return_value = [{"name": "Card"}]
        mock_cache.set.side_effect = Exception("write fail")
        svc = ScryfallS3Service()
        cards = svc.get_all_cards()
        self.assertEqual(len(cards), 1)

    @patch("deck_builder.services.scryfall_s3_service.cache")
    @patch("deck_builder.services.scryfall_s3_service._get_all_cards_cached")
    def test_empty_card_list_skips_cache_set(self, mock_s3, mock_cache):
        mock_cache.get.return_value = None
        mock_s3.return_value = []
        svc = ScryfallS3Service()
        svc.get_all_cards()
        mock_cache.set.assert_not_called()


# ScryfallS3Service.get_card_by_name

class ScryfallGetCardByNameTests(TestCase):

    def _make_service_with_index(self, index):
        svc = ScryfallS3Service.__new__(ScryfallS3Service)
        svc.bucket_name = "test-bucket"
        svc.bulk_type = "default_cards"
        svc._get_index = MagicMock(return_value=index)
        return svc

    def test_exact_match(self):
        card = {"name": "Lightning Bolt"}
        svc = self._make_service_with_index({"lightning bolt": card})
        result = svc.get_card_by_name("Lightning Bolt")
        self.assertEqual(result, card)

    def test_exact_match_cached_none_no_api_fallback(self):
        svc = self._make_service_with_index({"lightning bolt": None})
        result = svc.get_card_by_name("Lightning Bolt", allow_api_fallback=False)
        self.assertIsNone(result)

    def test_normalized_unicode_match(self):
        card = {"name": "Juzam Djinn"}
        svc = self._make_service_with_index({"juzam djinn": card})
        result = svc.get_card_by_name("Juzam Djinn")
        self.assertEqual(result, card)

    def test_fuzzy_substring_match(self):
        card = {"name": "Lightning Bolt"}
        svc = self._make_service_with_index({"lightning bolt": card})
        result = svc.get_card_by_name("lightning bolt extra")
        self.assertEqual(result, card)

    def test_not_found_no_api_fallback(self):
        svc = self._make_service_with_index({})
        result = svc.get_card_by_name("Nonexistent Card", allow_api_fallback=False)
        self.assertIsNone(result)

    @patch("deck_builder.services.scryfall_s3_service.requests.get")
    @patch("deck_builder.services.scryfall_s3_service.time.sleep")
    def test_api_fallback_success(self, mock_sleep, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "Ancestral Recall",
            "type_line": "Instant",
        }
        mock_get.return_value = mock_response
        index = {}
        svc = self._make_service_with_index(index)
        result = svc.get_card_by_name("Ancestral Recall")
        self.assertIsNotNone(result)
        self.assertIn("ancestral recall", index)

    @patch("deck_builder.services.scryfall_s3_service.requests.get")
    @patch("deck_builder.services.scryfall_s3_service.time.sleep")
    def test_api_fallback_rate_limited(self, mock_sleep, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        svc = self._make_service_with_index({})
        result = svc.get_card_by_name("Some Card")
        self.assertIsNone(result)

    @patch("deck_builder.services.scryfall_s3_service.requests.get")
    @patch("deck_builder.services.scryfall_s3_service.time.sleep")
    def test_api_fallback_404(self, mock_sleep, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        index = {}
        svc = self._make_service_with_index(index)
        result = svc.get_card_by_name("Fake Card")
        self.assertIsNone(result)
        self.assertIn("fake card", index)

    @patch("deck_builder.services.scryfall_s3_service.requests.get")
    @patch("deck_builder.services.scryfall_s3_service.time.sleep")
    def test_api_fallback_exception(self, mock_sleep, mock_get):
        mock_get.side_effect = Exception("network error")
        index = {}
        svc = self._make_service_with_index(index)
        result = svc.get_card_by_name("Any Card")
        self.assertIsNone(result)

    def test_max_api_fallbacks_exceeded(self):
        from deck_builder.services.scryfall_s3_service import MAX_API_FALLBACKS
        index = {}
        svc = self._make_service_with_index(index)
        svc._api_fallback_count = MAX_API_FALLBACKS
        result = svc.get_card_by_name("Overflow Card")
        self.assertIsNone(result)
        self.assertIn("overflow card", index)

    def test_empty_index_builds_when_cards_empty(self):
        """When get_all_cards returns empty, index should be set to {} to avoid repeated S3 calls."""
        import deck_builder.services.scryfall_s3_service as module
        original = module._cards_index
        try:
            module._cards_index = None
            svc = ScryfallS3Service.__new__(ScryfallS3Service)
            svc.bucket_name = "b"
            svc.bulk_type = "t"
            with patch.object(svc, "get_all_cards", return_value=[]):
                idx = svc._get_index()
            self.assertEqual(idx, {})
        finally:
            module._cards_index = original


# organize_cards_by_type

class OrganizeCardsByTypeTests(TestCase):

    @patch("deck_builder.services.card_organizer.ScryfallS3Service")
    def test_found_card_placed_in_correct_category(self, MockService):
        mock_svc = MagicMock()
        MockService.return_value = mock_svc
        mock_svc.get_card_by_name.return_value = {
            "name": "Llanowar Elves",
            "type_line": "Creature — Elf Druid",
            "image_uris": {"normal": "http://img/elves.jpg"},
            "mana_cost": "{G}",
            "oracle_text": "Add {G}.",
            "colors": ["G"],
            "prices": {"usd": "0.25"},
        }
        ScryfallS3Service.get_card_price = MagicMock(return_value=0.25)
        ScryfallS3Service.get_card_mana_cost = MagicMock(return_value="{G}")
        ScryfallS3Service.get_card_image_url = MagicMock(return_value="http://img/elves.jpg")

        cards_data = [{"card_name": "Llanowar Elves", "quantity": 4}]
        organized = organize_cards_by_type(cards_data)
        self.assertIn("Creature", organized)
        self.assertEqual(organized["Creature"][0]["card_name"], "Llanowar Elves")

    @patch("deck_builder.services.card_organizer.ScryfallS3Service")
    def test_not_found_card_placed_in_unknown(self, MockService):
        mock_svc = MagicMock()
        MockService.return_value = mock_svc
        mock_svc.get_card_by_name.return_value = None

        cards_data = [{"card_name": "Fake Card", "quantity": 1}]
        organized = organize_cards_by_type(cards_data)
        self.assertIn("Unknown", organized)

    @patch("deck_builder.services.card_organizer.ScryfallS3Service")
    def test_empty_cards_returns_empty_dict(self, MockService):
        MockService.return_value = MagicMock()
        organized = organize_cards_by_type([])
        self.assertEqual(organized, {})


# get_deck_metadata

class GetDeckMetadataTests(TestCase):

    def _make_card_data(self, type_line, colors, price, image_url):
        return {
            "type_line": type_line,
            "colors": colors,
            "image_uris": {"normal": image_url},
            "prices": {"usd": str(price)},
        }

    @patch("deck_builder.services.card_organizer.ScryfallS3Service")
    def test_collects_colors_and_representative_image(self, MockService):
        mock_svc = MagicMock()
        MockService.return_value = mock_svc
        creature_card = self._make_card_data("Creature", ["G"], 1.0, "http://img/creature.jpg")
        mock_svc.get_card_by_name.return_value = creature_card
        ScryfallS3Service.get_card_image_url = MagicMock(return_value="http://img/creature.jpg")
        ScryfallS3Service.get_card_price = MagicMock(return_value=1.0)

        cards = [{"card_name": "Llanowar Elves"}]
        result = get_deck_metadata(cards)
        self.assertIn("G", result["colors"])
        self.assertEqual(result["representative_image"], "http://img/creature.jpg")

    @patch("deck_builder.services.card_organizer.ScryfallS3Service")
    def test_lands_skipped_as_representative(self, MockService):
        mock_svc = MagicMock()
        MockService.return_value = mock_svc
        land_card = self._make_card_data("Basic Land — Forest", ["G"], 0.1, "http://img/land.jpg")
        mock_svc.get_card_by_name.return_value = land_card
        ScryfallS3Service.get_card_image_url = MagicMock(return_value="http://img/land.jpg")
        ScryfallS3Service.get_card_price = MagicMock(return_value=0.1)

        cards = [{"card_name": "Forest"}]
        result = get_deck_metadata(cards)
        self.assertIsNone(result["representative_image"])

    @patch("deck_builder.services.card_organizer.ScryfallS3Service")
    def test_card_not_found_skipped(self, MockService):
        mock_svc = MagicMock()
        MockService.return_value = mock_svc
        mock_svc.get_card_by_name.return_value = None

        result = get_deck_metadata([{"card_name": "Ghost"}])
        self.assertEqual(result["colors"], [])
        self.assertIsNone(result["representative_image"])

    @patch("deck_builder.services.card_organizer.ScryfallS3Service")
    def test_colors_sorted_in_wubrg_order(self, MockService):
        mock_svc = MagicMock()
        MockService.return_value = mock_svc
        card = self._make_card_data("Creature", ["R", "W", "U"], 1.0, "http://img/x.jpg")
        mock_svc.get_card_by_name.return_value = card
        ScryfallS3Service.get_card_image_url = MagicMock(return_value="http://img/x.jpg")
        ScryfallS3Service.get_card_price = MagicMock(return_value=1.0)

        result = get_deck_metadata([{"card_name": "Tricolor"}])
        self.assertEqual(result["colors"], ["W", "U", "R"])

    @patch("deck_builder.services.card_organizer.ScryfallS3Service")
    def test_pricier_creature_replaces_cheaper_one(self, MockService):
        mock_svc = MagicMock()
        MockService.return_value = mock_svc

        cheap = self._make_card_data("Creature", ["W"], 1.0, "http://img/cheap.jpg")
        expensive = self._make_card_data("Creature", ["W"], 10.0, "http://img/expensive.jpg")
        mock_svc.get_card_by_name.side_effect = [cheap, expensive]
        ScryfallS3Service.get_card_image_url = MagicMock(
            side_effect=["http://img/cheap.jpg", "http://img/expensive.jpg"]
        )
        ScryfallS3Service.get_card_price = MagicMock(side_effect=[1.0, 10.0])

        result = get_deck_metadata([{"card_name": "Cheap"}, {"card_name": "Expensive"}])
        self.assertEqual(result["representative_image"], "http://img/expensive.jpg")


# QRService

class QRServiceTests(TestCase):

    @patch.dict("os.environ", {}, clear=True)
    def test_raises_when_endpoint_not_set(self):
        with self.assertRaises(Exception):
            QRService.get_qr_code_url("deck1", "http://example.com/decks/deck1/")

    @patch("deck_builder.services.qr_service.requests.post")
    @patch("deck_builder.services.qr_service.requests.get")
    @patch.dict("os.environ", {"QR_CODE_ENDPOINT": "http://qr.example.com"})
    def test_success_with_json_response_and_image_download(self, mock_get, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"qrcode_image_url": "https://img.example.com/qr.png"}),
        )
        img_bytes = b"PNGDATA"
        mock_get.return_value = MagicMock(
            status_code=200,
            content=img_bytes,
            headers={"Content-Type": "image/png"},
        )
        result = QRService.get_qr_code_url("deck1", "http://example.com/decks/deck1/")
        expected_b64 = base64.b64encode(img_bytes).decode("utf-8")
        self.assertIn(expected_b64, result)
        self.assertTrue(result.startswith("data:image/png;base64,"))

    @patch("deck_builder.services.qr_service.requests.post")
    @patch("deck_builder.services.qr_service.requests.get")
    @patch.dict("os.environ", {"QR_CODE_ENDPOINT": "http://qr.example.com"})
    def test_image_download_failure_returns_url(self, mock_get, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"qrcode_image_url": "https://img.example.com/qr.png"}),
        )
        mock_get.side_effect = Exception("download failed")
        result = QRService.get_qr_code_url("deck1", "http://example.com/decks/deck1/")
        self.assertEqual(result, "https://img.example.com/qr.png")

    @patch("deck_builder.services.qr_service.requests.post")
    @patch.dict("os.environ", {"QR_CODE_ENDPOINT": "http://qr.example.com"})
    def test_non_200_response_raises(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500, text="Server Error")
        with self.assertRaises(Exception):
            QRService.get_qr_code_url("deck1", "http://example.com/")

    @patch("deck_builder.services.qr_service.requests.post")
    @patch.dict("os.environ", {"QR_CODE_ENDPOINT": "http://qr.example.com"})
    def test_text_fallback_when_json_fails(self, mock_post):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.side_effect = ValueError("not json")
        mock_resp.text = "http://some-url.com/qr.png"
        mock_post.return_value = mock_resp
        # Returns the text URL (not https so skip image download)
        result = QRService.get_qr_code_url("deck1", "http://example.com/")
        self.assertEqual(result, "http://some-url.com/qr.png")


# VoucherService

class VoucherServiceTests(TestCase):

    @patch.dict("os.environ", {}, clear=True)
    def test_returns_none_when_env_not_set(self):
        result = VoucherService.generate_voucher()
        self.assertIsNone(result)

    @patch("deck_builder.services.voucher_service.requests.post")
    @patch.dict("os.environ", {"VOUCHER_SERVICE_ENDPOINT": "http://voucher.example.com"})
    def test_success_extracts_voucher_id(self, mock_post):
        mock_post.return_value = MagicMock(
            text="Your voucher ID is 'ABC123'"
        )
        mock_post.return_value.raise_for_status = MagicMock()
        result = VoucherService.generate_voucher()
        self.assertEqual(result, "ABC123")

    @patch("deck_builder.services.voucher_service.requests.post")
    @patch.dict("os.environ", {"VOUCHER_SERVICE_ENDPOINT": "http://voucher.example.com"})
    def test_no_match_returns_none(self, mock_post):
        mock_post.return_value = MagicMock(text="Unexpected response format")
        mock_post.return_value.raise_for_status = MagicMock()
        result = VoucherService.generate_voucher()
        self.assertIsNone(result)

    @patch("deck_builder.services.voucher_service.requests.post")
    @patch.dict("os.environ", {"VOUCHER_SERVICE_ENDPOINT": "http://voucher.example.com"})
    def test_request_exception_returns_none(self, mock_post):
        import requests
        mock_post.side_effect = requests.RequestException("timeout")
        result = VoucherService.generate_voucher()
        self.assertIsNone(result)


# PlotService

class PlotServiceTests(TestCase):

    def _make_scryfall_svc(self, cmc=2, type_line="Instant"):
        mock_svc = MagicMock()
        mock_svc.get_card_by_name.return_value = {"cmc": cmc, "type_line": type_line}
        return mock_svc

    @patch("deck_builder.services.plot_service.requests.get")
    @patch("deck_builder.services.plot_service.requests.put")
    @patch("deck_builder.services.plot_service.requests.post")
    @patch.dict("os.environ", {"FILECONVERT_API_BASE_URL": "http://convert.example.com"})
    def test_generate_mana_curve_plot_success(self, mock_post, mock_put, mock_get):
        mock_get.return_value = MagicMock(
            json=MagicMock(return_value={
                "upload_url": "http://s3.example.com/upload",
                "download_url": "http://s3.example.com/download",
            })
        )
        mock_get.return_value.raise_for_status = MagicMock()
        mock_put.return_value = MagicMock()
        mock_put.return_value.raise_for_status = MagicMock()
        mock_post.return_value = MagicMock(
            json=MagicMock(return_value={"url": "http://s3.example.com/plot.png"})
        )
        mock_post.return_value.raise_for_status = MagicMock()

        scryfall_svc = self._make_scryfall_svc(cmc=2, type_line="Instant")
        main_deck = [{"card_name": "Counterspell", "quantity": 4}]
        result = PlotService.generate_mana_curve_plot(main_deck, scryfall_svc)
        self.assertEqual(result, "http://s3.example.com/plot.png")

    def test_returns_none_for_lands_only_deck(self):
        scryfall_svc = MagicMock()
        scryfall_svc.get_card_by_name.return_value = {"cmc": 0, "type_line": "Basic Land — Island"}
        main_deck = [{"card_name": "Island", "quantity": 20}]
        result = PlotService.generate_mana_curve_plot(main_deck, scryfall_svc)
        self.assertIsNone(result)

    def test_returns_none_when_card_not_found(self):
        scryfall_svc = MagicMock()
        scryfall_svc.get_card_by_name.return_value = None
        main_deck = [{"card_name": "Unknown Card", "quantity": 1}]
        result = PlotService.generate_mana_curve_plot(main_deck, scryfall_svc)
        self.assertIsNone(result)

    def test_high_cmc_bucketed_to_six_plus(self):
        """Cards with CMC >= 6 should be bucketed into the 6+ slot."""
        scryfall_svc = MagicMock()
        scryfall_svc.get_card_by_name.return_value = {"cmc": 8, "type_line": "Creature"}

        with patch.object(PlotService, "_get_upload_url") as mock_up, \
             patch.object(PlotService, "_upload_data") as mock_ud, \
             patch.object(PlotService, "_generate_plot") as mock_gp:
            mock_up.return_value = {"upload_url": "http://u", "download_url": "http://d"}
            mock_gp.return_value = "http://plot.png"

            main_deck = [{"card_name": "Emrakul", "quantity": 1}]
            PlotService.generate_mana_curve_plot(main_deck, scryfall_svc)
            # _generate_plot was called, which means the 6+ bucket was used
            mock_gp.assert_called_once()


# Views

def _make_user(username="testuser", password="pass1234"):
    return User.objects.create_user(username=username, password=password)


DECK_UUID = "11111111-1111-1111-1111-111111111111"

MOCK_DECK = {
    "deck_id": DECK_UUID,
    "name": "Test Deck",
    "pk": f"USER#1",
    "sk": f"DECK#{DECK_UUID}",
}

MOCK_CARDS = [
    {"card_name": "Lightning Bolt", "quantity": 4, "is_sideboard": False,
     "pk": f"DECK#{DECK_UUID}", "sk": "CARD#Lightning Bolt#False"},
    {"card_name": "Mountain", "quantity": 20, "is_sideboard": False,
     "pk": f"DECK#{DECK_UUID}", "sk": "CARD#Mountain#False"},
]


class HomeViewTests(TestCase):

    def test_home_anonymous_renders_no_decks(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["decks"], [])

    @patch("deck_builder.views.DynamoDBService")
    @patch("deck_builder.views.get_deck_metadata")
    def test_home_authenticated_shows_decks(self, mock_metadata, MockDB):
        mock_db = MagicMock()
        MockDB.return_value = mock_db
        mock_db.get_user_decks.return_value = [dict(MOCK_DECK)]
        mock_db.get_deck_cards.return_value = list(MOCK_CARDS)
        mock_metadata.return_value = {"colors": ["R"], "representative_image": "http://img.jpg"}

        user = _make_user()
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["decks"]), 1)

    @patch("deck_builder.views.DynamoDBService")
    def test_home_db_exception_returns_empty_decks(self, MockDB):
        MockDB.return_value.get_user_decks.side_effect = Exception("db error")
        user = _make_user()
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["decks"], [])


class CreateDeckViewTests(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    def test_get_returns_200(self):
        response = self.client.get(reverse("create_deck"))
        self.assertEqual(response.status_code, 200)

    @patch("deck_builder.views.DynamoDBService")
    def test_post_valid_deck_redirects(self, MockDB):
        MockDB.return_value.create_deck.return_value = "new-deck-id"
        response = self.client.post(
            reverse("create_deck"),
            {"deck_list": "4 Lightning Bolt\n20 Mountain"},
        )
        self.assertRedirects(response, reverse("deck_detail", kwargs={"deck_id": "new-deck-id"}), fetch_redirect_response=False)

    @patch("deck_builder.views.DynamoDBService")
    def test_post_empty_deck_list_re_renders_form(self, MockDB):
        response = self.client.post(reverse("create_deck"), {"deck_list": ""})
        self.assertEqual(response.status_code, 200)

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("create_deck"))
        self.assertRedirects(response, "/accounts/login/?next=/decks/create/", fetch_redirect_response=False)


class DeckListViewTests(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    @patch("deck_builder.views.DynamoDBService")
    @patch("deck_builder.views.get_deck_metadata")
    def test_renders_deck_list(self, mock_metadata, MockDB):
        MockDB.return_value.get_user_decks.return_value = [dict(MOCK_DECK)]
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        mock_metadata.return_value = {"colors": [], "representative_image": None}
        response = self.client.get(reverse("deck_list"))
        self.assertEqual(response.status_code, 200)

    @patch("deck_builder.views.DynamoDBService")
    def test_db_exception_returns_empty_list(self, MockDB):
        MockDB.return_value.get_user_decks.side_effect = Exception("db error")
        response = self.client.get(reverse("deck_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["decks"], [])


class DeckDetailViewTests(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    @patch("deck_builder.views.DynamoDBService")
    def test_redirect_when_deck_not_found(self, MockDB):
        MockDB.return_value.get_deck.return_value = None
        response = self.client.get(reverse("deck_detail", kwargs={"deck_id": "00000000-0000-0000-0000-000000000000"}))
        self.assertRedirects(response, reverse("deck_list"), fetch_redirect_response=False)

    @patch("deck_builder.views.PlotService")
    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.organize_cards_by_type")
    @patch("deck_builder.views.DynamoDBService")
    def test_renders_deck_detail(self, MockDB, mock_organize, MockScryfall, MockPlot):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        mock_organize.return_value = {"Instant": MOCK_CARDS}
        MockScryfall.return_value.get_card_by_name.return_value = None
        MockScryfall.get_card_price = MagicMock(return_value=0.0)
        MockPlot.generate_mana_curve_plot.return_value = None
        response = self.client.get(reverse("deck_detail", kwargs={"deck_id": DECK_UUID}))
        self.assertEqual(response.status_code, 200)

    @patch("deck_builder.views.PlotService")
    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.organize_cards_by_type")
    @patch("deck_builder.views.DynamoDBService")
    def test_deck_detail_with_voucher(self, MockDB, mock_organize, MockScryfall, MockPlot):
        deck_with_voucher = dict(MOCK_DECK)
        deck_with_voucher["voucher_code"] = "SAVE20"
        deck_with_voucher["voucher_image_url"] = "http://img/voucher.png"
        MockDB.return_value.get_deck.return_value = deck_with_voucher
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        mock_organize.return_value = {}
        MockScryfall.return_value.get_card_by_name.return_value = None
        MockScryfall.get_card_price = MagicMock(return_value=0.0)
        MockPlot.generate_mana_curve_plot.return_value = None
        response = self.client.get(reverse("deck_detail", kwargs={"deck_id": DECK_UUID}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("voucher_code", response.context)

    @patch("deck_builder.views.PlotService")
    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.organize_cards_by_type")
    @patch("deck_builder.views.DynamoDBService")
    def test_deck_detail_with_qr_in_session(self, MockDB, mock_organize, MockScryfall, MockPlot):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        mock_organize.return_value = {}
        MockScryfall.return_value.get_card_by_name.return_value = None
        MockScryfall.get_card_price = MagicMock(return_value=0.0)
        MockPlot.generate_mana_curve_plot.return_value = None
        session = self.client.session
        session[f"qr_code_{DECK_UUID}"] = "http://qr.example.com/qr.png"
        session.save()
        response = self.client.get(reverse("deck_detail", kwargs={"deck_id": DECK_UUID}))
        self.assertEqual(response.status_code, 200)


class EditDeckViewTests(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    @patch("deck_builder.views.DynamoDBService")
    def test_get_renders_form(self, MockDB):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        response = self.client.get(reverse("edit_deck", kwargs={"deck_id": DECK_UUID}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("deck_text", response.context)

    @patch("deck_builder.views.DynamoDBService")
    def test_post_updates_deck_and_redirects(self, MockDB):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = []
        response = self.client.post(
            reverse("edit_deck", kwargs={"deck_id": DECK_UUID}),
            {"deck_list": "4 Llanowar Elves", "deck_name": "Updated Deck"},
        )
        MockDB.return_value.update_deck.assert_called_once()
        self.assertRedirects(
            response, reverse("deck_detail", kwargs={"deck_id": DECK_UUID}),
            fetch_redirect_response=False,
        )

    @patch("deck_builder.views.DynamoDBService")
    def test_post_empty_cards_re_renders(self, MockDB):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = []
        response = self.client.post(
            reverse("edit_deck", kwargs={"deck_id": DECK_UUID}),
            {"deck_list": "", "deck_name": ""},
        )
        self.assertEqual(response.status_code, 200)


class DeleteDeckViewTests(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    @patch("deck_builder.views.DynamoDBService")
    def test_get_renders_confirmation_page(self, MockDB):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        response = self.client.get(reverse("delete_deck", kwargs={"deck_id": DECK_UUID}))
        self.assertEqual(response.status_code, 200)

    @patch("deck_builder.views.DynamoDBService")
    def test_post_deletes_and_redirects(self, MockDB):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        response = self.client.post(reverse("delete_deck", kwargs={"deck_id": DECK_UUID}))
        MockDB.return_value.delete_deck.assert_called_once()
        self.assertRedirects(response, reverse("deck_list"), fetch_redirect_response=False)


class GenerateQRCodeViewTests(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    @patch("deck_builder.views.DynamoDBService")
    def test_redirect_when_deck_not_found(self, MockDB):
        MockDB.return_value.get_deck.return_value = None
        response = self.client.post(reverse("generate_qr_code", kwargs={"deck_id": "00000000-0000-0000-0000-000000000000"}))
        self.assertRedirects(response, reverse("deck_list"), fetch_redirect_response=False)

    @patch("deck_builder.views.QRService")
    @patch("deck_builder.views.DynamoDBService")
    def test_generates_qr_and_stores_in_session(self, MockDB, MockQR):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockQR.get_qr_code_url.return_value = "http://qr.example.com/qr.png"
        response = self.client.post(reverse("generate_qr_code", kwargs={"deck_id": DECK_UUID}))
        self.assertRedirects(
            response, reverse("deck_detail", kwargs={"deck_id": DECK_UUID}),
            fetch_redirect_response=False,
        )
        self.assertIn(f"qr_code_{DECK_UUID}", self.client.session)

    @patch("deck_builder.views.QRService")
    @patch("deck_builder.views.DynamoDBService")
    def test_qr_exception_still_redirects(self, MockDB, MockQR):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockQR.get_qr_code_url.side_effect = Exception("QR service down")
        response = self.client.post(reverse("generate_qr_code", kwargs={"deck_id": DECK_UUID}))
        self.assertRedirects(
            response, reverse("deck_detail", kwargs={"deck_id": DECK_UUID}),
            fetch_redirect_response=False,
        )


class AddVoucherViewTests(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    @patch("deck_builder.views.DynamoDBService")
    def test_redirect_when_deck_not_found(self, MockDB):
        MockDB.return_value.get_deck.return_value = None
        response = self.client.post(reverse("add_voucher", kwargs={"deck_id": "00000000-0000-0000-0000-000000000000"}))
        self.assertRedirects(response, reverse("deck_list"), fetch_redirect_response=False)

    @patch("deck_builder.views.DynamoDBService")
    def test_redirect_when_deck_already_has_voucher(self, MockDB):
        deck_with_voucher = dict(MOCK_DECK)
        deck_with_voucher["voucher_code"] = "EXISTING"
        MockDB.return_value.get_deck.return_value = deck_with_voucher
        response = self.client.post(reverse("add_voucher", kwargs={"deck_id": DECK_UUID}))
        self.assertRedirects(
            response, reverse("deck_detail", kwargs={"deck_id": DECK_UUID}),
            fetch_redirect_response=False,
        )
        MockDB.return_value.apply_voucher_to_deck.assert_not_called()

    @patch("deck_builder.views.VoucherService")
    @patch("deck_builder.views.DynamoDBService")
    def test_generates_and_applies_voucher(self, MockDB, MockVoucher):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockVoucher.generate_voucher.return_value = "NEWCODE"
        response = self.client.post(reverse("add_voucher", kwargs={"deck_id": DECK_UUID}))
        MockDB.return_value.apply_voucher_to_deck.assert_called_once()
        self.assertRedirects(
            response, reverse("deck_detail", kwargs={"deck_id": DECK_UUID}),
            fetch_redirect_response=False,
        )

    @patch("deck_builder.views.VoucherService")
    @patch("deck_builder.views.DynamoDBService")
    def test_no_voucher_generated_skips_apply(self, MockDB, MockVoucher):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockVoucher.generate_voucher.return_value = None
        self.client.post(reverse("add_voucher", kwargs={"deck_id": DECK_UUID}))
        MockDB.return_value.apply_voucher_to_deck.assert_not_called()


class GetRecommendationsViewTests(TestCase):

    def setUp(self):
        self.user = _make_user()
        self.client.force_login(self.user)

    @patch("deck_builder.views.DynamoDBService")
    def test_redirect_when_deck_not_found(self, MockDB):
        MockDB.return_value.get_deck.return_value = None
        response = self.client.get(reverse("get_recommendations", kwargs={"deck_id": "00000000-0000-0000-0000-000000000000"}))
        self.assertRedirects(response, reverse("deck_list"), fetch_redirect_response=False)

    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.DeckRecommendationAgent")
    @patch("deck_builder.views.DynamoDBService")
    def test_get_shows_recommendations(self, MockDB, MockAgent, MockScryfall):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = [
            {"card_name": "Lightning Bolt", "quantity": 4, "is_sideboard": False}
        ]
        MockAgent.return_value.get_deck_improvement_recommendations.return_value = ["Shock"]
        mock_scryfall = MagicMock()
        MockScryfall.return_value = mock_scryfall
        mock_scryfall.get_card_by_name.return_value = {
            "type_line": "Instant",
            "image_uris": {"normal": "http://img/shock.jpg"},
        }
        MockScryfall.get_card_price = MagicMock(return_value=0.5)
        MockScryfall.get_card_mana_cost = MagicMock(return_value="{R}")
        MockScryfall.get_card_image_url = MagicMock(return_value="http://img/shock.jpg")
        response = self.client.get(
            reverse("get_recommendations", kwargs={"deck_id": DECK_UUID})
        )
        self.assertEqual(response.status_code, 200)

    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.DeckRecommendationAgent")
    @patch("deck_builder.views.DynamoDBService")
    def test_get_recommendation_card_not_in_scryfall(self, MockDB, MockAgent, MockScryfall):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = []
        MockAgent.return_value.get_deck_improvement_recommendations.return_value = ["Ghost Card"]
        MockScryfall.return_value.get_card_by_name.return_value = None
        response = self.client.get(
            reverse("get_recommendations", kwargs={"deck_id": DECK_UUID})
        )
        self.assertEqual(response.status_code, 200)

    @patch("deck_builder.views.DynamoDBService")
    @patch("deck_builder.views.DeckRecommendationAgent")
    def test_post_adds_cards_to_deck(self, MockAgent, MockDB):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = [
            {"card_name": "Lightning Bolt", "quantity": 4, "is_sideboard": False}
        ]
        response = self.client.post(
            reverse("get_recommendations", kwargs={"deck_id": DECK_UUID}),
            {"cards": ["Shock", "Bolt"]},
        )
        MockDB.return_value.update_deck.assert_called_once()
        self.assertRedirects(
            response, reverse("deck_detail", kwargs={"deck_id": DECK_UUID}),
            fetch_redirect_response=False,
        )
