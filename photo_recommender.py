import base64
import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from io import BytesIO

import requests
from PIL import Image, ImageOps, UnidentifiedImageError


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4.1-mini"
RECOMMENDATION_STYLE = "表参道きれいめカジュアル"
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_PHOTO_COUNT = 8
MAX_TOTAL_IMAGE_BYTES = 60 * 1024 * 1024
MAX_IMAGE_PIXELS = 250_000_000
MAX_IMAGE_PIXELS_WITHOUT_JPEG_DOWNSAMPLING = 80_000_000
MAX_IMAGE_SIDE = 1280
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class PhotoAnalysisError(Exception):
    """Raised when a photo cannot be safely analyzed or parsed."""


@dataclass(frozen=True)
class OutfitRecommendation:
    title: str
    pattern: str
    style: str
    colors: tuple[tuple[str, str], ...]
    inner: str
    top: str
    bottom: str
    outerwear: str
    shoes: str
    accessory: str
    extra_item: str
    extra_item_reason: str
    reason: str


@dataclass(frozen=True)
class PhotoAnalysis:
    garment_found: bool
    item_type: str
    item_summary: str
    colors: tuple[str, ...]
    outfits: tuple[OutfitRecommendation, ...]


_LOOK_PATTERNS = (
    "オーバーサイズ×Iライン",
    "シアーインナー×レイヤード",
    "ショート丈×ロング丈",
    "ワントーン×異素材",
    "トラッド×エッジィ",
    "テック×モード",
    "テーラード崩し",
    "小物主役の大胆バランス",
)
_COLOR_ROLES = ("base", "secondary", "accent")
_COLOR_ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "hex": {"type": "string"},
    },
    "required": ["name", "hex"],
    "additionalProperties": False,
}

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
                        "type": "object",
                        "properties": {role: _COLOR_ENTRY_SCHEMA for role in _COLOR_ROLES},
                        "required": list(_COLOR_ROLES),
                        "additionalProperties": False,
                    },
                    "inner": {"type": "string"},
                    "top": {"type": "string"},
                    "bottom": {"type": "string"},
                    "outerwear": {"type": "string"},
                    "shoes": {"type": "string"},
                    "accessory": {"type": "string"},
                    "extra_item": {"type": "string"},
                    "extra_item_reason": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "title",
                    "style",
                    "colors",
                    "inner",
                    "top",
                    "bottom",
                    "outerwear",
                    "shoes",
                    "accessory",
                    "extra_item",
                    "extra_item_reason",
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


def normalize_photo_for_openai(image_bytes: bytes) -> bytes:
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

    return output.getvalue()


def _prepare_photo(image_bytes: bytes) -> str:
    encoded = base64.b64encode(normalize_photo_for_openai(image_bytes)).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _prepare_photos(image_bytes: bytes | Sequence[bytes]) -> tuple[str, ...]:
    if isinstance(image_bytes, bytes):
        photos = (image_bytes,)
    elif isinstance(image_bytes, Sequence) and not isinstance(image_bytes, (str, bytearray)):
        photos = tuple(image_bytes)
    else:
        raise PhotoAnalysisError("写真を選択してください。")

    if not photos:
        raise PhotoAnalysisError("写真を1枚以上選択してください。")
    if len(photos) > MAX_PHOTO_COUNT:
        raise PhotoAnalysisError(f"写真は最大{MAX_PHOTO_COUNT}枚まで選択できます。")
    if not all(isinstance(photo, bytes) for photo in photos):
        raise PhotoAnalysisError("写真データを読み取れませんでした。選び直してください。")
    if sum(len(photo) for photo in photos) > MAX_TOTAL_IMAGE_BYTES:
        raise PhotoAnalysisError("写真の合計サイズは60MB以下にしてください。")

    data_urls = []
    for index, photo in enumerate(photos, start=1):
        try:
            data_urls.append(_prepare_photo(photo))
        except PhotoAnalysisError as error:
            raise PhotoAnalysisError(f"{index}枚目の写真を処理できませんでした。{error}") from error
    return tuple(data_urls)


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
    pattern_guidance = "、".join(
        f"{index + 1}案目「{pattern}」"
        for index, pattern in enumerate(_LOOK_PATTERNS)
    )

    return (
        "あなたは若者向けの日本語ファッションスタイリストです。"
        "添付されたすべての写真をまとめて読み取り、写真ごとに写っている衣類・服飾アイテムを"
        "一つの手持ちワードローブとして整理してください。"
        "同じアイテムが複数の写真に写っている場合は重複して数えないでください。"
        "写真から確認できるアイテムを組み合わせ、各コーデに少なくとも1点使ってください。"
        "8案全体を通じて写真の手持ちアイテムを幅広く活用し、表参道のきれいめカジュアルを土台にしてください。"
        "上質なベーシックを軸に、ファッション誌の特集のようにシルエット・丈感・素材・レイヤードを"
        "やりすぎなくらい大胆に遊び、ひと目でおしゃれとわかるファッションスナップにしてください。"
        "ただしコスチュームではなく、街で実際に着られる服として成立させてください。"
        "写真に人物が写っていても体型・年齢・性別を推測せず、服とアイテムだけを見てください。"
        "見えないブランド、素材、色、ロゴを断定しないでください。"
        "どの写真にも衣類や服飾アイテムが判別できない場合は garment_found=false、outfits=[] としてください。"
        "判別できる場合は、写真に写ったアイテムを使った異なる着こなしを必ず8案作ってください。"
        f"8案すべてを{preferred_style}に統一し、各style欄は正確に「{preferred_style}」としてください。"
        "色、シルエット、トップス・ボトムス・羽織りの組み合わせを変えて、各案に違いを出してください。"
        f"8案は次の着こなしパターンを番号順に1案ずつ提案してください: {pattern_guidance}。"
        "各案で主役にする写真アイテムをできるだけ入れ替え、同じトップス・ボトムス・羽織りの組み合わせを繰り返さないでください。"
        "丈感、シルエット、レイヤード、タックイン、素材感を変えて、8案の見た目がはっきり異なるようにしてください。"
        "各案のinner欄には、肌着ではなく見せるためのファッションインナーを具体的に1点必ず入れてください。"
        "薄手タートル、シアートップス、タンクトップ、シャツなどを使い、トップスとの重ね方と"
        "首元・袖口・裾のどこから見せるかをinner欄に記述してください。"
        "インナーが写真にない場合は写真外の追加候補だと明記し、手持ちにあると決めつけないでください。"
        "accessory欄とshoes欄は各コーデに合うものを自由に選び、特定のブランドや商品を指定しないでください。"
        "天気欄が前年同月の平均気温なら、今日の実況・予報ではない季節参考値として扱ってください。"
        "前年同月の平均気温を参考に、気温に合う素材や羽織りで季節感を整えてください。"
        "降水・風・湿度が不明な場合、それらを推測して服装に反映しないでください。"
        "写真に写ったアイテムを別の商品に置き換えないでください。"
        "extra_itemにはinnerと重複しない、写真に写っていないファッションアイテムを各案1点だけ"
        "プラスワン候補として提案してください。"
        "8案で同じ追加アイテムを繰り返さず、ベルト、バッグ、帽子、スカーフ、ソックスなどからコーデに合う種類を選んでください。"
        "extra_item_reasonには、そのアイテムを加えるとコーデがどうおしゃれになるかを簡潔に説明し、手持ちにあると決めつけないでください。"
        "性別・着こなし区分: "
        f"{audience}。好きなテイスト: {preferred_style}。配色方針: {palette}"
        f" 今日の日付: {today.isoformat()}。天気: {weather}。"
        f"今季の海外トレンドテーマ: {seasonal_context}。"
        "各コーデのcolorsはbase・secondary・accentの3項目を持つオブジェクトにしてください。"
        "各項目には日本語の色名nameと、#から始まる6桁のHEX値hexを必ず入れてください。"
        "reasonには、写真のアイテムが他の服や配色とどう合うかを簡潔に書いてください。"
        "回答は指定JSONスキーマに厳密に従い、日本語で記述してください。"
    )


def _parse_analysis(
    content: str,
    preferred_style: str = RECOMMENDATION_STYLE,
) -> PhotoAnalysis:
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
        or not all(isinstance(color, str) for color in item_colors)
        or not isinstance(outfits_data, list)
    ):
        raise PhotoAnalysisError("画像解析サービスから不正なデータが返されました。")

    if not garment_found:
        return PhotoAnalysis(False, item_type, item_summary, tuple(item_colors), ())
    if len(outfits_data) != 8:
        raise PhotoAnalysisError("8案のコーディネートを生成できませんでした。再度お試しください。")

    outfits = []
    for index, outfit in enumerate(outfits_data):
        if not isinstance(outfit, dict):
            raise PhotoAnalysisError("画像解析サービスから不正なコーディネートが返されました。")
        colors = outfit.get("colors")
        if not isinstance(colors, dict) or set(colors) != set(_COLOR_ROLES):
            raise PhotoAnalysisError("コーディネートの配色データが不完全です。再度お試しください。")

        parsed_colors = []
        for role in _COLOR_ROLES:
            color = colors[role]
            if (
                not isinstance(color, dict)
                or not isinstance(color.get("name"), str)
                or not isinstance(color.get("hex"), str)
                or re.fullmatch(r"#[0-9A-Fa-f]{6}", color["hex"]) is None
            ):
                raise PhotoAnalysisError("コーディネートの色データが不正です。")
            parsed_colors.append((color["name"], color["hex"]))

        text_fields = (
            "title",
            "style",
            "inner",
            "top",
            "bottom",
            "outerwear",
            "shoes",
            "accessory",
            "extra_item",
            "extra_item_reason",
            "reason",
        )
        if not all(isinstance(outfit.get(field), str) for field in text_fields):
            raise PhotoAnalysisError("コーディネートの説明が不完全です。再度お試しください。")
        if not outfit["inner"].strip():
            raise PhotoAnalysisError("コーディネートのインナーが不完全です。再度お試しください。")
        if not outfit["extra_item"].strip() or not outfit["extra_item_reason"].strip():
            raise PhotoAnalysisError("プラスワンアイテムの説明が不完全です。再度お試しください。")
        outfits.append(
            OutfitRecommendation(
                title=outfit["title"],
                pattern=_LOOK_PATTERNS[index],
                style=outfit["style"],
                colors=tuple(parsed_colors),
                inner=outfit["inner"],
                top=outfit["top"],
                bottom=outfit["bottom"],
                outerwear=outfit["outerwear"],
                shoes=outfit["shoes"],
                accessory=outfit["accessory"],
                extra_item=outfit["extra_item"],
                extra_item_reason=outfit["extra_item_reason"],
                reason=outfit["reason"],
            )
        )
    if any(outfit.style != preferred_style for outfit in outfits):
        raise PhotoAnalysisError(
            f"全案を{preferred_style}に統一できませんでした。再度お試しください。"
        )
    return PhotoAnalysis(True, item_type, item_summary, tuple(item_colors), tuple(outfits))


def recommend_from_photo(
    image_bytes: bytes | Sequence[bytes],
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

    image_urls = _prepare_photos(image_bytes)
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
                    }
                ]
                + [
                    {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}}
                    for image_url in image_urls
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
        "max_completion_tokens": 5500,
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
    return _parse_analysis(content, preferred_style)
