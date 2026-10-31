from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

st.set_page_config(
    page_title="FITTING | コーデと髪型の提案",
    page_icon=":material/checkroom:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

page = st.navigation(
    [
        st.Page(
            r"app_pages\wardrobe.py",
            title="今日のコーデ",
            icon=":material/checkroom:",
            default=True,
        ),
        st.Page(
            r"app_pages\hairstyles.py",
            title="メンズ髪型診断",
            icon=":material/face:",
        ),
    ],
    position="top",
)
page.run()
