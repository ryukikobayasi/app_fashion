from hashlib import sha256

import streamlit as st

from bookmark_store import (
    ALL_BOOKMARKS_TAB,
    DEFAULT_BOOKMARK_GROUP,
    MAX_BOOKMARKS,
    MAX_BOOKMARK_GROUP_LENGTH,
    MAX_BOOKMARK_NAME_LENGTH,
    MAX_BOOKMARK_URL_LENGTH,
    Bookmark,
    BookmarkLimitError,
    BookmarkStorageError,
    InvalidBookmarkDetails,
    InvalidBookmarkUrl,
    add_bookmark,
    delete_bookmark,
    load_bookmarks,
    update_bookmark,
)


_PENDING_DELETE_KEY = "pending_shared_bookmark_delete"
_DELETE_NOTICE_KEY = "shared_bookmark_delete_notice"
_UPDATE_NOTICE_KEY = "shared_bookmark_update_notice"


def _render_bookmark(bookmark: Bookmark, tab_key: str) -> None:
    bookmark_key = f"{tab_key}_{bookmark.id}"
    with st.container(border=True):
        st.subheader(bookmark.site_name)
        st.caption(f"グループ: {bookmark.group_name}")
        st.code(bookmark.url, language=None, wrap_lines=True)

        with st.expander(
            "サイト名・グループを編集",
            key=f"edit_bookmark_section_{bookmark_key}",
        ):
            with st.form(f"edit_bookmark_form_{bookmark_key}"):
                site_name = st.text_input(
                    "サイト名",
                    value=bookmark.site_name,
                    max_chars=MAX_BOOKMARK_NAME_LENGTH,
                    key=f"edit_bookmark_name_{bookmark_key}",
                )
                group_name = st.text_input(
                    "グループ",
                    value=bookmark.group_name,
                    max_chars=MAX_BOOKMARK_GROUP_LENGTH,
                    key=f"edit_bookmark_group_{bookmark_key}",
                )
                edit_submitted = st.form_submit_button(
                    "変更を保存",
                    key=f"save_bookmark_{bookmark_key}",
                    type="primary",
                )

        if edit_submitted:
            try:
                updated = update_bookmark(
                    bookmark.url,
                    site_name,
                    group_name,
                )
            except InvalidBookmarkDetails as error:
                st.error(str(error))
            except BookmarkStorageError as error:
                st.error(f"ブックマークを更新できませんでした。{error}")
            else:
                st.session_state[_UPDATE_NOTICE_KEY] = (
                    "サイト名とグループを更新しました。"
                    if updated
                    else "このサイトはすでに削除されています。"
                )
                st.rerun()

        if st.session_state.get(_PENDING_DELETE_KEY) == bookmark.url:
            st.warning("このURLを削除しますか？")
            confirm_column, cancel_column = st.columns(2)
            with confirm_column:
                if st.button(
                    "削除する",
                    key=f"confirm_bookmark_delete_{bookmark_key}",
                    type="primary",
                ):
                    try:
                        _, deleted = delete_bookmark(bookmark.url)
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
                    bookmark.url,
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
                    st.session_state[_PENDING_DELETE_KEY] = bookmark.url
                    st.rerun()


st.title("お気に入りサイト", icon=":material/bookmark:")
st.caption("サイト名とグループを付けて保存し、グループごとのタブで整理できます。")
st.warning(
    "このリストは利用者全員で共有され、ログインなしで閲覧・追加・編集・削除できます。"
    "保存先はTursoの外部SQLite互換データベースです。Renderの再起動・再デプロイでは消えません。"
    "Turso側の利用枠・サービス条件は適用されます。"
)

delete_notice = st.session_state.pop(_DELETE_NOTICE_KEY, None)
if delete_notice:
    st.success(delete_notice)

update_notice = st.session_state.pop(_UPDATE_NOTICE_KEY, None)
if update_notice:
    st.success(update_notice)

try:
    bookmarks = load_bookmarks()
except BookmarkStorageError as error:
    st.error(f"サイトURLを読み込めませんでした。{error}")
    st.stop()

with st.form("add_bookmark_form", clear_on_submit=True):
    bookmark_url = st.text_input(
        "サイトURL",
        placeholder="https://example.com",
        max_chars=MAX_BOOKMARK_URL_LENGTH,
    )
    site_name = st.text_input(
        "サイト名",
        placeholder="例: Vogue Japan（空欄ならドメイン名）",
        max_chars=MAX_BOOKMARK_NAME_LENGTH,
    )
    group_name = st.text_input(
        "グループ",
        value=DEFAULT_BOOKMARK_GROUP,
        max_chars=MAX_BOOKMARK_GROUP_LENGTH,
    )
    add_submitted = st.form_submit_button(
        "URLを登録",
        type="primary",
        icon=":material/bookmark_add:",
    )
st.caption("新しいグループ名を入力すると、そのグループのタブが作られます。")

if add_submitted:
    try:
        bookmarks, added = add_bookmark(
            bookmark_url,
            site_name,
            group_name,
        )
    except (InvalidBookmarkUrl, InvalidBookmarkDetails, BookmarkLimitError) as error:
        st.error(str(error))
    except BookmarkStorageError as error:
        st.error(f"URLを保存できませんでした。{error}")
    else:
        if added:
            st.success("サイトURLを登録しました。")
        else:
            st.info("このURLはすでに登録されています。編集からサイト名やグループを変更できます。")

st.subheader("登録済みサイト")
st.caption(f"{len(bookmarks)} / {MAX_BOOKMARKS} 件")

bookmark_urls = {bookmark.url for bookmark in bookmarks}
pending_delete = st.session_state.get(_PENDING_DELETE_KEY)
if pending_delete is not None and pending_delete not in bookmark_urls:
    st.session_state.pop(_PENDING_DELETE_KEY, None)

groups = list(dict.fromkeys(bookmark.group_name for bookmark in bookmarks))
tab_specs = [(ALL_BOOKMARKS_TAB, None), *((group, group) for group in groups)]
tabs = st.tabs([label for label, _ in tab_specs])

for tab, (_, selected_group) in zip(tabs, tab_specs):
    tab_key = (
        "all"
        if selected_group is None
        else sha256(selected_group.encode("utf-8")).hexdigest()[:12]
    )
    with tab:
        visible_bookmarks = (
            bookmarks
            if selected_group is None
            else [
                bookmark
                for bookmark in bookmarks
                if bookmark.group_name == selected_group
            ]
        )
        if not visible_bookmarks:
            st.info("まだサイトURLがありません。上のフォームから登録できます。")
        for bookmark in visible_bookmarks:
            _render_bookmark(bookmark, tab_key)
