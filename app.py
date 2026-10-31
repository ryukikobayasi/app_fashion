from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))
APP_DIRECTORY = Path(__file__).resolve().parent

st.set_page_config(
    page_title="FITTING | コーデと髪型の提案",
    page_icon=":material/checkroom:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

page = st.navigation(
    [
        st.Page(
            APP_DIRECTORY / "app_pages" / "wardrobe.py",
            title="今日のコーデ",
            icon=":material/checkroom:",
            default=True,
        ),
        st.Page(
            APP_DIRECTORY / "app_pages" / "hairstyles.py",
            title="メンズ髪型診断",
            icon=":material/face:",
        ),
        st.Page(
            APP_DIRECTORY / "app_pages" / "bookmarks.py",
            title="お気に入り",
            icon=":material/bookmark:",
        ),
    ],
    position="top",
)
page.run()
