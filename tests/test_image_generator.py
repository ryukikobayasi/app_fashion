import base64
import json
import os
import unittest
from io import BytesIO
from unittest.mock import Mock, patch

from PIL import Image

from image_generator import (
    DEFAULT_IMAGE_MODEL,
    ImageGenerationError,
    generate_outfit_image,
)
from photo_recommender import OutfitRecommendation


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
            style="きれいめストリート",
            colors=(
                ("ネイビー", "#243956"),
                ("アイボリー", "#F1EBDD"),
                ("レッド", "#B52D45"),
            ),
            top="写真のブルーシャツ",
            bottom="ワイドスラックス",
            outerwear="ショートコート",
            shoes="レザースニーカー",
            accessory="ミニショルダー",
            reason="ブルーシャツを主役にした着こなしです。",
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
        self.assertIn("ワイドスラックス", payload["prompt"])
        with Image.open(BytesIO(result)) as image:
            self.assertEqual(image.format, "JPEG")

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


if __name__ == "__main__":
    unittest.main()
