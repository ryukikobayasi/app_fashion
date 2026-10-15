import hashlib
from datetime import datetime, timedelta, timezone
from html import escape
import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

from outfit_engine import TREND_AS_OF, TREND_SOURCES, seasonal_trends
from image_generator import ImageGenerationError, generate_outfit_image
from photo_recommender import (
    MAX_IMAGE_BYTES,
    OutfitRecommendation,
    PhotoAnalysis,
    PhotoAnalysisError,
    recommend_from_photo,
)
from weather import CITIES, WeatherDataError, WeatherRateLimitError, get_weather


JST = timezone(timedelta(hours=9))
WEEKDAYS = ("月", "火", "水", "木", "金", "土", "日")

st.set_page_config(
    page_title="FITTING | 手持ち服からコーデ提案",
    page_icon=":material/checkroom:",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def render_outfit(outfit: OutfitRecommendation, number: int) -> None:
    with st.container(border=True):
        st.badge(f"LOOK {number:02}", color="red", icon=":material/checkroom:")
        st.subheader(outfit.title)
        st.caption(outfit.style)
        st.markdown(f"**色合わせ**　{' × '.join(name for name, _ in outfit.colors)}")
        swatches = "".join(
            (
                '<span style="display:inline-flex;align-items:center;gap:.4rem;'
                'margin-right:.9rem;white-space:nowrap">'
                f'<span aria-hidden="true" style="display:inline-block;width:1rem;'
                f'height:1rem;border-radius:50%;background:{color_hex};'
                'border:1px solid #888"></span>'
                f"<span>{escape(color_name)}</span></span>"
            )
            for color_name, color_hex in outfit.colors
        )
        st.html(
            '<div role="group" aria-label="おすすめ配色、ベース・サブカラー・差し色">'
            f"{swatches}</div>"
        )
        for label, value in (
            ("トップス", outfit.top),
            ("ボトムス", outfit.bottom),
            ("羽織り", outfit.outerwear),
            ("シューズ", outfit.shoes),
            ("小物", outfit.accessory),
        ):
            st.text(f"{label}　{value}")
        st.caption(outfit.reason)


with st.sidebar:
    st.title("コーデの条件", anchor=False)
    audience = st.selectbox(
        "着こなしのイメージ",
        options=["ユニセックス", "レディース", "メンズ"],
    )
    preferred_style = st.selectbox(
        "好きなテイスト",
        options=["おまかせ", "カジュアル", "ストリート", "きれいめ", "スポーティ"],
    )
    preferred_palette = st.selectbox(
        "好きなカラーコーデ",
        options=["おまかせ", "赤×ブルー", "モノトーン", "アースカラー", "ニュートラル"],
    )
    include_weather = st.checkbox("今日の天気も考慮する", value=True)
    city_name = st.selectbox("エリア", options=list(CITIES), index=0, disabled=not include_weather)
    st.caption("写真のアイテムを使った6案を提案します。")
    st.divider()
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        st.caption("OpenAI APIキーはサーバー設定から読み込みます。")
    else:
        st.subheader("OpenAI APIキー", anchor=False)
        api_key = st.text_input(
            "APIキー",
            type="password",
            placeholder="sk-...",
            help=(
                "入力したキーはこのアプリのセッション中だけ利用し、ファイルには保存しません。"
                "キーは提案の生成時にOpenAI APIへ送信されます。"
            ),
            autocomplete="off",
        ).strip()

today = datetime.now(JST).date()
weekday = WEEKDAYS[today.weekday()]
st.title("手持ちの服から、今日の6コーデ。", icon=":material/checkroom:")
st.caption(
    f"FITTING / {today.year}年{today.month}月{today.day}日（{weekday}）"
    " · アイテム写真を読み取り、着回しコーデを提案"
)

st.subheader("服・ファッションアイテムの写真をアップロード")
capture_method = st.radio(
    "写真の取り込み方法",
    options=["ファイルから選択", "カメラで撮影"],
    horizontal=True,
)
if capture_method == "カメラで撮影":
    uploaded_photo = st.camera_input(
        "カメラを起動してアイテムを撮影",
        help="ブラウザーからカメラへのアクセスを許可してください。",
    )
else:
    uploaded_photo = st.file_uploader(
        "使いたい服や小物がわかる写真を選んでください",
        type=["jpg", "jpeg", "png", "webp"],
        max_upload_size=30,
        help="JPEG、PNG、WebP形式、30MB以下。高解像度の写真は自動で縮小します。",
    )
st.caption(
    "ファイル選択または撮影した写真は、提案ボタンを押すと画像解析のためOpenAI APIへ送信されます。"
    "このアプリは写真を保存しません。"
)

if uploaded_photo is None:
    st.info("シャツ、パンツ、靴、バッグなど、コーデに使いたいアイテムの写真を選んでください。")
    photo_bytes = None
    photo_digest = ""
else:
    if uploaded_photo.size > MAX_IMAGE_BYTES:
        st.error("写真は30MB以下にしてください。")
        photo_bytes = None
        photo_digest = ""
    else:
        photo_bytes = uploaded_photo.getvalue()
        photo_digest = hashlib.sha256(photo_bytes).hexdigest()
        preview_column, guidance_column = st.columns([1, 2])
        with preview_column:
            st.image(
                photo_bytes,
                caption="アップロードしたアイテム",
                alt="コーデ提案のために選択した手持ちアイテムの写真",
                width="stretch",
            )
        with guidance_column:
            st.markdown("**写真のポイント**")
            st.caption("服全体が写っていて、色や形を確認できる明るい写真がおすすめです。")
            st.caption("複数の服が写っている場合は、組み合わせたいアイテムが分かる写真を選んでください。")

weather = None
weather_error = None
if include_weather:
    try:
        weather = get_weather(city_name)
        weather_by_city = st.session_state.get("last_weather_by_city", {})
        weather_by_city[city_name] = weather
        st.session_state["last_weather_by_city"] = weather_by_city
    except (requests.RequestException, WeatherDataError) as error:
        weather_error = error
        weather = st.session_state.get("last_weather_by_city", {}).get(city_name)

    with st.container(border=True):
        st.markdown(f"**{city_name}の今日の天気**")
        if weather is not None:
            if weather_error:
                st.warning(
                    f"最新の天気を取得できないため、前回の取得値"
                    f"（{weather.updated_at}）を表示しています。{weather_error}"
                )
            st.caption(
                f"現在 {weather.current_temperature:.0f}°C（体感 {weather.feels_like:.0f}°C）"
                f" · 最高 {weather.high:.0f}°C / 最低 {weather.low:.0f}°C"
            )
            st.caption(
                f"降水確率 {weather.rain_probability}% · "
                f"風速 {weather.wind_speed:.0f}km/h · 湿度 {weather.humidity}%"
            )
        else:
            st.warning(f"天気を取得できませんでした。天気なしで提案します。詳細: {weather_error}")
            if isinstance(weather_error, WeatherRateLimitError):
                st.caption("アクセス制限中は再取得を止めています。時間をおいてページを再読み込みしてください。")
            elif st.button("天気を再取得", key="retry_weather", icon=":material/refresh:"):
                get_weather.clear()
                st.rerun()

today_trends = "、".join(seasonal_trends(today))
request_signature = hashlib.sha256(
    "|".join(
        (
            photo_digest,
            audience,
            preferred_style,
            preferred_palette,
            today.isoformat(),
            str(include_weather),
            city_name if include_weather else "",
        )
    ).encode("utf-8")
).hexdigest()

if st.session_state.get("recommendation_signature") != request_signature:
    st.session_state.pop("photo_analysis", None)
    st.session_state.pop("recommendation_signature", None)
    st.session_state.pop("outfit_images", None)

if st.button(
    "写真から6コーデを提案",
    type="primary",
    icon=":material/auto_awesome:",
    disabled=photo_bytes is None,
):
    if not api_key:
        st.error(
            "OPENAI_API_KEYが設定されていません。"
            "左側の「OpenAI APIキー」に入力するか、環境変数に設定してください。"
        )
    else:
        weather_context = None
        if weather is not None:
            weather_context = (
                f"{weather.city}、現在{weather.current_temperature:.0f}°C、"
                f"体感{weather.feels_like:.0f}°C、最高{weather.high:.0f}°C、"
                f"最低{weather.low:.0f}°C、降水確率{weather.rain_probability}%、"
                f"最大風速{weather.wind_speed:.0f}km/h、湿度{weather.humidity}%"
            )

        try:
            with st.spinner("写真のアイテムを読み取り、6つの着こなしを考えています..."):
                analysis = recommend_from_photo(
                    image_bytes=photo_bytes,
                    audience=audience,
                    preferred_style=preferred_style,
                    preferred_palette=preferred_palette,
                    today=today,
                    weather_context=weather_context,
                    seasonal_context=f"{TREND_AS_OF.year}年秋冬、{today_trends}",
                    api_key=api_key,
                )
            st.session_state["photo_analysis"] = analysis
            st.session_state["recommendation_signature"] = request_signature
        except (PhotoAnalysisError, requests.RequestException) as error:
            st.error(f"コーデを作成できませんでした。{error}")

analysis: PhotoAnalysis | None = st.session_state.get("photo_analysis")
if analysis is not None and st.session_state.get("recommendation_signature") == request_signature:
    if not analysis.garment_found:
        st.warning("写真から服やファッションアイテムを確認できませんでした。別の写真をお試しください。")
        if analysis.item_summary:
            st.text(analysis.item_summary)
    else:
        st.subheader("写真から読み取ったアイテム", icon=":material/visibility:")
        st.text(f"{analysis.item_type} · {analysis.item_summary}")
        if analysis.colors:
            st.caption(f"写真で確認した色: {'、'.join(analysis.colors)}")

        st.subheader("このアイテムを使った6つのコーデ", icon=":material/checkroom:")
        st.caption("各案のボタンを押すと画像を1枚生成します。生成ごとにAPI利用料が発生する場合があります。")
        columns = st.columns(3)
        for index, outfit in enumerate(analysis.outfits):
            with columns[index % len(columns)]:
                render_outfit(outfit, index + 1)
                image_key = f"look_{index + 1}"
                if st.button(
                    "このコーデのイメージ画像を生成",
                    key=f"generate_image_{request_signature}_{index}",
                    icon=":material/image:",
                ):
                    try:
                        with st.spinner("コーデのイメージ画像を生成しています..."):
                            image_bytes = generate_outfit_image(
                                item_type=analysis.item_type,
                                item_summary=analysis.item_summary,
                                audience=audience,
                                outfit=outfit,
                                api_key=api_key,
                            )
                        generated_images = st.session_state.get("outfit_images", {})
                        generated_images[image_key] = image_bytes
                        st.session_state["outfit_images"] = generated_images
                    except (ImageGenerationError, requests.RequestException) as error:
                        st.error(f"イメージ画像を作成できませんでした。{error}")

                generated_image = st.session_state.get("outfit_images", {}).get(image_key)
                if generated_image:
                    st.image(
                        generated_image,
                        caption=f"LOOK {index + 1:02} のAIイメージ",
                        alt=f"{outfit.title}を着用した全身コーディネートのAIイメージ",
                        width="stretch",
                    )

st.markdown("**海外トレンドのムード**　" + today_trends)
st.caption(
    f"海外ストリートスタイル／ランウェイ記事を参考にした編集テーマ · "
    f"{TREND_AS_OF:%Y年%m月%d日}更新"
)
st.markdown(
    "出典: "
    + " · ".join(f"[{label}]({url})" for label, url in TREND_SOURCES)
)
