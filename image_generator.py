import base64
import binascii
import os
from io import BytesIO

import requests
from PIL import Image, UnidentifiedImageError

from photo_recommender import OutfitRecommendation


OPENAI_IMAGE_GENERATION_URL = "https://api.openai.com/v1/images/generations"
DEFAULT_IMAGE_MODEL = "gpt-image-1"
MAX_GENERATED_IMAGE_PIXELS = 20_000_000


class ImageGenerationError(Exception):
    """Raised when an outfit image cannot be generated or decoded."""


def _build_prompt(
    item_type: str,
    item_summary: str,
    audience: str,
    outfit: OutfitRecommendation,
) -> str:
    colors = "、".join(f"{name} ({hex_code})" for name, hex_code in outfit.colors)
    return (
        "Create one polished, photorealistic Japanese fashion editorial image. "
        "Show one adult model in a full-body view, wearing the complete outfit below. "
        "Keep the clothing clearly visible, with a natural pose and a clean, understated background. "
        "Use realistic garment proportions and layering. Do not add text, labels, logos, watermarks, "
        "collages, or extra people. "
        f"Styling audience: {audience}. Outfit title: {outfit.title}. Style: {outfit.style}. "
        f"Key item from the user's wardrobe photo: {item_type}, {item_summary}. "
        f"Top: {outfit.top}. Bottom: {outfit.bottom}. Outerwear: {outfit.outerwear}. "
        f"Shoes: {outfit.shoes}. Accessories: {outfit.accessory}. "
        f"Color palette: {colors}. "
        "The image is a visual interpretation of the outfit description, not a product photo."
    )


def generate_outfit_image(
    item_type: str,
    item_summary: str,
    audience: str,
    outfit: OutfitRecommendation,
    api_key: str | None = None,
) -> bytes:
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ImageGenerationError(
            "OPENAI_API_KEYが設定されていません。APIキーを入力してから再度お試しください。"
        )

    payload = {
        "model": os.environ.get("OPENAI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL),
        "prompt": _build_prompt(item_type, item_summary, audience, outfit),
        "size": "1024x1536",
        "quality": "medium",
        "output_format": "jpeg",
        "n": 1,
    }
    try:
        response = requests.post(
            OPENAI_IMAGE_GENERATION_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=(10, 120),
        )
    except requests.RequestException as error:
        raise ImageGenerationError(
            "画像生成サービスに接続できませんでした。通信環境を確認してください。"
        ) from error

    if not response.ok:
        try:
            error_payload = response.json()
            api_message = error_payload.get("error", {}).get("message", "")
        except (requests.JSONDecodeError, AttributeError, TypeError):
            api_message = ""
        message = api_message or f"HTTP {response.status_code}"
        raise ImageGenerationError(f"画像を生成できませんでした: {message}")

    try:
        response_payload = response.json()
        encoded_image = response_payload["data"][0]["b64_json"]
        if not isinstance(encoded_image, str):
            raise ImageGenerationError("画像生成サービスから不正な画像データが返されました。")
        image_bytes = base64.b64decode(encoded_image, validate=True)
        with Image.open(BytesIO(image_bytes)) as image:
            if image.width * image.height > MAX_GENERATED_IMAGE_PIXELS:
                raise ImageGenerationError("生成された画像の解像度が大きすぎます。")
            image.verify()
    except ImageGenerationError:
        raise
    except (
        requests.JSONDecodeError,
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        binascii.Error,
        UnidentifiedImageError,
        OSError,
    ) as error:
        raise ImageGenerationError(
            "画像生成サービスから有効な画像が返されませんでした。再度お試しください。"
        ) from error

    return image_bytes
