import base64
import json
import os
import re
from dataclasses import dataclass
from datetime import date

import requests

from photo_recommender import (
    DEFAULT_MODEL,
    OPENAI_CHAT_COMPLETIONS_URL,
    PhotoAnalysisError,
    normalize_photo_for_openai,
)


HAIRSTYLE_RECOMMENDATIONS_PER_CATEGORY = 5


class HairstyleAnalysisError(Exception):
    """Raised when a hairstyle analysis cannot be completed or parsed."""


@dataclass(frozen=True)
class HairstyleRecommendation:
    title: str
    suitability_reason: str
    styling: str
    salon_request: str
    maintenance: str


@dataclass(frozen=True)
class HairstyleAnalysis:
    face_shape_estimate: str
    visible_features: str
    trend_direction: str
    current_hair_recommendations: tuple[HairstyleRecommendation, ...]
    salon_cut_recommendations: tuple[HairstyleRecommendation, ...]


_RECOMMENDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "suitability_reason": {"type": "string"},
        "styling": {"type": "string"},
        "salon_request": {"type": "string"},
        "maintenance": {"type": "string"},
        "chemical_treatment": {"type": "string", "enum": ["なし"]},
    },
    "required": [
        "title",
        "suitability_reason",
        "styling",
        "salon_request",
        "maintenance",
        "chemical_treatment",
    ],
    "additionalProperties": False,
}

_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "face_shape_estimate": {"type": "string"},
        "visible_features": {"type": "string"},
        "trend_direction": {"type": "string"},
        "current_hair_recommendations": {
            "type": "array",
            "items": _RECOMMENDATION_SCHEMA,
        },
        "salon_cut_recommendations": {
            "type": "array",
            "items": _RECOMMENDATION_SCHEMA,
        },
    },
    "required": [
        "face_shape_estimate",
        "visible_features",
        "trend_direction",
        "current_hair_recommendations",
        "salon_cut_recommendations",
    ],
    "additionalProperties": False,
}

_CHEMICAL_TREATMENT_TERMS = re.compile(
    r"パーマ|perm|ヘアカラー|カラーリング|カラー|染め|ブリーチ|脱色|"
    r"ハイライト|バレイヤージュ|bleach|dye",
    re.IGNORECASE,
)
_NEGATED_CHEMICAL_TREATMENT_MENTION = re.compile(
    r"なし|不要|必要(?:は)?ありません|必要ない|"
    r"(?:し|入れ|かけ|あて|染め|施し|追加し|行い|使用し|使い|勧め|すすめ|推奨し)"
    r"(?:ない|なく|ません|ず|ずに)|"
    r"ではなく|ではない|避ける|避けて|せず|せぬ|ずに|ず|"
    r"そのまま|(?:を)?(?:活かす|活かし|生かす|生かし|維持する|維持し)|"
    r"変え(?:ない|ません|ず|ずに)|"
    r"風(?:の|に|な)?|っぽい|のように|のような|"
    r"\b(?:no|without|avoid|free|don't|do not)\b",
    re.IGNORECASE,
)


def _has_chemical_treatment_suggestion(text: str) -> bool:
    for match in _CHEMICAL_TREATMENT_TERMS.finditer(text):
        following_text = text[match.end():match.end() + 20]
        if not _NEGATED_CHEMICAL_TREATMENT_MENTION.search(following_text):
            return True
    return False


def _prompt(today: date) -> str:
    return (
        "あなたは日本の若者向けメンズヘアを提案するヘアスタイリストです。"
        "添付された1枚の自撮り写真から、髪の長さ・毛流れ・ボリュームと、写真で見える顔の輪郭を確認してください。"
        "写真から見える特徴だけを扱い、頭蓋骨や骨格を正確に診断したと断言しないでください。"
        "輪郭が見えにくい場合は顔型を「判定しにくい」とし、推測で補わないでください。"
        "顔の特徴は似合わせの参考としてのみ使い、人物の特定、年齢、性格、健康状態などを推測しないでください。"
        "提案は東京・表参道のような洗練された街のストリートムードを含む、現代的で若々しいメンズヘアにしてください。"
        "トレンド方向は今日の日付と現在の季節を踏まえたスタイリングの傾向として短く説明し、"
        "実測していない人気順位や流行の断定はしないでください。"
        f"今日の日付: {today.isoformat()}。"
        "current_hair_recommendationsには、今の長さと髪型を大きく変えず、ドライヤーやスタイリング剤など"
        "セット方法だけで再現できる案を必ず5案作ってください。カットが必要な案は含めないでください。"
        "salon_cut_recommendationsには、美容室でカットして実現する案を必ず5案作ってください。"
        "10案はタイトルとシルエットが重複しないようにしてください。"
        "どちらのカテゴリも、各案に似合う理由、具体的なセット方法、維持のしやすさを書いてください。"
        "salon_requestには美容師にそのまま伝えられる長さ・前髪・サイド・襟足のオーダーを簡潔に書いてください。"
        "現在の髪型でセットする案のsalon_requestには「カットせず、今の長さのまま」と書いてください。"
        "パーマ、カラー、染髪、ブリーチ、ハイライトなど薬剤を使う施術は一切提案しないでください。"
        "そのような施術名を各案の説明に書かず、全案のchemical_treatmentは必ず「なし」にしてください。"
        "提案は実際にセットまたはカットで再現できる内容にし、過度な加工や非現実的な髪型にしないでください。"
        "回答は指定JSONスキーマに厳密に従い、日本語で記述してください。"
    )


def _parse_recommendations(value: object) -> tuple[HairstyleRecommendation, ...]:
    if not isinstance(value, list) or len(value) != HAIRSTYLE_RECOMMENDATIONS_PER_CATEGORY:
        raise HairstyleAnalysisError(
            "髪型の提案を各カテゴリ5案ずつ生成できませんでした。再度お試しください。"
        )

    fields = (
        "title",
        "suitability_reason",
        "styling",
        "salon_request",
        "maintenance",
    )
    recommendations = []
    for recommendation in value:
        if not isinstance(recommendation, dict):
            raise HairstyleAnalysisError("髪型の提案データが不正です。再度お試しください。")
        if any(
            not isinstance(recommendation.get(field), str)
            or not recommendation[field].strip()
            for field in fields
        ):
            raise HairstyleAnalysisError("髪型の説明が不完全です。再度お試しください。")
        if recommendation.get("chemical_treatment") != "なし":
            raise HairstyleAnalysisError(
                "薬剤を使わない髪型の提案を生成できませんでした。再度お試しください。"
            )

        if any(
            _has_chemical_treatment_suggestion(recommendation[field])
            for field in fields
        ):
            raise HairstyleAnalysisError(
                "薬剤施術を勧める内容が返されました。薬剤施術を避けた内容で再度お試しください。"
            )

        recommendations.append(
            HairstyleRecommendation(
                title=recommendation["title"].strip(),
                suitability_reason=recommendation["suitability_reason"].strip(),
                styling=recommendation["styling"].strip(),
                salon_request=recommendation["salon_request"].strip(),
                maintenance=recommendation["maintenance"].strip(),
            )
        )
    return tuple(recommendations)


def _parse_analysis(content: str) -> HairstyleAnalysis:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise HairstyleAnalysisError(
            "髪型の解析結果を読み取れませんでした。再度お試しください。"
        ) from error

    if not isinstance(payload, dict):
        raise HairstyleAnalysisError("髪型の解析サービスから不正なデータが返されました。")
    summary_fields = ("face_shape_estimate", "visible_features", "trend_direction")
    if any(
        not isinstance(payload.get(field), str) or not payload[field].strip()
        for field in summary_fields
    ):
        raise HairstyleAnalysisError("髪型の解析結果が不完全です。再度お試しください。")

    current_hair = _parse_recommendations(payload.get("current_hair_recommendations"))
    salon_cuts = _parse_recommendations(payload.get("salon_cut_recommendations"))
    titles = [
        recommendation.title.casefold()
        for recommendation in (*current_hair, *salon_cuts)
    ]
    if len(set(titles)) != len(titles):
        raise HairstyleAnalysisError(
            "似た髪型の提案が重複しました。別の案を作るため再度お試しください。"
        )

    return HairstyleAnalysis(
        face_shape_estimate=payload["face_shape_estimate"].strip(),
        visible_features=payload["visible_features"].strip(),
        trend_direction=payload["trend_direction"].strip(),
        current_hair_recommendations=current_hair,
        salon_cut_recommendations=salon_cuts,
    )


def recommend_hairstyles(
    image_bytes: bytes,
    api_key: str | None = None,
    today: date | None = None,
) -> HairstyleAnalysis:
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HairstyleAnalysisError(
            "OPENAI_API_KEYが設定されていません。環境変数にAPIキーを設定してください。"
        )

    try:
        normalized_image = normalize_photo_for_openai(image_bytes)
    except PhotoAnalysisError as error:
        raise HairstyleAnalysisError(str(error)) from error

    image_url = (
        "data:image/jpeg;base64,"
        + base64.b64encode(normalized_image).decode("ascii")
    )
    payload = {
        "model": os.environ.get("OPENAI_VISION_MODEL", DEFAULT_MODEL),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _prompt(today or date.today())},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "high"},
                    },
                ],
            }
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "mens_hairstyle_recommendations",
                "strict": True,
                "schema": _ANALYSIS_SCHEMA,
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
        raise HairstyleAnalysisError(
            "OpenAIに接続できませんでした。通信環境を確認してください。"
        ) from error

    if not response.ok:
        try:
            error_payload = response.json()
            api_message = error_payload.get("error", {}).get("message", "")
        except (requests.JSONDecodeError, AttributeError, TypeError):
            api_message = ""
        message = api_message or f"HTTP {response.status_code}"
        raise HairstyleAnalysisError(f"髪型の画像解析に失敗しました: {message}")

    try:
        response_payload = response.json()
        choices = response_payload["choices"]
        if not isinstance(choices, list) or not choices:
            raise HairstyleAnalysisError("OpenAIから不完全な応答が返されました。")
        choice = choices[0].get("message")
        if not isinstance(choice, dict):
            raise HairstyleAnalysisError("OpenAIから不完全な応答が返されました。")
        if choice.get("refusal"):
            raise HairstyleAnalysisError(
                f"写真を解析できませんでした: {choice['refusal']}"
            )
        content = choice["content"]
    except HairstyleAnalysisError:
        raise
    except (
        requests.JSONDecodeError,
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
    ) as error:
        raise HairstyleAnalysisError("OpenAIから不完全な応答が返されました。") from error

    if not isinstance(content, str):
        raise HairstyleAnalysisError(
            "OpenAIからテキスト形式の髪型解析結果が返されませんでした。"
        )
    return _parse_analysis(content)
