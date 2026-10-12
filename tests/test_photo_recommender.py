import base64
import json
import os
import unittest
from datetime import date
from io import BytesIO
from unittest.mock import Mock, patch

from PIL import Image

from photo_recommender import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    PhotoAnalysisError,
    _prepare_photo,
    recommend_from_photo,
)


def make_png(width=64, height=48):
    image = Image.new("RGB", (width, height), color="#7799aa")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def make_bmp():
    image = Image.new("RGB", (64, 48), color="#7799aa")
    output = BytesIO()
    image.save(output, format="BMP")
    return output.getvalue()


def make_large_jpeg(width=6000, height=4000):
    image = Image.new("RGB", (width, height), color="#7799aa")
    output = BytesIO()
    image.save(output, format="JPEG", quality=75)
    return output.getvalue()


def make_large_image(format_name, width=6000, height=4000):
    image = Image.new("RGB", (width, height), color="#7799aa")
    output = BytesIO()
    image.save(output, format=format_name)
    image.close()
    return output.getvalue()


def make_response_payload(outfit_count=5):
    outfits = []
    for index in range(outfit_count):
        outfits.append(
            {
                "title": f"スタイル {index + 1}",
                "style": "ストリート",
                "colors": [
                    {"name": "ネイビー", "hex": "#243956"},
                    {"name": "アイボリー", "hex": "#F1EBDD"},
                    {"name": "レッド", "hex": "#B52D45"},
                ],
                "top": "アップロードしたシャツ",
                "bottom": "ワイドパンツ",
                "outerwear": "ジャケット",
                "shoes": "スニーカー",
                "accessory": "ショルダーバッグ",
                "reason": "色のコントラストを活かした提案です。",
            }
        )
    return {
        "garment_found": True,
        "item_type": "シャツ",
        "item_summary": "青系のシャツ",
        "colors": ["青"],
        "outfits": outfits,
    }


class PhotoRecommenderTests(unittest.TestCase):
    def setUp(self):
        self.api_key = patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True)
        self.api_key.start()
        self.addCleanup(self.api_key.stop)
        self.image_bytes = make_png()

    def call_recommender(self):
        return recommend_from_photo(
            image_bytes=self.image_bytes,
            audience="ユニセックス",
            preferred_style="おまかせ",
            preferred_palette="おまかせ",
            today=date(2026, 10, 12),
            weather_context="東京、体感18°C",
            seasonal_context="レトロスポーツ",
        )

    @patch("photo_recommender.requests.post")
    def test_sends_resized_jpeg_and_returns_five_recommendations(self, post):
        image_response = Mock()
        image_response.ok = True
        image_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(make_response_payload(), ensure_ascii=False)
                    }
                }
            ]
        }
        post.return_value = image_response
        self.image_bytes = make_png(1800, 1400)

        result = self.call_recommender()

        self.assertTrue(result.garment_found)
        self.assertEqual(result.item_type, "シャツ")
        self.assertEqual(len(result.outfits), 5)
        self.assertEqual(len(result.outfits[0].colors), 3)
        post.assert_called_once()
        request = post.call_args.kwargs
        self.assertEqual(
            request["headers"]["Authorization"],
            "Bearer test-key",
        )
        self.assertEqual(request["timeout"], (10, 90))
        body = request["json"]
        self.assertEqual(body["model"], "gpt-4.1-mini")
        image_url = body["messages"][0]["content"][1]["image_url"]["url"]
        self.assertTrue(image_url.startswith("data:image/jpeg;base64,"))
        encoded_image = image_url.split(",", 1)[1]
        with Image.open(BytesIO(base64.b64decode(encoded_image))) as sent_image:
            self.assertEqual(sent_image.format, "JPEG")
            self.assertLessEqual(max(sent_image.size), 1280)
        schema = body["response_format"]["json_schema"]["schema"]
        self.assertNotIn("maxItems", json.dumps(schema))
        self.assertNotIn("minItems", json.dumps(schema))

    @patch("photo_recommender.requests.post")
    def test_non_clothing_photo_returns_no_outfits(self, post):
        payload = make_response_payload(outfit_count=0)
        payload.update({"garment_found": False, "item_type": "", "item_summary": "アイテムなし"})
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]
        }
        post.return_value = response

        result = self.call_recommender()

        self.assertFalse(result.garment_found)
        self.assertEqual(result.outfits, ())

    def test_api_key_is_required_before_processing_image(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(PhotoAnalysisError, "OPENAI_API_KEY"):
                self.call_recommender()

    @patch("photo_recommender.requests.post")
    def test_api_key_can_be_passed_from_the_app_ui(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(make_response_payload(), ensure_ascii=False)
                    }
                }
            ]
        }
        post.return_value = response

        with patch.dict(os.environ, {}, clear=True):
            result = recommend_from_photo(
                image_bytes=self.image_bytes,
                audience="ユニセックス",
                preferred_style="おまかせ",
                preferred_palette="おまかせ",
                today=date(2026, 10, 12),
                weather_context=None,
                seasonal_context="レトロスポーツ",
                api_key="ui-test-key",
            )

        self.assertEqual(len(result.outfits), 5)
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer ui-test-key",
        )

    @patch("photo_recommender.requests.post")
    def test_empty_invalid_and_oversized_images_are_rejected(self, post):
        for image_bytes in (b"", b"not an image", b"x" * (MAX_IMAGE_BYTES + 1)):
            with self.subTest(size=len(image_bytes)):
                self.image_bytes = image_bytes
                with self.assertRaises(PhotoAnalysisError):
                    self.call_recommender()
        post.assert_not_called()

    def test_decodable_image_formats_are_normalized_to_jpeg(self):
        image_url = _prepare_photo(make_bmp())

        self.assertTrue(image_url.startswith("data:image/jpeg;base64,"))
        encoded = image_url.split(",", 1)[1]
        with Image.open(BytesIO(base64.b64decode(encoded))) as normalized:
            self.assertEqual(normalized.format, "JPEG")

    @patch("photo_recommender.requests.post")
    def test_high_resolution_phone_jpeg_is_downsampled_before_analysis(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(make_response_payload(), ensure_ascii=False)
                    }
                }
            ]
        }
        post.return_value = response
        self.image_bytes = make_large_jpeg()

        result = self.call_recommender()
        self.assertEqual(len(result.outfits), 5)
        image_url = post.call_args.kwargs["json"]["messages"][0]["content"][1]["image_url"]["url"]
        self.assertTrue(image_url.startswith("data:image/jpeg;base64,"))
        encoded = image_url.split(",", 1)[1]
        with Image.open(BytesIO(base64.b64decode(encoded))) as normalized:
            self.assertEqual(normalized.format, "JPEG")
            self.assertEqual(normalized.size, (1280, 853))

    def test_high_resolution_png_and_webp_are_downsampled_to_jpeg(self):
        for format_name in ("PNG", "WEBP"):
            with self.subTest(format=format_name):
                image_url = _prepare_photo(make_large_image(format_name))
                self.assertTrue(image_url.startswith("data:image/jpeg;base64,"))
                encoded = image_url.split(",", 1)[1]
                with Image.open(BytesIO(base64.b64decode(encoded))) as normalized:
                    self.assertEqual(normalized.format, "JPEG")
                    self.assertLessEqual(max(normalized.size), 1280)

    def test_images_over_the_source_pixel_limit_are_rejected(self):
        with patch("photo_recommender.Image.open") as open_image:
            open_image.return_value.__enter__.return_value.size = (MAX_IMAGE_PIXELS + 1, 1)

            with self.assertRaisesRegex(PhotoAnalysisError, "解像度"):
                _prepare_photo(b"jpeg")

    @patch("photo_recommender.requests.post")
    def test_api_errors_are_reported(self, post):
        response = Mock()
        response.ok = False
        response.status_code = 400
        response.json.return_value = {"error": {"message": "Invalid request"}}
        post.return_value = response

        with self.assertRaisesRegex(PhotoAnalysisError, "Invalid request"):
            self.call_recommender()

    @patch("photo_recommender.requests.post")
    def test_response_must_contain_exactly_five_outfits(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            make_response_payload(outfit_count=4),
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        post.return_value = response

        with self.assertRaisesRegex(PhotoAnalysisError, "5案"):
            self.call_recommender()

    @patch("photo_recommender.requests.post")
    def test_invalid_color_hex_is_rejected(self, post):
        payload = make_response_payload()
        payload["outfits"][0]["colors"][0]["hex"] = "blue"
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(payload, ensure_ascii=False)
                    }
                }
            ]
        }
        post.return_value = response

        with self.assertRaisesRegex(PhotoAnalysisError, "色データ"):
            self.call_recommender()

    @patch("photo_recommender.requests.post")
    def test_malformed_api_response_is_reported(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {"choices": [{"message": "invalid"}]}
        post.return_value = response

        with self.assertRaisesRegex(PhotoAnalysisError, "不完全な応答"):
            self.call_recommender()


if __name__ == "__main__":
    unittest.main()
