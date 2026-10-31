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

st.html(
    """
    <style>
    @media screen and (max-width: 640px) {
      .block-container {
        padding-top: max(5rem, calc(60px + env(safe-area-inset-top) + 1rem)) !important;
        padding-right: max(0.75rem, env(safe-area-inset-right)) !important;
        padding-bottom: 2rem !important;
        padding-left: max(0.75rem, env(safe-area-inset-left)) !important;
      }
      h1 {
        font-size: 1.6rem !important;
        line-height: 1.35 !important;
      }
      h2 {
        font-size: 1.4rem !important;
        line-height: 1.4 !important;
      }
      h3 {
        font-size: 1.15rem !important;
        line-height: 1.45 !important;
      }
      [data-testid="stMarkdownContainer"] p,
      [data-testid="stText"] p,
      [data-testid="stWidgetLabel"] p {
        font-size: 1rem !important;
        line-height: 1.6 !important;
      }
      [data-testid="stCaptionContainer"] p {
        font-size: 0.875rem !important;
        line-height: 1.5 !important;
      }
      [data-testid="stButton"] button,
      [data-testid="stFormSubmitButton"] button,
      [data-testid="stLinkButton"] a {
        min-height: 44px !important;
        font-size: 1rem !important;
      }
      [data-testid="stTextInput"] input,
      [data-testid="stTextArea"] textarea,
      [data-baseweb="select"] {
        font-size: 16px !important;
      }
      [data-testid="stSelectbox"] [data-baseweb="select"] * {
        font-size: 16px !important;
      }
      [data-testid="stTextInput"] input,
      [data-testid="stTextArea"] textarea,
      [data-baseweb="select"] > div {
        min-height: 44px !important;
      }
      [data-testid="stRadio"] label,
      [data-testid="stCheckbox"] label,
      [data-testid="stToggle"] label {
        font-size: 1rem !important;
      }
      [data-testid="stTabs"] [role="tablist"] {
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
      }
      [data-testid="stTabs"] [role="tab"] {
        flex: 0 0 auto !important;
        padding: 0.5rem 0.65rem !important;
        font-size: 0.875rem !important;
        white-space: nowrap !important;
      }
      [data-testid="stCodeBlock"] pre {
        overflow-wrap: anywhere !important;
        white-space: pre-wrap !important;
      }
    }
    </style>
    """
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
