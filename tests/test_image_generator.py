import base64
import json
import os
import unittest
from io import BytesIO
from unittest.mock import Mock, patch

from PIL import Image

from outfit_engine import OMOTESANDO_CLEAN_CASUAL_STYLE, Outfit as RuleBasedOutfit
from image_generator import (
    DEFAULT_IMAGE_MODEL,
    ImageGenerationError,
    OPENAI_IMAGE_EDIT_URL,
    OPENAI_IMAGE_GENERATION_URL,
    generate_outfit_image,
    generate_rule_based_outfit_image,
    generate_hairstyle_triptych,
)
from hairstyle_recommender import HairstyleRecommendation
from photo_recommender import OutfitRecommendation, RECOMMENDATION_STYLE


def make_jpeg():
    image = Image.new("RGB", (32, 48), color="#7890ab")
    output = BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


class ImageGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.api_key = patch.dict(os.environ, {"OPENAI_API_KEY": "image-test-key"}, clear=True)
        self.api_key.start()
        self.addCleanup(self.api_key.stop)
        self.generated_jpeg = make_jpeg()
        self.outfit = OutfitRecommendation(
            title="シティ・レイヤード",
            pattern="シアーインナー×レイヤード",
            style=RECOMMENDATION_STYLE,
            colors=(
                ("ネイビー", "#243956"),
                ("アイボリー", "#F1EBDD"),
                ("レッド", "#B52D45"),
            ),
            inner="薄手の黒ハイネックを襟元と袖口から見せる",
            top="写真のブルーシャツ",
            bottom="ワイドスラックス",
            outerwear="ショートコート",
            shoes="レザースニーカー",
            accessory="ミニショルダー",
            extra_item="シルバーの細チェーン",
            extra_item_reason="顔まわりにさりげない輝きを加えます。",
            reason="ブルーシャツを主役にした着こなしです。",
        )
        self.hairstyle = HairstyleRecommendation(
            title="ナチュラル・アップバング",
            suitability_reason="顔まわりをすっきり見せます。",
            styling="ドライヤーで前髪を立ち上げ、少量のワックスで整えます。",
            salon_request="サイドを整え、前髪は自然に上げられる長さにします。",
            maintenance="朝のドライヤーで形を作りやすいスタイルです。",
        )

    def make_success_response(self):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "data": [
                {
                    "b64_json": base64.b64encode(self.generated_jpeg).decode("ascii")
                }
            ]
        }
        return response

    @patch("image_generator.requests.post")
    def test_generates_one_portrait_image_for_the_selected_outfit(self, post):
        post.return_value = self.make_success_response()

        result = generate_outfit_image(
            item_type="シャツ",
            item_summary="青系の長袖シャツ",
            audience="ユニセックス",
            outfit=self.outfit,
        )

        self.assertEqual(result, self.generated_jpeg)
        request = post.call_args.kwargs
        self.assertEqual(
            request["headers"]["Authorization"],
            "Bearer image-test-key",
        )
        self.assertEqual(request["timeout"], (10, 120))
        payload = request["json"]
        self.assertEqual(payload["model"], DEFAULT_IMAGE_MODEL)
        self.assertEqual(payload["size"], "1024x1536")
        self.assertEqual(payload["quality"], "medium")
        self.assertEqual(payload["output_format"], "jpeg")
        self.assertEqual(payload["n"], 1)
        self.assertIn("青系の長袖シャツ", payload["prompt"])
        self.assertIn("薄手の黒ハイネック", payload["prompt"])
        self.assertIn("ワイドスラックス", payload["prompt"])
        self.assertIn("シアーインナー×レイヤード", payload["prompt"])
        self.assertIn("シルバーの細チェーン", payload["prompt"])
        with Image.open(BytesIO(result)) as image:
            self.assertEqual(image.format, "JPEG")

    @patch("image_generator.requests.post")
    def test_generates_photo_free_image_from_the_selected_outfit(self, post):
        post.return_value = self.make_success_response()
        outfit = RuleBasedOutfit(
            title="表参道・ミニマルテーラード",
            style=OMOTESANDO_CLEAN_CASUAL_STYLE,
            trend="グレー×ワイン",
            palette="チャコール × ライトグレー × アイボリー",
            colors=(
                ("チャコール", "#34353A"),
                ("ライトグレー", "#A7A8AD"),
                ("アイボリー", "#F2EEE7"),
            ),
            color_style="ニュートラル",
            color_tip="チャコールを軸にアイボリーを挟みます。",
            top="ハイゲージモックネック",
            bottom="ワンタックのウールスラックス",
            outerwear="ダブルジャケット",
            shoes="レザーローファー",
            accessory="レザーベルト",
            reason="今日の気温に合わせたレイヤードです。",
        )

        result = generate_rule_based_outfit_image("メンズ", outfit)

        self.assertEqual(result, self.generated_jpeg)
        request = post.call_args
        self.assertEqual(request.args[0], OPENAI_IMAGE_GENERATION_URL)
        payload = request.kwargs["json"]
        self.assertEqual(payload["n"], 1)
        self.assertIn("No wardrobe photo was provided", payload["prompt"])
        self.assertIn("refined, clean-casual silhouette", payload["prompt"])
        self.assertIn("almost extravagantly", payload["prompt"])
        self.assertIn("exaggerated but wearable proportions", payload["prompt"])
        self.assertIn("表参道・ミニマルテーラード", payload["prompt"])
        self.assertIn("ハイゲージモックネック", payload["prompt"])
        self.assertIn("ワンタックのウールスラックス", payload["prompt"])
        self.assertIn("レザーローファー", payload["prompt"])
        self.assertNotIn("Key item from the user's wardrobe photo", payload["prompt"])

    @patch("image_generator.requests.post")
    def test_model_can_be_overridden_by_environment(self, post):
        post.return_value = self.make_success_response()

        with patch.dict(os.environ, {"OPENAI_IMAGE_MODEL": "gpt-image-1"}):
            generate_outfit_image("シャツ", "青いシャツ", "ユニセックス", self.outfit)

        self.assertEqual(post.call_args.kwargs["json"]["model"], "gpt-image-1")

    def test_api_key_is_required(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ImageGenerationError, "OPENAI_API_KEY"):
                generate_outfit_image("シャツ", "青いシャツ", "ユニセックス", self.outfit)

    @patch("image_generator.requests.post")
    def test_api_error_is_reported(self, post):
        response = Mock()
        response.ok = False
        response.status_code = 400
        response.json.return_value = {"error": {"message": "Image request rejected"}}
        post.return_value = response

        with self.assertRaisesRegex(ImageGenerationError, "Image request rejected"):
            generate_outfit_image("シャツ", "青いシャツ", "ユニセックス", self.outfit)

    @patch("image_generator.requests.post")
    def test_invalid_image_response_is_rejected(self, post):
        response = Mock()
        response.ok = True
        response.json.return_value = {"data": [{"b64_json": "not-base64!"}]}
        post.return_value = response

        with self.assertRaisesRegex(ImageGenerationError, "有効な画像"):
            generate_outfit_image("シャツ", "青いシャツ", "ユニセックス", self.outfit)

    @patch("image_generator.requests.post")
    def test_generates_reference_based_three_view_hairstyle_preview(self, post):
        post.return_value = self.make_success_response()

        result = generate_hairstyle_triptych(
            reference_photo=make_jpeg(),
            hairstyle=self.hairstyle,
            category="current_hair",
            api_key="hairstyle-test-key",
        )

        self.assertEqual(result, self.generated_jpeg)
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], OPENAI_IMAGE_EDIT_URL)
        request = post.call_args.kwargs
        self.assertEqual(request["timeout"], (10, 180))
        self.assertTrue(request["headers"]["Authorization"].endswith("hairstyle-test-key"))
        payload = request["data"]
        self.assertEqual(payload["model"], DEFAULT_IMAGE_MODEL)
        self.assertEqual(payload["size"], "1536x1024")
        self.assertEqual(payload["quality"], "medium")
        self.assertEqual(payload["output_format"], "jpeg")
        self.assertEqual(payload["input_fidelity"], "high")
        self.assertEqual(payload["n"], "1")
        self.assertIn("front view, side profile, and back-of-head view", payload["prompt"])
        self.assertIn("same person", payload["prompt"])
        self.assertIn(self.hairstyle.title, payload["prompt"])
        self.assertIn("without a haircut", payload["prompt"])
        filename, uploaded_photo, content_type = request["files"]["image"]
        self.assertEqual(filename, "hairstyle-reference.jpg")
        self.assertEqual(content_type, "image/jpeg")
        with Image.open(BytesIO(uploaded_photo)) as normalized:
            self.assertEqual(normalized.format, "JPEG")

    @patch("image_generator.requests.post")
    def test_salon_preview_uses_the_barber_order(self, post):
        post.return_value = self.make_success_response()

        generate_hairstyle_triptych(
            reference_photo=make_jpeg(),
            hairstyle=self.hairstyle,
            category="salon_cut",
            api_key="hairstyle-test-key",
        )

        prompt = post.call_args.kwargs["data"]["prompt"]
        self.assertIn("Show the cut described in the salon request", prompt)
        self.assertIn(self.hairstyle.salon_request, prompt)

    @patch("image_generator.requests.post")
    def test_gpt_image_2_omits_unsupported_input_fidelity(self, post):
        post.return_value = self.make_success_response()

        with patch.dict(os.environ, {"OPENAI_IMAGE_MODEL": "gpt-image-2"}):
            generate_hairstyle_triptych(
                reference_photo=make_jpeg(),
                hairstyle=self.hairstyle,
                category="current_hair",
            )

        payload = post.call_args.kwargs["data"]
        self.assertEqual(payload["model"], "gpt-image-2")
        self.assertNotIn("input_fidelity", payload)

    @patch("image_generator.requests.post")
    def test_gpt_image_1_mini_uses_supported_low_input_fidelity(self, post):
        post.return_value = self.make_success_response()

        with patch.dict(os.environ, {"OPENAI_IMAGE_MODEL": "gpt-image-1-mini"}):
            generate_hairstyle_triptych(
                reference_photo=make_jpeg(),
                hairstyle=self.hairstyle,
                category="current_hair",
            )

        self.assertEqual(post.call_args.kwargs["data"]["input_fidelity"], "low")

    def test_hairstyle_generation_requires_a_valid_key_and_photo(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ImageGenerationError, "OPENAI_API_KEY"):
                generate_hairstyle_triptych(
                    reference_photo=make_jpeg(),
                    hairstyle=self.hairstyle,
                    category="current_hair",
                )

        with self.assertRaisesRegex(ImageGenerationError, "自撮り写真"):
            generate_hairstyle_triptych(
                reference_photo=b"not an image",
                hairstyle=self.hairstyle,
                category="current_hair",
                api_key="hairstyle-test-key",
            )


if __name__ == "__main__":
    unittest.main()
