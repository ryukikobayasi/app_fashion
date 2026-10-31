from hashlib import sha256

import streamlit as st

from bookmark_store import (
    MAX_BOOKMARKS,
    BookmarkLimitError,
    BookmarkStorageError,
    InvalidBookmarkUrl,
    add_bookmark,
    delete_bookmark,
    load_bookmarks,
)


_PENDING_DELETE_KEY = "pending_shared_bookmark_delete"
_DELETE_NOTICE_KEY = "shared_bookmark_delete_notice"


st.title("お気に入りサイト", icon=":material/bookmark:")
st.caption("あとで見返したいサイトのURLを登録しておけます。")
st.warning(
    "このURLリストはサイト利用者全員で共有されます。ログインはなく、URLを知る人は閲覧・追加・削除ができます。"
    "保存先はTursoの外部SQLite互換データベースです。Renderの再起動・再デプロイでは消えません。"
    "Turso側の利用枠・サービス条件は適用されます。"
)

delete_notice = st.session_state.pop(_DELETE_NOTICE_KEY, None)
if delete_notice:
    st.success(delete_notice)

try:
    bookmarks = load_bookmarks()
except BookmarkStorageError as error:
    st.error(f"サイトURLを読み込めませんでした。{error}")
    st.stop()

with st.form("add_bookmark_form", clear_on_submit=True):
    bookmark_url = st.text_input(
        "サイトURL",
        placeholder="https://example.com",
        max_chars=2048,
    )
    add_submitted = st.form_submit_button(
        "URLを登録",
        type="primary",
        icon=":material/bookmark_add:",
    )

if add_submitted:
    try:
        bookmarks, added = add_bookmark(bookmark_url)
    except (InvalidBookmarkUrl, BookmarkLimitError) as error:
        st.error(str(error))
    except BookmarkStorageError as error:
        st.error(f"URLを保存できませんでした。{error}")
    else:
        if added:
            st.success("サイトURLを登録しました。")
        else:
            st.info("このURLはすでに登録されています。")

st.subheader("登録済みURL")
st.caption(f"{len(bookmarks)} / {MAX_BOOKMARKS} 件")

pending_delete = st.session_state.get(_PENDING_DELETE_KEY)
if pending_delete is not None and pending_delete not in bookmarks:
    st.session_state.pop(_PENDING_DELETE_KEY, None)
    pending_delete = None

if not bookmarks:
    st.info("まだサイトURLがありません。上のフォームから登録できます。")

for url in bookmarks:
    bookmark_key = sha256(url.encode("utf-8")).hexdigest()[:16]
    with st.container(border=True):
        st.code(url, language=None, wrap_lines=True)
        if pending_delete == url:
            st.warning("このURLを削除しますか？")
            confirm_column, cancel_column = st.columns(2)
            with confirm_column:
                if st.button(
                    "削除する",
                    key=f"confirm_bookmark_delete_{bookmark_key}",
                    type="primary",
                ):
                    try:
                        _, deleted = delete_bookmark(url)
                    except BookmarkStorageError as error:
                        st.error(f"URLを削除できませんでした。{error}")
                    else:
                        st.session_state.pop(_PENDING_DELETE_KEY, None)
                        st.session_state[_DELETE_NOTICE_KEY] = (
                            "サイトURLを削除しました。"
                            if deleted
                            else "このURLはすでに削除されています。"
                        )
                        st.rerun()
            with cancel_column:
                if st.button(
                    "キャンセル",
                    key=f"cancel_bookmark_delete_{bookmark_key}",
                ):
                    st.session_state.pop(_PENDING_DELETE_KEY, None)
                    st.rerun()
        else:
            open_column, delete_column = st.columns([3, 1])
            with open_column:
                st.link_button(
                    "サイトを開く",
                    url,
                    key=f"open_bookmark_{bookmark_key}",
                    icon=":material/open_in_new:",
                    width="stretch",
                )
            with delete_column:
                if st.button(
                    "削除",
                    key=f"delete_bookmark_{bookmark_key}",
                    icon=":material/delete:",
                    width="stretch",
                ):
                    st.session_state[_PENDING_DELETE_KEY] = url
                    st.rerun()
