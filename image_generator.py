import base64
import binascii
import os
from io import BytesIO
from typing import Literal

import requests
from PIL import Image, UnidentifiedImageError

from hairstyle_recommender import HairstyleRecommendation
from outfit_engine import Outfit as RuleBasedOutfit
from photo_recommender import (
    OutfitRecommendation,
    PhotoAnalysisError,
    normalize_photo_for_openai,
)


OPENAI_IMAGE_GENERATION_URL = "https://api.openai.com/v1/images/generations"
OPENAI_IMAGE_EDIT_URL = "https://api.openai.com/v1/images/edits"
DEFAULT_IMAGE_MODEL = "gpt-image-1"
IMAGE_EDIT_INPUT_FIDELITY_BY_MODEL = {
    "gpt-image-1": "high",
    "gpt-image-1.5": "high",
    "gpt-image-1-mini": "low",
}
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
    if item_type or item_summary:
        style_instruction = (
            "Create one bold, photorealistic Japanese fashion editorial image inspired by "
            "Omotesando high-street style. "
        )
        item_context = (
            f"Key item from the user's wardrobe photo: {item_type}, {item_summary}. "
        )
    else:
        style_instruction = (
            "Create one polished, photorealistic Japanese fashion editorial image with a "
            "refined, clean silhouette inspired by Omotesando high-street style. "
        )
        item_context = (
            "No wardrobe photo was provided; style the complete outfit from the written "
            "description alone. "
        )
    inner_context = (
        f"Inner layer: {outfit.inner}. "
        "Show the inner layer at the neckline, cuffs, or hem as described. "
        if outfit.inner
        else ""
    )
    extra_item_context = (
        f"Optional add-on item: {outfit.extra_item}. "
        f"Reason to add it: {outfit.extra_item_reason}. "
        if outfit.extra_item
        else ""
    )
    return style_instruction + (
        "Show one adult model in a full-body view, wearing the complete outfit below. "
        "Keep the clothing clearly visible, with a natural pose and a clean, understated background. "
        "Use fashion-forward layering and realistic garment proportions. Do not add text, labels, logos, watermarks, "
        "collages, or extra people. "
        f"Styling audience: {audience}. Outfit title: {outfit.title}. Style: {outfit.style}. "
        f"Styling pattern: {outfit.pattern}. "
        f"{item_context}"
        f"{inner_context}"
        f"Top: {outfit.top}. "
        f"Bottom: {outfit.bottom}. Outerwear: {outfit.outerwear}. "
        f"Shoes: {outfit.shoes}. Accessories: {outfit.accessory}. "
        f"{extra_item_context}"
        f"Color palette: {colors}. "
        "The image is a visual interpretation of the outfit description, not a product photo."
    )


def _build_hairstyle_prompt(
    hairstyle: HairstyleRecommendation,
    category: Literal["current_hair", "salon_cut"],
) -> str:
    if category == "current_hair":
        category_instructions = (
            "Keep the person's current hair length and overall cut. "
            "Show only the recommended styling technique, without a haircut."
        )
    elif category == "salon_cut":
        category_instructions = (
            "Show the cut described in the salon request, keeping the person's identity "
            "and natural hair color."
        )
    else:
        raise ValueError(f"Unsupported hairstyle category: {category}")

    return (
        "Create one photorealistic men's hairstyle consultation image using the attached selfie "
        "as the visual reference. Show the same person in three equal vertical panels, arranged "
        "from left to right: front view, side profile, and back-of-head view. Keep the haircut, "
        "hairline, hair color, lighting, and background consistent across all three views. "
        "Preserve the recognizable facial identity, skin tone, and visible head proportions of "
        "the person in the reference as closely as possible; do not substitute another person. "
        "Frame each view from the shoulders up so the hairstyle is clear. Use a simple neutral "
        "background and realistic hair texture. Do not add text, labels, logos, watermarks, or "
        "other people. "
        f"{category_instructions} "
        f"Hairstyle: {hairstyle.title}. "
        f"Why it suits the person: {hairstyle.suitability_reason}. "
        f"Styling: {hairstyle.styling}. "
        f"Salon request: {hairstyle.salon_request}. "
        f"Maintenance: {hairstyle.maintenance}. "
        "Do not introduce a chemical hair treatment or change the person's hair color."
    )


def _decode_generated_image(response: requests.Response) -> bytes:
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


def generate_outfit_image(
    item_type: str | None,
    item_summary: str | None,
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

    return _decode_generated_image(response)


def generate_rule_based_outfit_image(
    audience: str,
    outfit: RuleBasedOutfit,
    api_key: str | None = None,
) -> bytes:
    photo_free_outfit = OutfitRecommendation(
        title=outfit.title,
        pattern=outfit.trend,
        style=outfit.style,
        colors=outfit.colors,
        inner="",
        top=outfit.top,
        bottom=outfit.bottom,
        outerwear=outfit.outerwear,
        shoes=outfit.shoes,
        accessory=outfit.accessory,
        extra_item="",
        extra_item_reason="",
        reason=outfit.reason,
    )
    return generate_outfit_image(
        item_type=None,
        item_summary=None,
        audience=audience,
        outfit=photo_free_outfit,
        api_key=api_key,
    )


def generate_hairstyle_triptych(
    reference_photo: bytes,
    hairstyle: HairstyleRecommendation,
    category: Literal["current_hair", "salon_cut"],
    api_key: str | None = None,
) -> bytes:
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ImageGenerationError(
            "OPENAI_API_KEYが設定されていません。APIキーを入力してから再度お試しください。"
        )

    try:
        normalized_photo = normalize_photo_for_openai(reference_photo)
    except PhotoAnalysisError as error:
        raise ImageGenerationError(f"自撮り写真を準備できませんでした: {error}") from error

    model = os.environ.get("OPENAI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)
    data = {
        "model": model,
        "prompt": _build_hairstyle_prompt(hairstyle, category),
        "size": "1536x1024",
        "quality": "medium",
        "output_format": "jpeg",
        "n": "1",
    }
    input_fidelity = IMAGE_EDIT_INPUT_FIDELITY_BY_MODEL.get(model)
    if input_fidelity is not None:
        data["input_fidelity"] = input_fidelity

    files = {"image": ("hairstyle-reference.jpg", normalized_photo, "image/jpeg")}
    try:
        response = requests.post(
            OPENAI_IMAGE_EDIT_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files=files,
            timeout=(10, 180),
        )
    except requests.RequestException as error:
        raise ImageGenerationError(
            "髪型イメージ画像の生成サービスに接続できませんでした。通信環境を確認してください。"
        ) from error

    return _decode_generated_image(response)
