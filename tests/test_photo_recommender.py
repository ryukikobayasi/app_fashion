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


def make_response_payload(outfit_count=8):
    outfits = []
    for index in range(outfit_count):
        outfits.append(
            {
                "title": f"スタイル {index + 1}",
                "style": "きれいめカジュアル",
                "colors": [
                    {"name": "ネイビー", "hex": "#243956"},
                    {"name": "アイボリー", "hex": "#F1EBDD"},
                    {"name": "レッド", "hex": "#B52D45"},
                ],
                "top": "アップロードしたシャツ",
                "bottom": "ワイドパンツ",
                "outerwear": "ジャケット",
                "shoes": "黒の厚底靴",
                "accessory": (
                    "ブラックスピネルのネックレスとセイコーの時計"
                    if index % 2 == 0
                    else "ブラックスピネルのネックレスとロンジンの自動巻き時計"
                ),
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

    def call_recommender(self, weather_context="東京、体感18°C"):
        return recommend_from_photo(
            image_bytes=self.image_bytes,
            audience="ユニセックス",
            preferred_style="きれいめカジュアル",
            preferred_palette="おまかせ",
            today=date(2026, 10, 12),
            weather_context=weather_context,
            seasonal_context="レトロスポーツ",
        )

    @patch("photo_recommender.requests.post")
    def test_sends_resized_jpeg_and_returns_eight_recommendations(self, post):
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
        self.assertEqual(len(result.outfits), 8)
        self.assertTrue(all(outfit.style == "きれいめカジュアル" for outfit in result.outfits))
        self.assertTrue(all("ブラックスピネル" in outfit.accessory for outfit in result.outfits))
        self.assertTrue(all("黒" in outfit.shoes and "厚底" in outfit.shoes for outfit in result.outfits))
        self.assertTrue(any("セイコー" in outfit.accessory for outfit in result.outfits))
        self.assertTrue(any("ロンジン" in outfit.accessory for outfit in result.outfits))
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
        prompt = body["messages"][0]["content"][0]["text"]
        self.assertIn("8案", prompt)
        self.assertIn("8案すべてをきれいめカジュアルに統一", prompt)
        self.assertIn("ブラックスピネルのネックレス", prompt)
        self.assertIn("セイコーの時計", prompt)
        self.assertIn("ロンジンの自動巻き時計", prompt)
        self.assertIn("黒の厚底靴", prompt)
        self.assertIn("前年同月の平均気温", prompt)
        self.assertEqual(body["max_completion_tokens"], 5500)
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
    def test_historical_temperature_is_passed_as_a_reference_not_a_forecast(self, post):
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
        historical_context = (
            "前年同月（2025年10月）の平均気温 17.4°C"
            "（今日の実況・予報ではない季節参考値。降水・風・湿度は不明）"
        )

        self.call_recommender(weather_context=historical_context)

        prompt = post.call_args.kwargs["json"]["messages"][0]["content"][0]["text"]
        self.assertIn(historical_context, prompt)
        self.assertIn("今日の実況・予報ではない季節参考値", prompt)
        self.assertIn("降水・風・湿度が不明な場合", prompt)

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

    @patch("photo_recommender.requests.post")
    def test_accepts_more_than_four_detected_item_colors(self, post):
        payload = make_response_payload()
        payload["colors"] = ["青", "白", "黒", "グレー", "赤"]
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

        result = self.call_recommender()

        self.assertEqual(result.colors, ("青", "白", "黒", "グレー", "赤"))
        self.assertEqual(len(result.outfits), 8)

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
                preferred_style="きれいめカジュアル",
                preferred_palette="おまかせ",
                today=date(2026, 10, 12),
                weather_context=None,
                seasonal_context="レトロスポーツ",
                api_key="ui-test-key",
            )

        self.assertEqual(len(result.outfits), 8)
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
        self.assertEqual(len(result.outfits), 8)
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
    def test_response_must_contain_exactly_eight_outfits(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            make_response_payload(outfit_count=7),
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        post.return_value = response

        with self.assertRaisesRegex(PhotoAnalysisError, "8案"):
            self.call_recommender()

    @patch("photo_recommender.requests.post")
    def test_response_must_use_smart_casual_style_for_all_outfits(self, post):
        payload = make_response_payload()
        payload["outfits"][0]["style"] = "ストリート"
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "choices": [
                {"message": {"content": json.dumps(payload, ensure_ascii=False)}}
            ]
        }
        post.return_value = response

        with self.assertRaisesRegex(PhotoAnalysisError, "全案をきれいめカジュアル"):
            self.call_recommender()

    @patch("photo_recommender.requests.post")
    def test_response_must_include_requested_necklace_shoes_and_watch_brands(self, post):
        payload = make_response_payload()
        payload["outfits"][0]["shoes"] = "白いスニーカー"
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "choices": [
                {"message": {"content": json.dumps(payload, ensure_ascii=False)}}
            ]
        }
        post.return_value = response

        with self.assertRaisesRegex(PhotoAnalysisError, "黒の厚底靴"):
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
