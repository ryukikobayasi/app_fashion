import base64
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO

import requests
from PIL import Image, ImageOps, UnidentifiedImageError


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4.1-mini"
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_IMAGE_PIXELS = 250_000_000
MAX_IMAGE_PIXELS_WITHOUT_JPEG_DOWNSAMPLING = 80_000_000
MAX_IMAGE_SIDE = 1280
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class PhotoAnalysisError(Exception):
    """Raised when a photo cannot be safely analyzed or parsed."""


@dataclass(frozen=True)
class OutfitRecommendation:
    title: str
    style: str
    colors: tuple[tuple[str, str], ...]
    top: str
    bottom: str
    outerwear: str
    shoes: str
    accessory: str
    reason: str


@dataclass(frozen=True)
class PhotoAnalysis:
    garment_found: bool
    item_type: str
    item_summary: str
    colors: tuple[str, ...]
    outfits: tuple[OutfitRecommendation, ...]


_OUTFIT_SCHEMA = {
    "type": "object",
    "properties": {
        "garment_found": {"type": "boolean"},
        "item_type": {"type": "string"},
        "item_summary": {"type": "string"},
        "colors": {
            "type": "array",
            "items": {"type": "string"},
        },
        "outfits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "style": {"type": "string"},
                    "colors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "hex": {"type": "string"},
                            },
                            "required": ["name", "hex"],
                            "additionalProperties": False,
                        },
                    },
                    "top": {"type": "string"},
                    "bottom": {"type": "string"},
                    "outerwear": {"type": "string"},
                    "shoes": {"type": "string"},
                    "accessory": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "title",
                    "style",
                    "colors",
                    "top",
                    "bottom",
                    "outerwear",
                    "shoes",
                    "accessory",
                    "reason",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["garment_found", "item_type", "item_summary", "colors", "outfits"],
    "additionalProperties": False,
}

_PALETTE_GUIDANCE = {
    "おまかせ": "アイテムに自然に合う、今季らしい配色を選ぶ。",
    "赤×ブルー": "赤とブルーを使い、どちらかを差し色にしてまとめる。",
    "モノトーン": "黒・白・グレーのみを使い、明度や素材感に変化をつける。",
    "アースカラー": "オリーブ、ブラウン、ベージュなど自然な色を中心にする。",
    "ニュートラル": "アイボリー、グレージュ、グレーなど穏やかな色を中心にする。",
}


def _prepare_photo(image_bytes: bytes) -> str:
    if not image_bytes:
        raise PhotoAnalysisError("写真ファイルが空です。別の画像を選んでください。")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise PhotoAnalysisError("写真は30MB以下にしてください。")

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            width, height = image.size
            source_pixels = width * height
            if source_pixels > MAX_IMAGE_PIXELS:
                raise PhotoAnalysisError("画像の解像度が大きすぎます。小さい画像を選んでください。")

            if image.format == "JPEG":
                image.draft("RGB", (MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            elif source_pixels > MAX_IMAGE_PIXELS_WITHOUT_JPEG_DOWNSAMPLING:
                raise PhotoAnalysisError(
                    "PNGやWebPは80MP以下の画像を選んでください。JPEGなら高解像度画像も利用できます。"
                )

            image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
            normalized = ImageOps.exif_transpose(image).convert("RGB")
            output = BytesIO()
            normalized.save(output, format="JPEG", quality=85, optimize=True)
    except PhotoAnalysisError:
        raise
    except Image.DecompressionBombError as error:
        raise PhotoAnalysisError("画像の解像度が大きすぎます。小さい画像を選んでください。") from error
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise PhotoAnalysisError(
            "画像を読み込めませんでした。JPEG、PNG、WebP形式の写真を選んでください。"
        ) from error

    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _prompt(
    audience: str,
    preferred_style: str,
    preferred_palette: str,
    today: date,
    weather_context: str | None,
    seasonal_context: str,
) -> str:
    weather = weather_context or "天気データは未指定。季節に合う一般的な重ね着を提案する。"
    palette = _PALETTE_GUIDANCE.get(preferred_palette)
    if palette is None:
        raise ValueError(f"対応していない配色です: {preferred_palette}")

    return (
        "あなたは若者向けの日本語ファッションスタイリストです。"
        "添付写真に実際に写っている手持ち衣類・服飾アイテムを主役として読み取り、"
        "そのアイテムを必ず使う、現実的でおしゃれなコーディネートを提案してください。"
        "写真に人物が写っていても体型・年齢・性別を推測せず、服とアイテムだけを見てください。"
        "見えないブランド、素材、色、ロゴを断定しないでください。"
        "衣類が判別できない写真では garment_found=false、outfits=[] としてください。"
        "判別できる場合は、主役アイテムをそれぞれ異なる着こなしにした5案を必ず作ってください。"
        "5案は色、シルエット、テイストが互いに似すぎないようにし、"
        "写真のアイテムを別の商品に置き換えないでください。"
        "性別・着こなし区分: "
        f"{audience}。好きなテイスト: {preferred_style}。配色方針: {palette}"
        f" 今日の日付: {today.isoformat()}。天気: {weather}。"
        f"今季の海外トレンドテーマ: {seasonal_context}。"
        "色は日本語名と、対応するHEXカラーを3色出してください。"
        "reasonには、写真のアイテムが他の服や配色とどう合うかを簡潔に書いてください。"
        "回答は指定JSONスキーマに厳密に従い、日本語で記述してください。"
    )


def _parse_analysis(content: str) -> PhotoAnalysis:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise PhotoAnalysisError("画像解析結果を読み取れませんでした。再度お試しください。") from error

    if not isinstance(payload, dict):
        raise PhotoAnalysisError("画像解析サービスから不正なデータが返されました。")
    garment_found = payload.get("garment_found")
    item_type = payload.get("item_type")
    item_summary = payload.get("item_summary")
    item_colors = payload.get("colors")
    outfits_data = payload.get("outfits")
    if (
        not isinstance(garment_found, bool)
        or not isinstance(item_type, str)
        or not isinstance(item_summary, str)
        or not isinstance(item_colors, list)
        or len(item_colors) > 4
        or not all(isinstance(color, str) for color in item_colors)
        or not isinstance(outfits_data, list)
    ):
        raise PhotoAnalysisError("画像解析サービスから不正なデータが返されました。")

    if not garment_found:
        return PhotoAnalysis(False, item_type, item_summary, tuple(item_colors), ())
    if len(outfits_data) != 5:
        raise PhotoAnalysisError("5案のコーディネートを生成できませんでした。再度お試しください。")

    outfits = []
    for outfit in outfits_data:
        if not isinstance(outfit, dict):
            raise PhotoAnalysisError("画像解析サービスから不正なコーディネートが返されました。")
        colors = outfit.get("colors")
        if not isinstance(colors, list) or len(colors) != 3:
            raise PhotoAnalysisError("コーディネートの配色データが不完全です。再度お試しください。")

        parsed_colors = []
        for color in colors:
            if (
                not isinstance(color, dict)
                or not isinstance(color.get("name"), str)
                or not isinstance(color.get("hex"), str)
                or re.fullmatch(r"#[0-9A-Fa-f]{6}", color["hex"]) is None
            ):
                raise PhotoAnalysisError("コーディネートの色データが不正です。")
            parsed_colors.append((color["name"], color["hex"]))

        text_fields = ("title", "style", "top", "bottom", "outerwear", "shoes", "accessory", "reason")
        if not all(isinstance(outfit.get(field), str) for field in text_fields):
            raise PhotoAnalysisError("コーディネートの説明が不完全です。再度お試しください。")
        outfits.append(
            OutfitRecommendation(
                title=outfit["title"],
                style=outfit["style"],
                colors=tuple(parsed_colors),
                top=outfit["top"],
                bottom=outfit["bottom"],
                outerwear=outfit["outerwear"],
                shoes=outfit["shoes"],
                accessory=outfit["accessory"],
                reason=outfit["reason"],
            )
        )
    return PhotoAnalysis(True, item_type, item_summary, tuple(item_colors), tuple(outfits))


def recommend_from_photo(
    image_bytes: bytes,
    audience: str,
    preferred_style: str,
    preferred_palette: str,
    today: date,
    weather_context: str | None,
    seasonal_context: str,
    api_key: str | None = None,
) -> PhotoAnalysis:
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise PhotoAnalysisError(
            "OPENAI_API_KEYが設定されていません。環境変数にAPIキーを設定してください。"
        )

    image_url = _prepare_photo(image_bytes)
    model = os.environ.get("OPENAI_VISION_MODEL", DEFAULT_MODEL)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": _prompt(
                            audience,
                            preferred_style,
                            preferred_palette,
                            today,
                            weather_context,
                            seasonal_context,
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}},
                ],
            }
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "wardrobe_outfit_recommendations",
                "strict": True,
                "schema": _OUTFIT_SCHEMA,
            },
        },
        "max_completion_tokens": 3500,
    }

    try:
        response = requests.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=(10, 90),
        )
    except requests.RequestException as error:
        raise PhotoAnalysisError("OpenAIに接続できませんでした。通信環境を確認してください。") from error

    if not response.ok:
        try:
            error_payload = response.json()
            api_message = error_payload.get("error", {}).get("message", "")
        except (requests.JSONDecodeError, AttributeError):
            api_message = ""
        message = api_message or f"HTTP {response.status_code}"
        raise PhotoAnalysisError(f"画像解析に失敗しました: {message}")

    try:
        response_payload = response.json()
        choices = response_payload["choices"]
        if not isinstance(choices, list) or not choices:
            raise PhotoAnalysisError("OpenAIから不完全な応答が返されました。")
        choice = choices[0].get("message")
        if not isinstance(choice, dict):
            raise PhotoAnalysisError("OpenAIから不完全な応答が返されました。")
        if choice.get("refusal"):
            raise PhotoAnalysisError(f"画像を解析できませんでした: {choice['refusal']}")
        content = choice["content"]
    except PhotoAnalysisError:
        raise
    except (requests.JSONDecodeError, AttributeError, IndexError, KeyError, TypeError) as error:
        raise PhotoAnalysisError("OpenAIから不完全な応答が返されました。") from error

    if not isinstance(content, str):
        raise PhotoAnalysisError("OpenAIからテキスト形式の解析結果が返されませんでした。")
    return _parse_analysis(content)
