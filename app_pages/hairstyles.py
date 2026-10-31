import hashlib
import os
from typing import Literal

import streamlit as st

from camera_component import CameraCaptureError, capture_camera_photo, decode_camera_photo
from hairstyle_recommender import (
    HAIRSTYLE_RECOMMENDATIONS_PER_CATEGORY,
    HairstyleAnalysis,
    HairstyleAnalysisError,
    HairstyleRecommendation,
    recommend_hairstyles,
)
from image_generator import ImageGenerationError, generate_hairstyle_triptych


def _clear_hairstyle_results() -> None:
    for key in ("hairstyle_analysis", "hairstyle_analysis_digest", "hairstyle_previews"):
        st.session_state.pop(key, None)


def _render_recommendation(
    recommendation: HairstyleRecommendation,
    index: int,
    category: Literal["current_hair", "salon_cut"],
    photo: bytes,
    photo_digest: str,
    api_key: str,
) -> None:
    with st.container(border=True):
        st.badge(f"STYLE {index:02}", color="blue", icon=":material/content_cut:")
        st.subheader(recommendation.title)
        st.markdown(f"**似合わせの理由**　{recommendation.suitability_reason}")
        st.markdown(f"**セット方法**　{recommendation.styling}")
        if category == "salon_cut":
            st.markdown(f"**美容室でのオーダー**　{recommendation.salon_request}")
        else:
            st.caption("今の長さのまま、カットを前提にしないセット案です。")
        st.markdown(f"**維持のしやすさ**　{recommendation.maintenance}")

        image_key = f"{photo_digest}:{category}:{index}"
        if st.button(
            "本人写真で前・横・後ろのイメージを生成",
            key=f"generate_hairstyle_{category}_{index}",
            icon=":material/image:",
        ):
            if not api_key:
                st.error("OpenAI APIキーを設定してから再度お試しください。")
            else:
                try:
                    with st.spinner("本人写真を参考に、3方向の髪型イメージを生成しています..."):
                        image = generate_hairstyle_triptych(
                            reference_photo=photo,
                            hairstyle=recommendation,
                            category=category,
                            api_key=api_key,
                        )
                    previews = st.session_state.get("hairstyle_previews", {})
                    previews[image_key] = image
                    st.session_state["hairstyle_previews"] = previews
                except ImageGenerationError as error:
                    st.error(f"髪型イメージを作成できませんでした。{error}")

        generated_image = st.session_state.get("hairstyle_previews", {}).get(image_key)
        if generated_image:
            st.image(
                generated_image,
                caption=f"{recommendation.title} · 左から前・横・後ろ",
                alt=f"{recommendation.title}を本人写真を参考に前・横・後ろから描いたAIイメージ",
                width="stretch",
            )


with st.sidebar:
    st.title("メンズ髪型診断", anchor=False)
    st.caption("自撮り写真から、セット案と美容室でのカット案を提案します。")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        st.caption("OpenAI APIキーはサーバー設定から読み込みます。")
    else:
        api_key = st.text_input(
            "OpenAI APIキー",
            type="password",
            placeholder="sk-...",
            help="入力したキーはこのセッション中だけ利用し、ファイルには保存しません。",
            autocomplete="off",
            key="hairstyle_openai_api_key",
        ).strip()

st.title("自分に似合う、次の髪型。", icon=":material/face:")
st.caption("MEN'S HAIR / 写真から見える輪郭と髪の特徴を参考に、トレンド感のある10案を提案")
st.info(
    "写真から見える輪郭・髪の特徴による目安です。2D写真だけで頭や骨格を正確に診断するものではありません。"
)
st.caption("トレンドの方向性はAIの一般知識に基づく提案で、リアルタイム検索や人気ランキングではありません。")
st.caption(
    "写真は診断時にOpenAIの画像解析APIへ送信されます。写真をファイルには保存せず、セッション中だけ保持します。"
    "本人写真を使う画像生成は各案のボタンを押した時だけ実行され、生成ごとにAPI利用料が発生する場合があります。"
)

camera_generation = st.session_state.setdefault("hairstyle_camera_generation", 0)
camera_key = f"hairstyle_selfie_{camera_generation}"
if st.session_state.get("hairstyle_photo"):
    if st.button(
        "自撮り写真と診断結果を削除",
        key="clear_hairstyle_photo",
        icon=":material/delete:",
    ):
        st.session_state.pop(camera_key, None)
        st.session_state.pop("hairstyle_photo", None)
        _clear_hairstyle_results()
        st.session_state["hairstyle_camera_generation"] = camera_generation + 1
        st.rerun()

st.subheader("自撮り写真を撮影")
st.caption("前面カメラから起動します。顔と髪全体が明るく見えるように正面から撮影してください。")
camera_result = capture_camera_photo(
    reset_token=camera_generation,
    key=camera_key,
    initial_facing_mode="user",
)
if camera_result.photo_added is not None:
    try:
        captured_photo = decode_camera_photo(camera_result.photo_added)
    except CameraCaptureError as error:
        st.error(str(error))
    else:
        st.session_state.pop(camera_key, None)
        st.session_state["hairstyle_photo"] = captured_photo
        _clear_hairstyle_results()
        st.session_state["hairstyle_camera_generation"] = camera_generation + 1
        st.rerun()

photo: bytes | None = st.session_state.get("hairstyle_photo")
photo_digest = hashlib.sha256(photo).hexdigest() if photo else ""
if photo:
    st.image(
        photo,
        caption="現在の自撮り写真（セッション中のみ保持）",
        alt="髪型診断に使う自撮り写真",
        width="stretch",
    )
else:
    st.info("撮影後、「撮影した写真を追加」を押して自撮り写真を確定してください。")

if st.button(
    "この写真で髪型を10案診断",
    type="primary",
    icon=":material/auto_awesome:",
    disabled=photo is None,
):
    if photo is None:
        st.error("先に自撮り写真を撮影してください。")
    elif not api_key:
        st.error(
            "OPENAI_API_KEYが設定されていません。"
            "左側の「OpenAI APIキー」に入力するか、環境変数に設定してください。"
        )
    else:
        try:
            with st.spinner("写真を分析し、セット案5つと美容室のカット案5つを考えています..."):
                analysis = recommend_hairstyles(photo, api_key=api_key)
            st.session_state["hairstyle_analysis"] = analysis
            st.session_state["hairstyle_analysis_digest"] = photo_digest
            st.session_state.pop("hairstyle_previews", None)
        except HairstyleAnalysisError as error:
            st.error(f"髪型を診断できませんでした。{error}")

analysis: HairstyleAnalysis | None = st.session_state.get("hairstyle_analysis")
if analysis and photo and st.session_state.get("hairstyle_analysis_digest") == photo_digest:
    st.subheader("写真から見える特徴")
    st.markdown(f"**顔型の目安**　{analysis.face_shape_estimate}")
    st.markdown(f"**髪・輪郭の見え方**　{analysis.visible_features}")
    st.markdown(f"**トレンドの方向性**　{analysis.trend_direction}")
    st.caption(
        "各案のイメージ生成は選択式です。生成画像は3方向を1枚にまとめ、本人らしさの再現は保証されません。"
    )
    current_tab, salon_tab = st.tabs(
        [
            f"今の髪型でセット（{HAIRSTYLE_RECOMMENDATIONS_PER_CATEGORY}案）",
            f"美容室でカット（{HAIRSTYLE_RECOMMENDATIONS_PER_CATEGORY}案）",
        ]
    )
    with current_tab:
        for index, recommendation in enumerate(
            analysis.current_hair_recommendations,
            start=1,
        ):
            _render_recommendation(
                recommendation,
                index,
                "current_hair",
                photo,
                photo_digest,
                api_key,
            )
    with salon_tab:
        for index, recommendation in enumerate(
            analysis.salon_cut_recommendations,
            start=1,
        ):
            _render_recommendation(
                recommendation,
                index,
                "salon_cut",
                photo,
                photo_digest,
                api_key,
            )
