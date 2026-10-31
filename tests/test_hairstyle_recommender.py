import base64
import json
import os
import unittest
from datetime import date
from io import BytesIO
from unittest.mock import Mock, patch

from PIL import Image

from hairstyle_recommender import (
    HAIRSTYLE_RECOMMENDATIONS_PER_CATEGORY,
    HairstyleAnalysisError,
    _parse_analysis,
    recommend_hairstyles,
)


def make_jpeg():
    image = Image.new("RGB", (64, 80), color="#7799aa")
    output = BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


def make_recommendations(prefix, category):
    return [
        {
            "title": f"{prefix} {index}",
            "suitability_reason": "写真で見える輪郭と髪の流れを活かします。",
            "styling": "ドライヤーで根元を立ち上げ、少量のワックスで整えます。",
            "salon_request": (
                "カットせず、今の長さのままセットします。"
                if category == "current_hair"
                else "サイドをすっきりさせ、前髪は自然に流せる長さで整えます。"
            ),
            "maintenance": "朝のドライヤーと少量のスタイリング剤で整えられます。",
            "chemical_treatment": "なし",
        }
        for index in range(1, HAIRSTYLE_RECOMMENDATIONS_PER_CATEGORY + 1)
    ]


def make_analysis_payload():
    return {
        "face_shape_estimate": "やや面長に見える印象（写真からの目安）",
        "visible_features": "前髪は自然に流れ、トップに動きを出しやすそうです。",
        "trend_direction": "自然な束感と軽いレイヤーを活かす方向です。",
        "current_hair_recommendations": make_recommendations("セット案", "current_hair"),
        "salon_cut_recommendations": make_recommendations("カット案", "salon_cut"),
    }


class HairstyleRecommenderTests(unittest.TestCase):
    def setUp(self):
        self.api_key = patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "hairstyle-test-key"},
            clear=True,
        )
        self.api_key.start()
        self.addCleanup(self.api_key.stop)
        self.image_bytes = make_jpeg()

    @patch("hairstyle_recommender.requests.post")
    def test_returns_five_set_styles_and_five_salon_cuts(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(make_analysis_payload(), ensure_ascii=False)
                    }
                }
            ]
        }
        post.return_value = response

        result = recommend_hairstyles(self.image_bytes, today=date(2026, 10, 12))

        self.assertEqual(len(result.current_hair_recommendations), 5)
        self.assertEqual(len(result.salon_cut_recommendations), 5)
        self.assertEqual(result.face_shape_estimate, "やや面長に見える印象（写真からの目安）")
        self.assertEqual(
            len(
                {
                    recommendation.title
                    for recommendation in (
                        *result.current_hair_recommendations,
                        *result.salon_cut_recommendations,
                    )
                }
            ),
            10,
        )
        request = post.call_args.kwargs
        self.assertEqual(request["timeout"], (10, 90))
        self.assertTrue(request["headers"]["Authorization"].endswith("hairstyle-test-key"))
        body = request["json"]
        prompt = body["messages"][0]["content"][0]["text"]
        self.assertIn("今の長さ", prompt)
        self.assertIn("美容室でカット", prompt)
        self.assertIn("パーマ", prompt)
        self.assertIn("カラー", prompt)
        schema = body["response_format"]["json_schema"]["schema"]
        self.assertEqual(
            schema["properties"]["current_hair_recommendations"]["items"]["properties"][
                "chemical_treatment"
            ]["enum"],
            ["なし"],
        )
        image_url = body["messages"][0]["content"][1]["image_url"]["url"]
        self.assertTrue(image_url.startswith("data:image/jpeg;base64,"))
        with Image.open(BytesIO(base64.b64decode(image_url.split(",", 1)[1]))) as sent_image:
            self.assertEqual(sent_image.format, "JPEG")

    def test_rejects_missing_api_key_and_invalid_photo(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(HairstyleAnalysisError, "OPENAI_API_KEY"):
                recommend_hairstyles(self.image_bytes)

        with patch("hairstyle_recommender.requests.post") as post:
            with self.assertRaises(HairstyleAnalysisError):
                recommend_hairstyles(b"not an image", api_key="test-key")
        post.assert_not_called()

    def test_rejects_incomplete_or_chemical_recommendations(self):
        payload = make_analysis_payload()
        payload["salon_cut_recommendations"].pop()
        with self.assertRaisesRegex(HairstyleAnalysisError, "5案"):
            _parse_analysis(json.dumps(payload, ensure_ascii=False))

        payload = make_analysis_payload()
        payload["salon_cut_recommendations"][0]["chemical_treatment"] = "パーマ"
        with self.assertRaisesRegex(HairstyleAnalysisError, "薬剤を使わない"):
            _parse_analysis(json.dumps(payload, ensure_ascii=False))

        payload = make_analysis_payload()
        payload["current_hair_recommendations"][0]["styling"] = "髪をカラーで染めて整えます。"
        with self.assertRaisesRegex(HairstyleAnalysisError, "薬剤施術"):
            _parse_analysis(json.dumps(payload, ensure_ascii=False))

    def test_allows_negated_treatment_mentions_but_blocks_active_services(self):
        for safe_description in (
            "パーマは不要です。ドライヤーで自然に整えます。",
            "カラーを入れずに、今の髪色を活かします。",
            "地毛のカラーを活かし、束感を出します。",
            "カラーはそのままにします。",
            "パーマ風の動きはワックスで作れます。",
        ):
            with self.subTest(description=safe_description):
                payload = make_analysis_payload()
                payload["current_hair_recommendations"][0]["styling"] = safe_description
                _parse_analysis(json.dumps(payload, ensure_ascii=False))

        for active_description in (
            "ゆるいパーマをかけて動きを出します。",
            "カラーを入れて明るくします。",
            "髪を染めて印象を変えます。",
        ):
            with self.subTest(description=active_description):
                payload = make_analysis_payload()
                payload["current_hair_recommendations"][0]["styling"] = active_description
                with self.assertRaisesRegex(HairstyleAnalysisError, "薬剤施術"):
                    _parse_analysis(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
