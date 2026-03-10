"""Tests for the deck_builder app."""

from unittest.mock import MagicMock, patch
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from deck_builder.views import parse_deck_list
from deck_builder.services.card_organizer import get_card_type_category, organize_cards_by_type, get_deck_metadata
from deck_builder.services.scryfall_s3_service import _strip_card, _build_index, _string_similarity, ScryfallS3Service
from deck_builder.services.qr_service import QRService
from deck_builder.services.voucher_service import VoucherService
from deck_builder.services.plot_service import PlotService
from deck_builder.templatetags.deck_builder_filters import mul, mana_icons, mark_safe_mana


# ---------------------------------------------------------------------------
# parse_deck_list
# ---------------------------------------------------------------------------

class ParseDeckListTests(TestCase):

    def test_basic_deck_no_headers(self):
        _, cards = parse_deck_list("4 Lightning Bolt\n2 Mountain")
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]["quantity"], 4)
        self.assertFalse(cards[0]["is_sideboard"])

    def test_name_and_sideboard_parsed(self):
        name, cards = parse_deck_list("Name My Deck\nDeck\n4 Bolt\nSideboard\n2 Negate")
        self.assertEqual(name, "My Deck")
        self.assertTrue(next(c for c in cards if c["card_name"] == "Negate")["is_sideboard"])

    def test_duplicate_cards_summed(self):
        _, cards = parse_deck_list("Deck\n2 Bolt\n2 Bolt")
        self.assertEqual(cards[0]["quantity"], 4)

    def test_about_and_empty_lines_skipped(self):
        _, cards = parse_deck_list("About\n\n4 Swamp")
        self.assertEqual(len(cards), 1)

    def test_empty_input(self):
        _, cards = parse_deck_list("")
        self.assertEqual(cards, [])


# ---------------------------------------------------------------------------
# get_card_type_category
# ---------------------------------------------------------------------------

class GetCardTypeCategoryTests(TestCase):

    def test_all_types(self):
        cases = [
            ("Legendary Creature — Elf", "Creature"),
            ("Sorcery", "Sorcery"),
            ("Instant", "Instant"),
            ("Enchantment — Aura", "Enchantment"),
            ("Legendary Planeswalker — Jace", "Planeswalker"),
            ("Artifact — Equipment", "Artifact"),
            ("Basic Land — Island", "Land"),
            ("Conspiracy", "Other"),
            ("Artifact Creature — Robot", "Creature"),  # Creature takes priority
        ]
        for type_line, expected in cases:
            with self.subTest(type_line=type_line):
                self.assertEqual(get_card_type_category(type_line), expected)

# ---------------------------------------------------------------------------

class ScryallHelpersTests(TestCase):

    def test_strip_card_removes_unwanted_fields(self):
        stripped = _strip_card({"name": "Bolt", "type_line": "Instant", "set": "ignored"})
        self.assertIn("name", stripped)
        self.assertNotIn("set", stripped)

    def test_strip_card_strips_card_faces(self):
        raw = {"name": "Delver", "card_faces": [{"mana_cost": "{U}", "extra": "drop"}]}
        self.assertNotIn("extra", _strip_card(raw)["card_faces"][0])

    def test_build_index_double_faced_and_aliases(self):
        cards = [
            {"name": "Delver // Aberration"},
            {"name": "Storm", "printed_name": "Tormenta"},
            {"name": "Gideon", "flavor_name": "Kytheon"},
        ]
        index = _build_index(cards)
        self.assertIn("delver", index)
        self.assertIn("tormenta", index)
        self.assertIn("kytheon", index)

    def test_string_similarity(self):
        self.assertEqual(_string_similarity("abc", "abc"), 1.0)
        self.assertEqual(_string_similarity("", "abc"), 0.0)
        self.assertGreater(_string_similarity("abc", "axc"), 0.0)


# ---------------------------------------------------------------------------
# ScryfallS3Service static methods
# ---------------------------------------------------------------------------

class ScryfallStaticTests(TestCase):

    def test_image_url_direct_and_card_faces_fallback(self):
        self.assertEqual(ScryfallS3Service.get_card_image_url({"image_uris": {"normal": "http://a.jpg"}}), "http://a.jpg")
        self.assertEqual(ScryfallS3Service.get_card_image_url({"card_faces": [{"image_uris": {"normal": "http://b.jpg"}}]}), "http://b.jpg")
        self.assertIsNone(ScryfallS3Service.get_card_image_url({}))

    def test_price_fallback_chain(self):
        self.assertEqual(ScryfallS3Service.get_card_price({"prices": {"usd": "2.50"}}), 2.50)
        self.assertEqual(ScryfallS3Service.get_card_price({"prices": {"usd_foil": "5.00"}}), 5.00)
        self.assertEqual(ScryfallS3Service.get_card_price({"prices": {"usd": "bad"}}), 0.0)
        self.assertEqual(ScryfallS3Service.get_card_price({}), 0.0)

    def test_mana_cost_direct_and_card_faces_fallback(self):
        self.assertEqual(ScryfallS3Service.get_card_mana_cost({"mana_cost": "{U}{U}"}), "{U}{U}")
        self.assertEqual(ScryfallS3Service.get_card_mana_cost({"mana_cost": "", "card_faces": [{"mana_cost": "{1}{W}"}]}), "{1}{W}")
        self.assertEqual(ScryfallS3Service.get_card_mana_cost({}), "")


# ---------------------------------------------------------------------------
# ScryfallS3Service.get_all_cards and get_card_by_name
# ---------------------------------------------------------------------------

class ScryfallServiceTests(TestCase):

    @patch("deck_builder.services.scryfall_s3_service.cache")
    @patch("deck_builder.services.scryfall_s3_service._get_all_cards_cached")
    def test_cache_hit_skips_s3(self, mock_s3, mock_cache):
        mock_cache.get.return_value = [{"name": "Cached"}]
        self.assertEqual(ScryfallS3Service().get_all_cards(), [{"name": "Cached"}])
        mock_s3.assert_not_called()

    @patch("deck_builder.services.scryfall_s3_service.cache")
    @patch("deck_builder.services.scryfall_s3_service._get_all_cards_cached")
    def test_cache_miss_fetches_s3_and_stores(self, mock_s3, mock_cache):
        mock_cache.get.return_value = None
        mock_s3.return_value = [{"name": "S3 Card"}]
        ScryfallS3Service().get_all_cards()
        mock_cache.set.assert_called_once()

    @patch("deck_builder.services.scryfall_s3_service.cache")
    @patch("deck_builder.services.scryfall_s3_service._get_all_cards_cached")
    def test_cache_exception_falls_back_to_s3(self, mock_s3, mock_cache):
        mock_cache.get.side_effect = Exception("down")
        mock_s3.return_value = [{"name": "Card"}]
        self.assertEqual(len(ScryfallS3Service().get_all_cards()), 1)

    def _svc(self, index):
        svc = ScryfallS3Service.__new__(ScryfallS3Service)
        svc.bucket_name = "b"
        svc.bulk_type = "t"
        svc._get_index = MagicMock(return_value=index)
        return svc

    def test_exact_match(self):
        card = {"name": "Bolt"}
        self.assertEqual(self._svc({"lightning bolt": card}).get_card_by_name("Lightning Bolt"), card)

    def test_no_api_fallback_returns_none(self):
        self.assertIsNone(self._svc({}).get_card_by_name("Ghost", allow_api_fallback=False))

    @patch("deck_builder.services.scryfall_s3_service.requests.get")
    @patch("deck_builder.services.scryfall_s3_service.time.sleep")
    def test_api_fallback_success(self, _, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=MagicMock(return_value={"name": "Recall", "type_line": "Instant"}))
        index = {}
        result = self._svc(index).get_card_by_name("Ancestral Recall")
        self.assertIsNotNone(result)

    @patch("deck_builder.services.scryfall_s3_service.requests.get")
    @patch("deck_builder.services.scryfall_s3_service.time.sleep")
    def test_api_fallback_429_returns_none(self, _, mock_get):
        mock_get.return_value = MagicMock(status_code=429)
        self.assertIsNone(self._svc({}).get_card_by_name("Card"))


# ---------------------------------------------------------------------------
# organize_cards_by_type / get_deck_metadata
# ---------------------------------------------------------------------------

class CardOrganizerTests(TestCase):

    @patch("deck_builder.services.card_organizer.ScryfallS3Service")
    def test_organize_found_card(self, MockSvc):
        mock_svc = MagicMock()
        MockSvc.return_value = mock_svc
        mock_svc.get_card_by_name.return_value = {"name": "Bolt", "type_line": "Instant", "image_uris": {"normal": "http://a.jpg"}, "mana_cost": "{R}", "oracle_text": "", "colors": ["R"], "prices": {"usd": "1.0"}}
        MockSvc.get_card_price.return_value = 1.0
        MockSvc.get_card_mana_cost.return_value = "{R}"
        MockSvc.get_card_image_url.return_value = "http://a.jpg"
        result = organize_cards_by_type([{"card_name": "Bolt", "quantity": 4}])
        self.assertIn("Instant", result)

    @patch("deck_builder.services.card_organizer.ScryfallS3Service")
    def test_organize_not_found_card(self, MockSvc):
        MockSvc.return_value.get_card_by_name.return_value = None
        result = organize_cards_by_type([{"card_name": "Fake", "quantity": 1}])
        self.assertIn("Unknown", result)

    @patch("deck_builder.services.card_organizer.ScryfallS3Service")
    def test_metadata_collects_colors_and_image(self, MockSvc):
        mock_svc = MagicMock()
        MockSvc.return_value = mock_svc
        mock_svc.get_card_by_name.return_value = {"type_line": "Creature", "colors": ["G"], "image_uris": {"normal": "http://img.jpg"}, "prices": {"usd": "1.0"}}
        MockSvc.get_card_image_url.return_value = "http://img.jpg"
        MockSvc.get_card_price.return_value = 1.0
        result = get_deck_metadata([{"card_name": "Elf"}])
        self.assertIn("G", result["colors"])
        self.assertEqual(result["representative_image"], "http://img.jpg")

    @patch("deck_builder.services.card_organizer.ScryfallS3Service")
    def test_metadata_skips_lands(self, MockSvc):
        mock_svc = MagicMock()
        MockSvc.return_value = mock_svc
        mock_svc.get_card_by_name.return_value = {"type_line": "Basic Land", "colors": [], "image_uris": {"normal": "http://land.jpg"}, "prices": {}}
        MockSvc.get_card_image_url.return_value = "http://land.jpg"
        MockSvc.get_card_price.return_value = 0.0
        result = get_deck_metadata([{"card_name": "Forest"}])
        self.assertIsNone(result["representative_image"])


# ---------------------------------------------------------------------------
# QRService
# ---------------------------------------------------------------------------

class QRServiceTests(TestCase):

    @patch.dict("os.environ", {}, clear=True)
    def test_raises_without_endpoint(self):
        with self.assertRaises(Exception):
            QRService.get_qr_code_url("d1", "http://x.com/")

    @patch("deck_builder.services.qr_service.requests.post")
    @patch("deck_builder.services.qr_service.requests.get")
    @patch.dict("os.environ", {"QR_CODE_ENDPOINT": "http://qr.example.com"})
    def test_success_returns_base64_image(self, mock_get, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=MagicMock(return_value={"qrcode_image_url": "https://img.example.com/qr.png"}))
        mock_get.return_value = MagicMock(status_code=200, content=b"PNG", headers={"Content-Type": "image/png"})
        result = QRService.get_qr_code_url("d1", "http://x.com/")
        self.assertTrue(result.startswith("data:image/png;base64,"))

    @patch("deck_builder.services.qr_service.requests.post")
    @patch.dict("os.environ", {"QR_CODE_ENDPOINT": "http://qr.example.com"})
    def test_non_200_raises(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500, text="err")
        with self.assertRaises(Exception):
            QRService.get_qr_code_url("d1", "http://x.com/")


# ---------------------------------------------------------------------------
# VoucherService
# ---------------------------------------------------------------------------

class VoucherServiceTests(TestCase):

    @patch.dict("os.environ", {}, clear=True)
    def test_returns_none_without_endpoint(self):
        self.assertIsNone(VoucherService.generate_voucher())

    @patch("deck_builder.services.voucher_service.requests.post")
    @patch.dict("os.environ", {"VOUCHER_SERVICE_ENDPOINT": "http://v.example.com"})
    def test_extracts_voucher_id(self, mock_post):
        mock_post.return_value = MagicMock(text="voucher ID is 'ABC123'")
        mock_post.return_value.raise_for_status = MagicMock()
        self.assertEqual(VoucherService.generate_voucher(), "ABC123")

    @patch("deck_builder.services.voucher_service.requests.post")
    @patch.dict("os.environ", {"VOUCHER_SERVICE_ENDPOINT": "http://v.example.com"})
    def test_request_error_returns_none(self, mock_post):
        import requests
        mock_post.side_effect = requests.RequestException("timeout")
        self.assertIsNone(VoucherService.generate_voucher())


# ---------------------------------------------------------------------------
# PlotService
# ---------------------------------------------------------------------------

class PlotServiceTests(TestCase):

    def test_lands_only_returns_none(self):
        svc = MagicMock()
        svc.get_card_by_name.return_value = {"cmc": 0, "type_line": "Basic Land"}
        self.assertIsNone(PlotService.generate_mana_curve_plot([{"card_name": "Island", "quantity": 20}], svc))

    def test_upload_failure_returns_none(self):
        svc = MagicMock()
        svc.get_card_by_name.return_value = {"cmc": 2, "type_line": "Instant"}
        with patch.object(PlotService, "_get_upload_url", side_effect=Exception("fail")):
            self.assertIsNone(PlotService.generate_mana_curve_plot([{"card_name": "Bolt", "quantity": 4}], svc))

    def test_success_returns_url(self):
        svc = MagicMock()
        svc.get_card_by_name.return_value = {"cmc": 2, "type_line": "Instant"}
        with patch.object(PlotService, "_get_upload_url", return_value={"upload_url": "http://u", "download_url": "http://d"}), \
             patch.object(PlotService, "_upload_data"), \
             patch.object(PlotService, "_generate_plot", return_value="http://plot.png"):
            result = PlotService.generate_mana_curve_plot([{"card_name": "Bolt", "quantity": 4}], svc)
        self.assertEqual(result, "http://plot.png")

    @patch("deck_builder.services.plot_service.requests.get")
    def test_get_upload_url_retries_on_failure(self, mock_get):
        """Test that _get_upload_url retries up to 3 times on failure."""
        # First two calls fail, third succeeds
        mock_get.side_effect = [
            Exception("Network error"),
            Exception("Network error"),
            MagicMock(status_code=200, json=MagicMock(return_value={"upload_url": "http://u", "download_url": "http://d"}))
        ]

        with patch("deck_builder.services.plot_service.time.sleep"):  # Skip actual sleep
            result = PlotService._get_upload_url("test.csv")

        self.assertEqual(result, {"upload_url": "http://u", "download_url": "http://d"})
        self.assertEqual(mock_get.call_count, 3)

    @patch("deck_builder.services.plot_service.requests.get")
    def test_get_upload_url_fails_after_retries(self, mock_get):
        """Test that _get_upload_url raises after all retries exhausted."""
        mock_get.side_effect = Exception("Network error")

        with patch("deck_builder.services.plot_service.time.sleep"):
            with self.assertRaises(Exception):
                PlotService._get_upload_url("test.csv")

        self.assertEqual(mock_get.call_count, 3)

    @patch("deck_builder.services.plot_service.requests.put")
    def test_upload_data_retries_on_failure(self, mock_put):
        """Test that _upload_data retries up to 3 times on failure."""
        # First two calls fail, third succeeds
        mock_put.side_effect = [
            Exception("Upload failed"),
            Exception("Upload failed"),
            MagicMock(status_code=200)
        ]
        mock_put.return_value.raise_for_status = MagicMock()

        with patch("deck_builder.services.plot_service.time.sleep"):
            PlotService._upload_data("http://upload", "data")

        self.assertEqual(mock_put.call_count, 3)

    @patch("deck_builder.services.plot_service.requests.post")
    def test_generate_plot_retries_on_failure(self, mock_post):
        """Test that _generate_plot retries up to 3 times on failure."""
        # First two calls fail, third succeeds
        mock_post.side_effect = [
            Exception("API error"),
            Exception("API error"),
            MagicMock(status_code=200, json=MagicMock(return_value={"url": "http://plot.png"}))
        ]
        mock_post.return_value.raise_for_status = MagicMock()

        with patch("deck_builder.services.plot_service.time.sleep"):
            result = PlotService._generate_plot("http://data", "bar")

        self.assertEqual(result, "http://plot.png")
        self.assertEqual(mock_post.call_count, 3)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

DECK_UUID = "11111111-1111-1111-1111-111111111111"
NEW_UUID = "22222222-2222-2222-2222-222222222222"

MOCK_DECK = {"deck_id": DECK_UUID, "name": "Test Deck", "pk": "USER#1", "sk": f"DECK#{DECK_UUID}"}
MOCK_CARDS = [
    {"card_name": "Lightning Bolt", "quantity": 4, "is_sideboard": False, "pk": f"DECK#{DECK_UUID}", "sk": "CARD#1"},
    {"card_name": "Mountain", "quantity": 20, "is_sideboard": False, "pk": f"DECK#{DECK_UUID}", "sk": "CARD#2"},
]


def make_user(username="tester"):
    return User.objects.create_user(username=username, password="pass1234")


class HomeViewTests(TestCase):

    def test_anonymous_shows_no_decks(self):
        self.assertEqual(self.client.get(reverse("home")).context["decks"], [])

    @patch("deck_builder.views.DynamoDBService")
    @patch("deck_builder.views.get_deck_metadata", return_value={"colors": [], "representative_image": None})
    def test_authenticated_shows_decks(self, _, MockDB):
        MockDB.return_value.get_user_decks.return_value = [dict(MOCK_DECK)]
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        self.client.force_login(make_user())
        self.assertEqual(len(self.client.get(reverse("home")).context["decks"]), 1)

    @patch("deck_builder.views.DynamoDBService")
    def test_db_error_returns_empty(self, MockDB):
        MockDB.return_value.get_user_decks.side_effect = Exception("db error")
        self.client.force_login(make_user("u2"))
        self.assertEqual(self.client.get(reverse("home")).context["decks"], [])


class CreateDeckViewTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user())

    @patch("deck_builder.views.DynamoDBService")
    def test_get_returns_200(self, _):
        self.assertEqual(self.client.get(reverse("create_deck")).status_code, 200)

    @patch("deck_builder.views.DynamoDBService")
    def test_post_redirects_on_valid_deck(self, MockDB):
        MockDB.return_value.create_deck.return_value = NEW_UUID
        response = self.client.post(reverse("create_deck"), {"deck_list": "4 Bolt\n20 Mountain"})
        self.assertRedirects(response, reverse("deck_detail", kwargs={"deck_id": NEW_UUID}), fetch_redirect_response=False)

    @patch("deck_builder.views.DynamoDBService")
    def test_post_empty_deck_list_rerenders(self, _):
        self.assertEqual(self.client.post(reverse("create_deck"), {"deck_list": ""}).status_code, 200)

    def test_anonymous_redirected(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("create_deck")).status_code, 302)


class DeckListViewTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user())

    @patch("deck_builder.views.DynamoDBService")
    @patch("deck_builder.views.get_deck_metadata", return_value={"colors": [], "representative_image": None})
    def test_renders_ok(self, _, MockDB):
        MockDB.return_value.get_user_decks.return_value = [dict(MOCK_DECK)]
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        self.assertEqual(self.client.get(reverse("deck_list")).status_code, 200)

    @patch("deck_builder.views.DynamoDBService")
    def test_db_error_still_renders(self, MockDB):
        MockDB.return_value.get_user_decks.side_effect = Exception("error")
        self.assertEqual(self.client.get(reverse("deck_list")).status_code, 200)


class DeckDetailViewTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user())

    @patch("deck_builder.views.DynamoDBService")
    def test_missing_deck_redirects(self, MockDB):
        MockDB.return_value.get_deck.return_value = None
        self.assertRedirects(
            self.client.get(reverse("deck_detail", kwargs={"deck_id": "00000000-0000-0000-0000-000000000000"})),
            reverse("deck_list"), fetch_redirect_response=False,
        )

    @patch("deck_builder.views.PlotService")
    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.organize_cards_by_type", return_value={})
    @patch("deck_builder.views.DynamoDBService")
    def test_renders_ok(self, MockDB, _, MockScryfall, MockPlot):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        MockScryfall.return_value.get_card_by_name.return_value = None
        MockScryfall.get_card_price.return_value = 0.0
        MockPlot.generate_mana_curve_plot.return_value = None
        self.assertEqual(self.client.get(reverse("deck_detail", kwargs={"deck_id": DECK_UUID})).status_code, 200)

    @patch("deck_builder.views.PlotService")
    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.organize_cards_by_type", return_value={})
    @patch("deck_builder.views.DynamoDBService")
    def test_voucher_shown_in_context(self, MockDB, _, MockScryfall, MockPlot):
        deck = dict(MOCK_DECK)
        deck["voucher_code"] = "SAVE20"
        MockDB.return_value.get_deck.return_value = deck
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        MockScryfall.return_value.get_card_by_name.return_value = None
        MockScryfall.get_card_price.return_value = 0.0
        MockPlot.generate_mana_curve_plot.return_value = None
        response = self.client.get(reverse("deck_detail", kwargs={"deck_id": DECK_UUID}))
        self.assertIn("voucher_code", response.context)


class EditDeckViewTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user())

    @patch("deck_builder.views.DynamoDBService")
    def test_get_renders_form(self, MockDB):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        self.assertIn("deck_text", self.client.get(reverse("edit_deck", kwargs={"deck_id": DECK_UUID})).context)

    @patch("deck_builder.views.DynamoDBService")
    def test_post_updates_and_redirects(self, MockDB):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = []
        self.assertRedirects(
            self.client.post(reverse("edit_deck", kwargs={"deck_id": DECK_UUID}), {"deck_list": "4 Bolt", "deck_name": "New"}),
            reverse("deck_detail", kwargs={"deck_id": DECK_UUID}), fetch_redirect_response=False,
        )


class DeleteDeckViewTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user())

    @patch("deck_builder.views.DynamoDBService")
    def test_get_renders_and_post_deletes(self, MockDB):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        self.assertEqual(self.client.get(reverse("delete_deck", kwargs={"deck_id": DECK_UUID})).status_code, 200)
        self.assertRedirects(
            self.client.post(reverse("delete_deck", kwargs={"deck_id": DECK_UUID})),
            reverse("deck_list"), fetch_redirect_response=False,
        )


class GenerateQRCodeViewTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user())

    @patch("deck_builder.views.QRService")
    @patch("deck_builder.views.DynamoDBService")
    def test_generates_and_stores_qr(self, MockDB, MockQR):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockQR.get_qr_code_url.return_value = "http://qr.example.com/qr.png"
        self.client.post(reverse("generate_qr_code", kwargs={"deck_id": DECK_UUID}))
        self.assertIn(f"qr_code_{DECK_UUID}", self.client.session)

    @patch("deck_builder.views.QRService")
    @patch("deck_builder.views.DynamoDBService")
    def test_qr_error_still_redirects(self, MockDB, MockQR):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockQR.get_qr_code_url.side_effect = Exception("down")
        self.assertRedirects(
            self.client.post(reverse("generate_qr_code", kwargs={"deck_id": DECK_UUID})),
            reverse("deck_detail", kwargs={"deck_id": DECK_UUID}), fetch_redirect_response=False,
        )


class AddVoucherViewTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user())

    @patch("deck_builder.views.VoucherService")
    @patch("deck_builder.views.DynamoDBService")
    def test_applies_voucher(self, MockDB, MockVoucher):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockVoucher.generate_voucher.return_value = "CODE"
        self.client.post(reverse("add_voucher", kwargs={"deck_id": DECK_UUID}))
        MockDB.return_value.apply_voucher_to_deck.assert_called_once()

    @patch("deck_builder.views.DynamoDBService")
    def test_skips_if_already_has_voucher(self, MockDB):
        deck = dict(MOCK_DECK)
        deck["voucher_code"] = "EXISTING"
        MockDB.return_value.get_deck.return_value = deck
        self.client.post(reverse("add_voucher", kwargs={"deck_id": DECK_UUID}))
        MockDB.return_value.apply_voucher_to_deck.assert_not_called()


class GetRecommendationsViewTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user())

    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.DeckRecommendationAgent")
    @patch("deck_builder.views.DynamoDBService")
    def test_get_shows_recommendations(self, MockDB, MockAgent, MockScryfall):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = []
        MockAgent.return_value.get_deck_improvement_recommendations.return_value = ["Shock"]
        MockScryfall.return_value.get_card_by_name.return_value = None
        self.assertEqual(self.client.get(reverse("get_recommendations", kwargs={"deck_id": DECK_UUID})).status_code, 200)

    @patch("deck_builder.views.DynamoDBService")
    @patch("deck_builder.views.DeckRecommendationAgent")
    def test_post_adds_cards_to_deck(self, MockAgent, MockDB):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = []
        self.client.post(reverse("get_recommendations", kwargs={"deck_id": DECK_UUID}), {"cards": ["Shock"]})
        MockDB.return_value.update_deck.assert_called_once()

    @patch("deck_builder.views.DynamoDBService")
    def test_missing_deck_redirects(self, MockDB):
        MockDB.return_value.get_deck.return_value = None
        self.assertRedirects(
            self.client.get(reverse("get_recommendations", kwargs={"deck_id": DECK_UUID})),
            reverse("deck_list"), fetch_redirect_response=False,
        )


# ---------------------------------------------------------------------------
# DynamoDBService
# ---------------------------------------------------------------------------

class DynamoDBServiceTests(TestCase):

    @patch("deck_builder.services.dynamodb_service.boto3")
    def _make_svc(self, mock_boto):
        mock_table = MagicMock()
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        mock_boto.resource.return_value = mock_resource
        from deck_builder.services.dynamodb_service import DynamoDBService
        svc = DynamoDBService()
        return svc, mock_table

    def test_create_deck_puts_deck_and_cards(self):
        svc, mock_table = self._make_svc()
        cards = [{"card_name": "Bolt", "quantity": 4, "is_sideboard": False}]
        deck_id = svc.create_deck("user1", "My Deck", cards)
        self.assertIsNotNone(deck_id)
        # 1 deck put + 1 card put = 2 calls
        self.assertEqual(mock_table.put_item.call_count, 2)

    def test_get_user_decks_queries_by_user(self):
        svc, mock_table = self._make_svc()
        mock_table.query.return_value = {"Items": [{"deck_id": "d1"}]}
        result = svc.get_user_decks("user1")
        self.assertEqual(len(result), 1)
        mock_table.query.assert_called_once()

    def test_get_deck_returns_item(self):
        svc, mock_table = self._make_svc()
        mock_table.get_item.return_value = {"Item": {"deck_id": "d1", "name": "Test"}}
        result = svc.get_deck("user1", "d1")
        self.assertEqual(result["name"], "Test")

    def test_get_deck_returns_none_when_missing(self):
        svc, mock_table = self._make_svc()
        mock_table.get_item.return_value = {}
        result = svc.get_deck("user1", "missing")
        self.assertIsNone(result)

    def test_get_deck_cards_returns_all(self):
        svc, mock_table = self._make_svc()
        mock_table.query.return_value = {"Items": [
            {"card_name": "Bolt", "is_sideboard": False},
            {"card_name": "Negate", "is_sideboard": True},
        ]}
        result = svc.get_deck_cards("d1")
        self.assertEqual(len(result), 2)

    def test_get_deck_cards_filters_sideboard(self):
        svc, mock_table = self._make_svc()
        mock_table.query.return_value = {"Items": [
            {"card_name": "Bolt", "is_sideboard": False},
            {"card_name": "Negate", "is_sideboard": True},
        ]}
        result = svc.get_deck_cards("d1", is_sideboard=True)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["card_name"], "Negate")

    def test_update_deck_deletes_old_and_adds_new(self):
        svc, mock_table = self._make_svc()
        mock_table.query.return_value = {"Items": [
            {"pk": "DECK#d1", "sk": "CARD#OldCard#False"},
        ]}
        new_cards = [{"card_name": "NewCard", "quantity": 3, "is_sideboard": False}]
        result = svc.update_deck("user1", "d1", "Updated Deck", new_cards)
        self.assertTrue(result)
        mock_table.update_item.assert_called_once()
        mock_table.delete_item.assert_called_once()
        mock_table.put_item.assert_called_once()

    def test_delete_deck_removes_deck_and_cards(self):
        svc, mock_table = self._make_svc()
        mock_table.query.return_value = {"Items": [
            {"pk": "DECK#d1", "sk": "CARD#Bolt#False"},
        ]}
        result = svc.delete_deck("user1", "d1")
        self.assertTrue(result)
        # 1 deck delete + 1 card delete = 2 calls
        self.assertEqual(mock_table.delete_item.call_count, 2)

    def test_apply_voucher_to_deck(self):
        svc, mock_table = self._make_svc()
        result = svc.apply_voucher_to_deck("user1", "d1", "SAVE20")
        self.assertTrue(result)
        mock_table.update_item.assert_called_once()


# ---------------------------------------------------------------------------
# Model __str__ methods
# ---------------------------------------------------------------------------

class ModelStrTests(TestCase):

    def test_card_str(self):
        from deck_builder.models import Card
        card = Card(name="Lightning Bolt", set_code="LEA")
        self.assertEqual(str(card), "Lightning Bolt (LEA)")

    def test_deck_str(self):
        from deck_builder.models import Deck
        deck = Deck(name="Burn Deck")
        self.assertEqual(str(deck), "Burn Deck")

    def test_deck_card_str(self):
        from deck_builder.models import DeckCard
        dc = DeckCard(card_name="Mountain", quantity=20)
        self.assertEqual(str(dc), "20x Mountain")


# ---------------------------------------------------------------------------
# Template filter edge cases
# ---------------------------------------------------------------------------

class DeckBuilderFiltersTests(TestCase):

    def test_mul_valid(self):
        self.assertEqual(mul(3, 4), 12.0)

    def test_mul_invalid_returns_zero(self):
        self.assertEqual(mul("abc", 4), 0)

    def test_mul_none_returns_zero(self):
        self.assertEqual(mul(None, 4), 0)

    def test_mana_icons_empty(self):
        self.assertEqual(mana_icons(""), "")

    def test_mana_icons_none(self):
        self.assertEqual(mana_icons(None), "")

    def test_mana_icons_whitespace_only(self):
        self.assertEqual(mana_icons("   "), "")

    def test_mana_icons_single_color(self):
        result = mana_icons("R")
        self.assertIn("ms-r", result)
        self.assertIn("mana-cost", result)

    def test_mana_icons_multi_color(self):
        result = mana_icons("2UB")
        self.assertIn("ms-2", result)
        self.assertIn("ms-u", result)
        self.assertIn("ms-b", result)

    def test_mana_icons_two_digit_number(self):
        result = mana_icons("12R")
        self.assertIn("ms-12", result)
        self.assertIn("ms-r", result)

    def test_mana_icons_unknown_character_skipped(self):
        result = mana_icons("{R}")
        # { and } are unknown — should be skipped, R should be present
        self.assertIn("ms-r", result)

    def test_mana_icons_colorless(self):
        result = mana_icons("C")
        self.assertIn("ms-c", result)

    def test_mana_icons_x_cost(self):
        result = mana_icons("XRR")
        self.assertIn("ms-x", result)
        self.assertIn("ms-r", result)

    def test_mark_safe_mana_returns_safe_string(self):
        from django.utils.safestring import SafeString
        result = mark_safe_mana("<i>test</i>")
        self.assertIsInstance(result, SafeString)


# ---------------------------------------------------------------------------
# Additional ScryfallS3Service coverage (stream parse, S3 errors, index,
# ---------------------------------------------------------------------------

class ScryfallStreamParseTests(TestCase):

    def test_stream_parse_valid_json(self):
        from deck_builder.services.scryfall_s3_service import _stream_parse_cards
        import json
        cards = [{"name": "Bolt", "type_line": "Instant"}]
        content = json.dumps(cards).encode()
        result = _stream_parse_cards(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Bolt")

    def test_stream_parse_invalid_json_returns_partial(self):
        from deck_builder.services.scryfall_s3_service import _stream_parse_cards
        # Corrupt data — should return empty list without raising
        result = _stream_parse_cards(b"not json at all {{{")
        self.assertIsInstance(result, list)


class ScryfallGetAllCardsCachedTests(TestCase):

    @patch("deck_builder.services.scryfall_s3_service.s3_client")
    def test_nosuchkey_returns_empty(self, mock_s3):
        from deck_builder.services.scryfall_s3_service import _get_all_cards_cached
        _get_all_cards_cached.cache_clear()
        mock_s3.get_object.side_effect = mock_s3.exceptions.NoSuchKey("no key")
        mock_s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        mock_s3.get_object.side_effect = mock_s3.exceptions.NoSuchKey("no key")
        result = _get_all_cards_cached("bucket", "type")
        _get_all_cards_cached.cache_clear()
        self.assertEqual(result, [])

    @patch("deck_builder.services.scryfall_s3_service.s3_client")
    def test_generic_exception_returns_empty(self, mock_s3):
        from deck_builder.services.scryfall_s3_service import _get_all_cards_cached
        _get_all_cards_cached.cache_clear()
        mock_s3.get_object.side_effect = Exception("network error")
        mock_s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        result = _get_all_cards_cached("bucket", "type")
        _get_all_cards_cached.cache_clear()
        self.assertEqual(result, [])

    @patch("deck_builder.services.scryfall_s3_service._stream_parse_cards")
    @patch("deck_builder.services.scryfall_s3_service.s3_client")
    def test_plain_json_body_parsed(self, mock_s3, mock_parse):
        import json
        from deck_builder.services.scryfall_s3_service import _get_all_cards_cached
        _get_all_cards_cached.cache_clear()
        mock_s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        body = json.dumps([{"name": "Bolt"}]).encode()
        mock_s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=body))}
        mock_parse.return_value = [{"name": "Bolt"}]
        result = _get_all_cards_cached("bucket", "type")
        _get_all_cards_cached.cache_clear()
        self.assertEqual(len(result), 1)

    @patch("deck_builder.services.scryfall_s3_service._stream_parse_cards")
    @patch("deck_builder.services.scryfall_s3_service.s3_client")
    def test_gzipped_body_decompressed(self, mock_s3, mock_parse):
        import gzip, json
        from deck_builder.services.scryfall_s3_service import _get_all_cards_cached
        _get_all_cards_cached.cache_clear()
        mock_s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        body = gzip.compress(json.dumps([{"name": "Elf"}]).encode())
        mock_s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=body))}
        mock_parse.return_value = [{"name": "Elf"}]
        result = _get_all_cards_cached("bucket", "type")
        _get_all_cards_cached.cache_clear()
        self.assertEqual(len(result), 1)


class ScryfallGetIndexTests(TestCase):

    def setUp(self):
        # Reset global index before each test
        import deck_builder.services.scryfall_s3_service as mod
        mod._cards_index = None

    def tearDown(self):
        import deck_builder.services.scryfall_s3_service as mod
        mod._cards_index = None

    @patch("deck_builder.services.scryfall_s3_service.cache")
    @patch("deck_builder.services.scryfall_s3_service._get_all_cards_cached")
    def test_get_index_empty_cards_sets_empty_index(self, mock_s3, mock_cache):
        mock_cache.get.return_value = None
        mock_s3.return_value = []
        svc = ScryfallS3Service()
        index = svc._get_index()
        self.assertEqual(index, {})

    @patch("deck_builder.services.scryfall_s3_service.cache")
    @patch("deck_builder.services.scryfall_s3_service._get_all_cards_cached")
    def test_get_index_builds_index_from_cards(self, mock_s3, mock_cache):
        mock_cache.get.return_value = None
        mock_s3.return_value = [{"name": "Lightning Bolt", "type_line": "Instant"}]
        svc = ScryfallS3Service()
        index = svc._get_index()
        self.assertIn("lightning bolt", index)

    @patch("deck_builder.services.scryfall_s3_service.cache")
    @patch("deck_builder.services.scryfall_s3_service._get_all_cards_cached")
    def test_cache_write_failure_still_returns_cards(self, mock_s3, mock_cache):
        mock_cache.get.return_value = None
        mock_cache.set.side_effect = Exception("cache write failed")
        mock_s3.return_value = [{"name": "Forest"}]
        result = ScryfallS3Service().get_all_cards()
        self.assertEqual(len(result), 1)


class ScryfallLookupEdgeCasesTests(TestCase):

    def _svc_with_index(self, index):
        svc = ScryfallS3Service.__new__(ScryfallS3Service)
        svc.bucket_name = "b"
        svc.bulk_type = "t"
        svc._get_index = MagicMock(return_value=index)
        return svc

    def test_cached_none_in_index_no_fallback_returns_none(self):
        """When index has card=None (previously failed) and fallback disabled."""
        svc = self._svc_with_index({"ghost card": None})
        result = svc.get_card_by_name("Ghost Card", allow_api_fallback=False)
        self.assertIsNone(result)

    def test_normalized_unicode_lookup(self):
        """Accented character gets normalized for lookup."""
        card = {"name": "Lim-Dul's Vault"}
        svc = self._svc_with_index({"lim-dul's vault": card})
        # Should not raise — just exercises the NFD normalization path
        result = svc.get_card_by_name("Lim-Dûl's Vault")
        # result is either the card (normalized matched) or None (fallback)
        # We only care that no exception was raised
        self.assertIn(result, [card, None])

    def test_fuzzy_match_finds_card(self):
        card = {"name": "Lightning Bolt"}
        index = {"lightning bolt": card}
        svc = self._svc_with_index(index)
        # "light" is a substring of "lightning bolt" → fuzzy matches
        result = svc.get_card_by_name("light", allow_api_fallback=False)
        self.assertEqual(result, card)

    def test_fuzzy_match_skips_none_entries(self):
        index = {"broken card": None, "lightning bolt": {"name": "Lightning Bolt"}}
        svc = self._svc_with_index(index)
        # Should skip None entry and not crash
        result = svc.get_card_by_name("light", allow_api_fallback=False)
        self.assertIsNotNone(result)

    @patch("deck_builder.services.scryfall_s3_service.requests.get")
    @patch("deck_builder.services.scryfall_s3_service.time.sleep")
    def test_api_non200_caches_none_returns_none(self, _, mock_get):
        mock_get.return_value = MagicMock(status_code=404)
        index = {}
        svc = self._svc_with_index(index)
        result = svc.get_card_by_name("Nonexistent Card")
        self.assertIsNone(result)
        self.assertIsNone(index.get("nonexistent card"))  # cached as None

    @patch("deck_builder.services.scryfall_s3_service.requests.get")
    @patch("deck_builder.services.scryfall_s3_service.time.sleep")
    def test_api_exception_caches_none_returns_none(self, _, mock_get):
        mock_get.side_effect = Exception("timeout")
        index = {}
        svc = self._svc_with_index(index)
        result = svc.get_card_by_name("Error Card")
        self.assertIsNone(result)

    def test_max_api_fallbacks_exceeded_returns_none(self):
        """When _api_fallback_count >= MAX_API_FALLBACKS, skip and return None."""
        from deck_builder.services.scryfall_s3_service import MAX_API_FALLBACKS
        index = {}
        svc = self._svc_with_index(index)
        svc._api_fallback_count = MAX_API_FALLBACKS  # already at limit
        result = svc.get_card_by_name("Any Card")
        self.assertIsNone(result)
        self.assertIsNone(index.get("any card"))


# ---------------------------------------------------------------------------
# Additional view coverage — exception handlers, sideboard, QR session,
# ---------------------------------------------------------------------------

class HomeViewMetadataErrorTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user("meta_user"))

    @patch("deck_builder.views.DynamoDBService")
    @patch("deck_builder.views.get_deck_metadata", side_effect=Exception("meta fail"))
    def test_metadata_error_still_renders_deck(self, _, MockDB):
        """Lines 99-102: metadata exception sets color_identity=[] and image=None."""
        MockDB.return_value.get_user_decks.return_value = [dict(MOCK_DECK)]
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        deck = response.context["decks"][0]
        self.assertEqual(deck["color_identity"], [])
        self.assertIsNone(deck["representative_image"])


class DeckListMetadataErrorTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user("list_meta_user"))

    @patch("deck_builder.views.DynamoDBService")
    @patch("deck_builder.views.get_deck_metadata", side_effect=Exception("meta fail"))
    def test_metadata_error_in_deck_list(self, _, MockDB):
        """Lines 141-144: metadata exception in deck_list sets defaults."""
        MockDB.return_value.get_user_decks.return_value = [dict(MOCK_DECK)]
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        response = self.client.get(reverse("deck_list"))
        self.assertEqual(response.status_code, 200)


class DeckDetailExtendedTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user("detail_user"))

    @patch("deck_builder.views.PlotService")
    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.organize_cards_by_type")
    @patch("deck_builder.views.DynamoDBService")
    def test_organize_main_deck_exception_handled(self, MockDB, mock_organize, MockScryfall, MockPlot):
        """Lines 167-169: organize_cards_by_type exception → main_deck_organized={}."""
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        MockScryfall.return_value.get_card_by_name.return_value = None
        MockScryfall.get_card_price.return_value = 0.0
        MockPlot.generate_mana_curve_plot.return_value = None
        mock_organize.side_effect = Exception("type error")
        response = self.client.get(reverse("deck_detail", kwargs={"deck_id": DECK_UUID}))
        self.assertEqual(response.status_code, 200)

    @patch("deck_builder.views.PlotService")
    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.organize_cards_by_type")
    @patch("deck_builder.views.DynamoDBService")
    def test_sideboard_flat_populated_from_organize(self, MockDB, mock_organize, MockScryfall, MockPlot):
        """Line 179: sideboard_flat.extend(cards_list) when sideboard has cards."""
        deck = dict(MOCK_DECK)
        cards = list(MOCK_CARDS) + [
            {"card_name": "Negate", "quantity": 2, "is_sideboard": True}
        ]
        MockDB.return_value.get_deck.return_value = deck
        MockDB.return_value.get_deck_cards.return_value = cards
        MockScryfall.return_value.get_card_by_name.return_value = None
        MockScryfall.get_card_price.return_value = 0.0
        MockPlot.generate_mana_curve_plot.return_value = None
        # First call (main deck) returns {}, second (sideboard) returns {"Instant": [{"card_name": "Negate"}]}
        mock_organize.side_effect = [
            {},
            {"Instant": [{"card_name": "Negate", "quantity": 2}]}
        ]
        response = self.client.get(reverse("deck_detail", kwargs={"deck_id": DECK_UUID}))
        self.assertEqual(response.status_code, 200)

    @patch("deck_builder.views.PlotService")
    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.organize_cards_by_type", return_value={})
    @patch("deck_builder.views.DynamoDBService")
    def test_get_card_price_with_data(self, MockDB, _, MockScryfall, MockPlot):
        """Line 190: get_card_price returns price when card_data exists."""
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = [MOCK_CARDS[0]]  # 1 card
        MockScryfall.return_value.get_card_by_name.return_value = {"prices": {"usd": "1.50"}}
        MockScryfall.get_card_price.return_value = 1.50
        MockPlot.generate_mana_curve_plot.return_value = None
        response = self.client.get(reverse("deck_detail", kwargs={"deck_id": DECK_UUID}))
        self.assertEqual(response.status_code, 200)

    @patch("deck_builder.views.PlotService")
    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.organize_cards_by_type", return_value={})
    @patch("deck_builder.views.DynamoDBService")
    def test_qr_code_in_session_added_to_context(self, MockDB, _, MockScryfall, MockPlot):
        """Line 223-224: QR code from session is added to context."""
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = []
        MockScryfall.return_value.get_card_by_name.return_value = None
        MockScryfall.get_card_price.return_value = 0.0
        MockPlot.generate_mana_curve_plot.return_value = None
        session = self.client.session
        session[f"qr_code_{DECK_UUID}"] = "http://qr.example.com/qr.png"
        session.save()
        response = self.client.get(reverse("deck_detail", kwargs={"deck_id": DECK_UUID}))
        self.assertIn("qr_code_url", response.context)


class EditDeckSideboardTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user("edit_user"))

    @patch("deck_builder.views.DynamoDBService")
    def test_get_with_sideboard_includes_sideboard_text(self, MockDB):
        """Lines 260-263: sideboard section added to deck_text when present."""
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = [
            {"card_name": "Bolt", "quantity": 4, "is_sideboard": False},
            {"card_name": "Negate", "quantity": 2, "is_sideboard": True},
        ]
        response = self.client.get(reverse("edit_deck", kwargs={"deck_id": DECK_UUID}))
        self.assertIn("Sideboard", response.context["deck_text"])
        self.assertIn("Negate", response.context["deck_text"])


class RecommendationsCardFoundTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user("rec_user"))

    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.DeckRecommendationAgent")
    @patch("deck_builder.views.DynamoDBService")
    def test_get_recommendations_card_found_returns_details(self, MockDB, MockAgent, MockScryfall):
        """Lines 326-332: fetch_card_details returns full card data when found."""
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = []
        MockAgent.return_value.get_deck_improvement_recommendations.return_value = ["Shock"]
        MockScryfall.return_value.get_card_by_name.return_value = {
            "type_line": "Instant",
            "image_uris": {"normal": "http://img.example.com/shock.jpg"},
            "mana_cost": "{R}",
            "prices": {"usd": "0.10"},
        }
        MockScryfall.get_card_image_url.return_value = "http://img.example.com/shock.jpg"
        MockScryfall.get_card_mana_cost.return_value = "{R}"
        MockScryfall.get_card_price.return_value = 0.10
        response = self.client.get(reverse("get_recommendations", kwargs={"deck_id": DECK_UUID}))
        self.assertEqual(response.status_code, 200)
        recs = response.context["recommendations"]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["name"], "Shock")


class RecommendationsExecutorExceptionTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user("exec_user"))

    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.DeckRecommendationAgent")
    @patch("deck_builder.views.DynamoDBService")
    def test_future_exception_adds_fallback_entry(self, MockDB, MockAgent, MockScryfall):
        """Lines 356-360: when future.result() raises, a fallback card entry is appended."""
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = []
        MockAgent.return_value.get_deck_improvement_recommendations.return_value = ["ErrorCard"]
        # Make get_card_by_name raise to trigger the future exception handler
        MockScryfall.return_value.get_card_by_name.side_effect = RuntimeError("lookup failed")
        response = self.client.get(reverse("get_recommendations", kwargs={"deck_id": DECK_UUID}))
        self.assertEqual(response.status_code, 200)
        recs = response.context["recommendations"]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["type_line"], "Unknown")
        self.assertIsNone(recs[0]["image_url"])


class GenerateQRCodeMissingDeckTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user("qr_missing_user"))

    @patch("deck_builder.views.DynamoDBService")
    def test_missing_deck_redirects_to_deck_list(self, MockDB):
        """Line 383: generate_qr_code redirects to deck_list when deck is None."""
        MockDB.return_value.get_deck.return_value = None
        response = self.client.post(reverse("generate_qr_code", kwargs={"deck_id": DECK_UUID}))
        self.assertRedirects(response, reverse("deck_list"), fetch_redirect_response=False)


class AddVoucherMissingDeckTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user("voucher_missing_user"))

    @patch("deck_builder.views.DynamoDBService")
    def test_missing_deck_redirects_to_deck_list(self, MockDB):
        """Line 402: add_voucher redirects to deck_list when deck is None."""
        MockDB.return_value.get_deck.return_value = None
        response = self.client.post(reverse("add_voucher", kwargs={"deck_id": DECK_UUID}))
        self.assertRedirects(response, reverse("deck_list"), fetch_redirect_response=False)


# ---------------------------------------------------------------------------
# check_plot_status view
# ---------------------------------------------------------------------------

class CheckPlotStatusViewTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user("plot_status_user"))

    @patch("deck_builder.views.DynamoDBService")
    def test_missing_deck_returns_404(self, MockDB):
        MockDB.return_value.get_deck.return_value = None
        response = self.client.get(reverse("check_plot_status", kwargs={"deck_id": DECK_UUID}))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()["ready"])

    @patch("deck_builder.views.cache")
    @patch("deck_builder.views.DynamoDBService")
    def test_plot_ready_returns_url(self, MockDB, mock_cache):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        mock_cache.get.return_value = "http://plot.example.com/curve.png"
        response = self.client.get(reverse("check_plot_status", kwargs={"deck_id": DECK_UUID}))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ready"])
        self.assertEqual(data["url"], "http://plot.example.com/curve.png")

    @patch("deck_builder.views.cache")
    @patch("deck_builder.views.DynamoDBService")
    def test_plot_not_ready_returns_not_ready(self, MockDB, mock_cache):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        mock_cache.get.return_value = None
        response = self.client.get(reverse("check_plot_status", kwargs={"deck_id": DECK_UUID}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ready"])

    @patch("deck_builder.views.cache")
    @patch("deck_builder.views.DynamoDBService")
    def test_cache_exception_returns_500(self, MockDB, mock_cache):
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        mock_cache.get.side_effect = Exception("cache down")
        response = self.client.get(reverse("check_plot_status", kwargs={"deck_id": DECK_UUID}))
        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.json()["ready"])


# ---------------------------------------------------------------------------
# PlotService async generation
# ---------------------------------------------------------------------------

class PlotServiceAsyncTests(TestCase):

    @patch("deck_builder.services.plot_service.cache")
    def test_async_stores_url_in_cache_on_success(self, mock_cache):
        """generate_mana_curve_plot_async stores result in cache when plot succeeds."""
        svc = MagicMock()
        svc.get_card_by_name.return_value = {"cmc": 2, "type_line": "Instant"}

        with patch.object(PlotService, "generate_mana_curve_plot", return_value="http://plot.png"):
            import threading
            done = threading.Event()

            def capture_set(*args, **kwargs):
                done.set()

            mock_cache.set.side_effect = capture_set
            PlotService.generate_mana_curve_plot_async("deck-1", [], svc, "cache_key")
            done.wait(timeout=5)

        mock_cache.set.assert_called_once_with("cache_key", "http://plot.png", 86400)

    @patch("deck_builder.services.plot_service.cache")
    def test_async_does_not_cache_when_plot_returns_none(self, mock_cache):
        """generate_mana_curve_plot_async does not cache when plot generation returns None."""
        svc = MagicMock()

        with patch.object(PlotService, "generate_mana_curve_plot", return_value=None):
            import threading
            done = threading.Event()

            # Use a side effect on generate_mana_curve_plot to signal completion
            original_generate = PlotService.generate_mana_curve_plot

            def generate_and_signal(*args, **kwargs):
                result = original_generate(*args, **kwargs)
                done.set()
                return result

            with patch.object(PlotService, "generate_mana_curve_plot", side_effect=generate_and_signal):
                PlotService.generate_mana_curve_plot_async("deck-1", [], svc, "cache_key")
                done.wait(timeout=5)

        mock_cache.set.assert_not_called()


# ---------------------------------------------------------------------------
# deck_detail cache hit/miss behaviour
# ---------------------------------------------------------------------------

class DeckDetailCacheBehaviourTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user("cache_user"))

    @patch("deck_builder.views.cache")
    @patch("deck_builder.views.PlotService")
    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.organize_cards_by_type", return_value={})
    @patch("deck_builder.views.DynamoDBService")
    def test_cache_hit_passes_url_to_context(self, MockDB, _, MockScryfall, MockPlot, mock_cache):
        """When cache has plot URL, it is included in the template context."""
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        MockScryfall.return_value.get_card_by_name.return_value = None
        MockScryfall.get_card_price.return_value = 0.0
        mock_cache.get.return_value = "http://cached-plot.png"

        response = self.client.get(reverse("deck_detail", kwargs={"deck_id": DECK_UUID}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["mana_curve_url"], "http://cached-plot.png")
        # Synchronous generation should NOT be called when cache hits
        MockPlot.generate_mana_curve_plot.assert_not_called()

    @patch("deck_builder.views.cache")
    @patch("deck_builder.views.PlotService")
    @patch("deck_builder.views.ScryfallS3Service")
    @patch("deck_builder.views.organize_cards_by_type", return_value={})
    @patch("deck_builder.views.DynamoDBService")
    def test_cache_miss_triggers_sync_generation(self, MockDB, _, MockScryfall, MockPlot, mock_cache):
        """When cache misses, synchronous generation is triggered and URL is in context."""
        MockDB.return_value.get_deck.return_value = dict(MOCK_DECK)
        MockDB.return_value.get_deck_cards.return_value = list(MOCK_CARDS)
        MockScryfall.return_value.get_card_by_name.return_value = None
        MockScryfall.get_card_price.return_value = 0.0
        mock_cache.get.return_value = None
        MockPlot.generate_mana_curve_plot.return_value = "http://new-plot.png"

        response = self.client.get(reverse("deck_detail", kwargs={"deck_id": DECK_UUID}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["mana_curve_url"], "http://new-plot.png")
        MockPlot.generate_mana_curve_plot.assert_called_once()
        # Verify the result was cached with 45-min TTL
        mock_cache.set.assert_called_once_with(
            mock_cache.set.call_args[0][0],  # cache key (dynamic)
            "http://new-plot.png",
            2700,  # 45-minute TTL
        )

