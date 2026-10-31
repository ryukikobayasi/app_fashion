import hashlib
from datetime import datetime, timedelta, timezone
from html import escape
import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

from camera_component import CameraCaptureError, capture_camera_photo, decode_camera_photo
from outfit_engine import TREND_AS_OF, TREND_SOURCES, seasonal_trends
from image_generator import ImageGenerationError, generate_outfit_image
from photo_recommender import (
    MAX_IMAGE_BYTES,
    MAX_PHOTO_COUNT,
    MAX_TOTAL_IMAGE_BYTES,
    OutfitRecommendation,
    PhotoAnalysis,
    PhotoAnalysisError,
    recommend_from_photo,
)
from weather import (
    CITIES,
    HistoricalMonthlyAverage,
    Weather,
    WeatherDataError,
    WeatherRateLimitError,
    get_historical_monthly_average,
    get_weather,
)


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
        st.badge(outfit.pattern, color="blue", icon=":material/style:")
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
        st.markdown(f"**プラスワン候補**　{outfit.extra_item}")
        st.caption(outfit.extra_item_reason)
        st.caption(outfit.reason)


with st.sidebar:
    st.title("コーデの条件", anchor=False)
    audience = st.selectbox(
        "着こなしのイメージ",
        options=["ユニセックス", "レディース", "メンズ"],
        index=2,
    )
    preferred_style = "きれいめカジュアル"
    preferred_palette = st.selectbox(
        "好きなカラーコーデ",
        options=["おまかせ", "赤×ブルー", "モノトーン", "アースカラー", "ニュートラル"],
        index=2,
    )
    include_weather = st.checkbox("今日の天気も考慮する", value=True)
    city_name = st.selectbox("エリア", options=list(CITIES), index=0, disabled=not include_weather)
    st.caption(
        "写真のアイテムを使った8案を、すべてきれいめカジュアルで提案します。"
        "ブラックスピネルのネックレス、時計、黒の厚底靴を合わせます。"
    )
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
st.title("手持ちの服から、今日の8コーデ。", icon=":material/checkroom:")
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
    st.caption(
        "背面カメラから起動します。前後を切り替えられ、1枚撮るごとに追加して複数枚を登録できます。"
    )
    camera_photos = st.session_state.setdefault("camera_photos", [])
    camera_capture_index = st.session_state.setdefault("camera_capture_index", 0)
    if len(camera_photos) < MAX_PHOTO_COUNT:
        camera_result = capture_camera_photo(reset_token=camera_capture_index)
        if camera_result.photo_added is not None:
            try:
                captured_bytes = decode_camera_photo(camera_result.photo_added)
            except CameraCaptureError as error:
                st.error(str(error))
            else:
                total_camera_bytes = sum(len(photo) for photo in camera_photos)
                if total_camera_bytes + len(captured_bytes) > MAX_TOTAL_IMAGE_BYTES:
                    st.error("写真の合計サイズは60MB以下にしてください。撮影写真を追加できません。")
                else:
                    st.session_state["camera_photos"] = [*camera_photos, captured_bytes]
                    st.session_state["camera_capture_index"] = camera_capture_index + 1
                    st.rerun()
    else:
        st.info(f"最大{MAX_PHOTO_COUNT}枚を追加済みです。別の写真を撮るには、下の写真を削除してください。")
    candidate_photo_bytes = tuple(camera_photos)
else:
    uploaded_photos = st.file_uploader(
        "使いたい服や小物の写真を選んでください（複数選択可）",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        max_upload_size=30,
        help="JPEG、PNG、WebP形式。最大8枚、1枚30MB以下、合計60MB以下。高解像度の写真は自動で縮小します。",
    ) or []
    candidate_photo_bytes = tuple(photo.getvalue() for photo in uploaded_photos)
st.caption(
    "選択した写真はすべて、提案ボタンを押すと画像解析のためOpenAI APIへ送信されます。"
    "写真はファイルに保存せず、カメラ撮影分はセッション中だけ一時保持します。"
    "写真が複数枚の場合、API利用料が増えることがあります。"
)

photo_bytes: tuple[bytes, ...] | None = None
photo_digest = ""
if not candidate_photo_bytes:
    if capture_method == "カメラで撮影":
        st.info("アイテムを撮影し、「撮影した写真を追加」を押してください。")
    else:
        st.info("シャツ、パンツ、靴、バッグなど、コーデに使いたいアイテムの写真を選んでください。")
elif len(candidate_photo_bytes) > MAX_PHOTO_COUNT:
    st.error(f"写真は最大{MAX_PHOTO_COUNT}枚まで選択できます。")
else:
    oversized_photo = next(
        (
            index
            for index, image in enumerate(candidate_photo_bytes, start=1)
            if len(image) > MAX_IMAGE_BYTES
        ),
        None,
    )
    total_size = sum(len(image) for image in candidate_photo_bytes)
    if oversized_photo is not None:
        st.error(f"{oversized_photo}枚目の写真は30MB以下にしてください。")
    elif total_size > MAX_TOTAL_IMAGE_BYTES:
        st.error("写真の合計サイズは60MB以下にしてください。")
    else:
        photo_bytes = candidate_photo_bytes
        photo_digest = hashlib.sha256(
            "\0".join(hashlib.sha256(image).hexdigest() for image in photo_bytes).encode("ascii")
        ).hexdigest()
        st.caption(f"{len(photo_bytes)}枚の写真をまとめてコーデ提案に使用します。")
        preview_columns = st.columns(3)
        for index, image in enumerate(photo_bytes):
            with preview_columns[index % len(preview_columns)]:
                st.image(
                    image,
                    caption=f"アイテム写真 {index + 1}",
                    alt=f"コーデ提案のために選択した手持ちアイテムの写真 {index + 1}",
                    width="stretch",
                )
                if capture_method == "カメラで撮影" and st.button(
                    "撮影写真を削除",
                    key=f"remove_camera_photo_{index}",
                    icon=":material/delete:",
                ):
                    updated_camera_photos = list(st.session_state["camera_photos"])
                    updated_camera_photos.pop(index)
                    st.session_state["camera_photos"] = updated_camera_photos
                    st.rerun()
        st.caption("服全体が写っていて、色や形を確認できる明るい写真がおすすめです。")

weather: Weather | None = None
weather_error = None
historical_weather: HistoricalMonthlyAverage | None = None
historical_weather_error = None
if include_weather:
    try:
        weather = get_weather(city_name)
    except (requests.RequestException, WeatherDataError) as error:
        weather_error = error
        try:
            historical_weather = get_historical_monthly_average(
                city_name,
                today.year - 1,
                today.month,
            )
        except (requests.RequestException, WeatherDataError) as historical_error:
            historical_weather_error = historical_error

    with st.container(border=True):
        weather_heading = (
            f"{city_name}の今日の天気"
            if weather is not None
            else f"{city_name}の天気・気温情報"
        )
        st.markdown(f"**{weather_heading}**")
        if weather is not None:
            st.caption(
                f"現在 {weather.current_temperature:.0f}°C（体感 {weather.feels_like:.0f}°C）"
                f" · 最高 {weather.high:.0f}°C / 最低 {weather.low:.0f}°C"
            )
            st.caption(
                f"降水確率 {weather.rain_probability}% · "
                f"風速 {weather.wind_speed:.0f}km/h · 湿度 {weather.humidity}%"
            )
        elif historical_weather is not None:
            st.warning(
                f"今日の天気を取得できないため、前年同月の平均気温を参考に提案します。"
                f"（{weather_error}）"
            )
            st.caption(
                f"{historical_weather.year}年{historical_weather.month}月の平均気温 "
                f"{historical_weather.average_temperature:.1f}°C"
                f"（{historical_weather.sample_days}日分。今日の実況・予報ではありません）"
            )
            st.caption("降水確率・風速・湿度は取得できていないため、服装には反映しません。")
        else:
            st.warning("今日の天気と前年同月の平均気温を取得できませんでした。季節感をもとに提案します。")
            st.caption(f"天気: {weather_error} · 前年同月平均: {historical_weather_error}")
            if isinstance(weather_error, WeatherRateLimitError) or isinstance(
                historical_weather_error,
                WeatherRateLimitError,
            ):
                st.caption("アクセス制限中は再取得を止めています。時間をおいてページを再読み込みしてください。")
            elif st.button("天気を再取得", key="retry_weather", icon=":material/refresh:"):
                get_weather.clear()
                get_historical_monthly_average.clear()
                st.rerun()

today_trends = "、".join(seasonal_trends(today))
weather_context = None
if weather is not None:
    weather_context = (
        f"{weather.city}、現在{weather.current_temperature:.0f}°C、"
        f"体感{weather.feels_like:.0f}°C、最高{weather.high:.0f}°C、"
        f"最低{weather.low:.0f}°C、降水確率{weather.rain_probability}%、"
        f"最大風速{weather.wind_speed:.0f}km/h、湿度{weather.humidity}%"
    )
elif historical_weather is not None:
    weather_context = (
        f"前年同月（{historical_weather.year}年{historical_weather.month}月）の平均気温 "
        f"{historical_weather.average_temperature:.1f}°C"
        f"（{historical_weather.sample_days}日分。今日の実況・予報ではない季節参考値。"
        "降水・風・湿度は不明）"
    )

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
            weather_context or "",
        )
    ).encode("utf-8")
).hexdigest()

if st.session_state.get("recommendation_signature") != request_signature:
    st.session_state.pop("photo_analysis", None)
    st.session_state.pop("recommendation_signature", None)
    st.session_state.pop("outfit_images", None)

if st.button(
    "写真から8コーデを提案",
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
        try:
            with st.spinner("すべての写真を読み取り、8つの着こなしを考えています..."):
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

        st.subheader("このアイテムを使った8つのコーデ", icon=":material/checkroom:")
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
