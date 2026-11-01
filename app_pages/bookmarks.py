from hashlib import sha256

import streamlit as st

from bookmark_store import (
    ALL_BOOKMARKS_TAB,
    DEFAULT_BOOKMARK_GROUP,
    MAX_BOOKMARKS,
    MAX_BOOKMARK_GROUP_LENGTH,
    MAX_BOOKMARK_MEMO_LENGTH,
    MAX_BOOKMARK_NAME_LENGTH,
    MAX_BOOKMARK_URL_LENGTH,
    Bookmark,
    BookmarkLimitError,
    BookmarkStorageError,
    InvalidBookmarkDetails,
    InvalidBookmarkOrder,
    InvalidBookmarkUrl,
    add_bookmark,
    delete_bookmark,
    load_bookmark_group_order,
    load_bookmarks,
    rename_bookmark_group,
    save_bookmark_group_order,
    save_bookmark_order,
    update_bookmark,
)


_PENDING_DELETE_KEY = "pending_shared_bookmark_delete"
_DELETE_NOTICE_KEY = "shared_bookmark_delete_notice"
_UPDATE_NOTICE_KEY = "shared_bookmark_update_notice"
_GROUP_RENAME_NOTICE_KEY = "shared_bookmark_group_rename_notice"


def _render_group_fields(
    groups: list[str],
    selected_group: str,
    widget_key: str,
) -> str:
    group_options = groups or [selected_group or DEFAULT_BOOKMARK_GROUP]
    if selected_group not in group_options:
        group_options = [selected_group, *group_options]

    selection_key = f"{widget_key}_existing_group"
    if st.session_state.get(selection_key) not in group_options:
        st.session_state.pop(selection_key, None)

    selected = st.selectbox(
        "登録済みグループ",
        options=group_options,
        index=group_options.index(selected_group),
        key=selection_key,
    )
    new_group = st.text_input(
        "新しいグループ名（任意）",
        placeholder="入力すると選択中のグループの代わりに使われます",
        max_chars=MAX_BOOKMARK_GROUP_LENGTH,
        key=f"{widget_key}_new_group",
    )
    return new_group.strip() or selected


def _render_bookmark(bookmark: Bookmark, tab_key: str, groups: list[str]) -> None:
    bookmark_key = f"{tab_key}_{bookmark.id}"
    group_rename_widget_key = (
        f"{bookmark_key}_{sha256(bookmark.group_name.encode('utf-8')).hexdigest()[:12]}"
    )
    with st.container(border=True):
        st.subheader(bookmark.site_name)
        st.caption(f"グループ: {bookmark.group_name}")
        if bookmark.memo:
            st.caption(f"メモ: {bookmark.memo}")
        with st.expander(
            "サイト情報を編集",
            key=f"edit_bookmark_section_{bookmark_key}",
            expanded=st.session_state.get(_PENDING_DELETE_KEY) == bookmark.url,
        ):
            with st.form(f"edit_bookmark_form_{bookmark_key}"):
                site_url = st.text_input(
                    "サイトURL",
                    value=bookmark.url,
                    max_chars=MAX_BOOKMARK_URL_LENGTH,
                    key=f"edit_bookmark_url_{bookmark_key}",
                )
                site_name = st.text_input(
                    "サイト名",
                    value=bookmark.site_name,
                    max_chars=MAX_BOOKMARK_NAME_LENGTH,
                    key=f"edit_bookmark_name_{bookmark_key}",
                )
                group_name = _render_group_fields(
                    groups,
                    bookmark.group_name,
                    f"edit_bookmark_{bookmark_key}",
                )
                memo = st.text_area(
                    "メモ",
                    value=bookmark.memo,
                    max_chars=MAX_BOOKMARK_MEMO_LENGTH,
                    help="入力したメモは、登録済み一覧でグループ名の下に表示されます。",
                    key=f"edit_bookmark_memo_{bookmark_key}",
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
                        new_url=site_url,
                        memo=memo,
                    )
                except (InvalidBookmarkUrl, InvalidBookmarkDetails) as error:
                    st.error(str(error))
                except BookmarkStorageError as error:
                    st.error(f"ブックマークを更新できませんでした。{error}")
                else:
                    st.session_state[_UPDATE_NOTICE_KEY] = (
                        "URL、サイト名、グループ、メモを更新しました。"
                        if updated
                        else "このサイトはすでに削除されています。"
                    )
                    st.rerun()

            with st.container(border=True):
                st.markdown(f"**グループ名を変更: {bookmark.group_name}**")
                st.caption("このグループに属するすべてのサイトに反映されます。")
                with st.form(
                    f"rename_bookmark_group_form_{group_rename_widget_key}"
                ):
                    new_group_name = st.text_input(
                        "新しいグループ名",
                        max_chars=MAX_BOOKMARK_GROUP_LENGTH,
                        key=f"rename_bookmark_group_name_{group_rename_widget_key}",
                    )
                    rename_submitted = st.form_submit_button(
                        "グループ名を変更",
                        key=f"save_group_rename_{group_rename_widget_key}",
                    )

                if rename_submitted:
                    try:
                        renamed = rename_bookmark_group(
                            bookmark.group_name,
                            new_group_name,
                        )
                    except (InvalidBookmarkDetails, BookmarkStorageError) as error:
                        st.error(f"グループ名を変更できませんでした。{error}")
                    else:
                        if renamed:
                            st.session_state[_GROUP_RENAME_NOTICE_KEY] = (
                                "グループ名を変更しました。"
                            )
                            st.rerun()
                        st.info("変更対象のグループはすでにありません。")

            st.divider()
            if st.session_state.get(_PENDING_DELETE_KEY) == bookmark.url:
                st.warning("このサイトを削除しますか？")
                st.caption("削除すると元に戻せません。")
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
                            st.error(f"サイトを削除できませんでした。{error}")
                        else:
                            st.session_state.pop(_PENDING_DELETE_KEY, None)
                            st.session_state[_DELETE_NOTICE_KEY] = (
                                "サイトを削除しました。"
                                if deleted
                                else "このサイトはすでに削除されています。"
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
                if st.button(
                    "このサイトを削除",
                    key=f"delete_bookmark_{bookmark_key}",
                    icon=":material/delete:",
                    width="stretch",
                ):
                    st.session_state[_PENDING_DELETE_KEY] = bookmark.url
                    st.rerun()

        st.link_button(
            "サイトを開く",
            bookmark.url,
            key=f"open_bookmark_{bookmark_key}",
            icon=":material/open_in_new:",
            width="stretch",
        )


st.title("お気に入りサイト", icon=":material/bookmark:")
st.caption("サイト名・URL・グループ・メモを保存し、登録後の編集や並べ替えができます。")

delete_notice = st.session_state.pop(_DELETE_NOTICE_KEY, None)
if delete_notice:
    st.success(delete_notice)

update_notice = st.session_state.pop(_UPDATE_NOTICE_KEY, None)
if update_notice:
    st.success(update_notice)

group_rename_notice = st.session_state.pop(_GROUP_RENAME_NOTICE_KEY, None)
if group_rename_notice:
    st.success(group_rename_notice)

try:
    bookmarks = load_bookmarks()
except BookmarkStorageError as error:
    st.error(f"サイトURLを読み込めませんでした。{error}")
    st.stop()

group_names = list(dict.fromkeys(bookmark.group_name for bookmark in bookmarks))
try:
    groups = load_bookmark_group_order(group_names)
except BookmarkStorageError as error:
    st.error(f"グループの順番を読み込めませんでした。{error}")
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
    group_name = _render_group_fields(
        groups,
        groups[0] if groups else DEFAULT_BOOKMARK_GROUP,
        "add_bookmark",
    )
    add_submitted = st.form_submit_button(
        "URLを登録",
        type="primary",
        icon=":material/bookmark_add:",
    )
st.caption("登録済みグループを選ぶか、新しいグループ名を入力できます。URLは編集フォーム内でのみ確認できます。")

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
        group_names = list(dict.fromkeys(bookmark.group_name for bookmark in bookmarks))
        groups = [group for group in groups if group in group_names] + [
            group for group in group_names if group not in groups
        ]

st.subheader("登録済みサイト")
st.caption(f"{len(bookmarks)} / {MAX_BOOKMARKS} 件")

bookmark_urls = {bookmark.url for bookmark in bookmarks}
pending_delete = st.session_state.get(_PENDING_DELETE_KEY)
if pending_delete is not None and pending_delete not in bookmark_urls:
    st.session_state.pop(_PENDING_DELETE_KEY, None)

if len(bookmarks) > 1:
    with st.expander("登録サイトの順番", expanded=False):
        st.caption(
            "「上へ」「下へ」で1つずつ、「先頭へ」で一覧の一番上に移動できます。新しく登録したサイトは末尾に追加され、変更は自動保存されます。"
        )
        for index, bookmark in enumerate(bookmarks):
            with st.container(border=True):
                st.markdown(f"**{index + 1}. {bookmark.site_name}**")
                st.caption(f"グループ: {bookmark.group_name}")
                move_up_column, move_down_column, move_to_top_column = st.columns(3)
                with move_up_column:
                    move_up = st.button(
                        "1つ上へ",
                        icon=":material/arrow_upward:",
                        disabled=index == 0,
                        key=f"move_bookmark_up_{bookmark.id}",
                    )
                with move_down_column:
                    move_down = st.button(
                        "1つ下へ",
                        icon=":material/arrow_downward:",
                        disabled=index == len(bookmarks) - 1,
                        key=f"move_bookmark_down_{bookmark.id}",
                    )
                with move_to_top_column:
                    move_to_top = st.button(
                        "先頭へ",
                        icon=":material/arrow_upward:",
                        disabled=index == 0,
                        key=f"move_bookmark_to_top_{bookmark.id}",
                    )

            if move_up or move_down or move_to_top:
                reordered_bookmarks = list(bookmarks)
                if move_up:
                    reordered_bookmarks[index - 1], reordered_bookmarks[index] = (
                        reordered_bookmarks[index],
                        reordered_bookmarks[index - 1],
                    )
                elif move_down:
                    reordered_bookmarks[index], reordered_bookmarks[index + 1] = (
                        reordered_bookmarks[index + 1],
                        reordered_bookmarks[index],
                    )
                else:
                    reordered_bookmarks = [
                        bookmark,
                        *bookmarks[:index],
                        *bookmarks[index + 1 :],
                    ]
                try:
                    save_bookmark_order(
                        [item.id for item in reordered_bookmarks]
                    )
                except (InvalidBookmarkOrder, BookmarkStorageError) as error:
                    st.error(f"登録サイトの順番を保存できませんでした。{error}")
                else:
                    st.rerun()

if len(groups) > 1:
    with st.expander("グループタブの順番", expanded=False):
        st.caption(
            "番号の上から順にタブが並びます。各グループの「上へ」「下へ」で1つずつ移動できます。変更は自動保存されます。"
        )
        for index, group in enumerate(groups):
            group_key = sha256(group.encode("utf-8")).hexdigest()[:12]
            with st.container(border=True):
                st.markdown(f"**{index + 1}. {group}**")
                move_up_column, move_down_column = st.columns(2)
                with move_up_column:
                    move_up = st.button(
                        "上へ",
                        icon=":material/arrow_upward:",
                        disabled=index == 0,
                        key=f"move_bookmark_group_up_{group_key}",
                    )
                with move_down_column:
                    move_down = st.button(
                        "下へ",
                        icon=":material/arrow_downward:",
                        disabled=index == len(groups) - 1,
                        key=f"move_bookmark_group_down_{group_key}",
                    )

            if move_up or move_down:
                reordered_groups = groups.copy()
                target_index = index - 1 if move_up else index + 1
                reordered_groups[index], reordered_groups[target_index] = (
                    reordered_groups[target_index],
                    reordered_groups[index],
                )
                try:
                    save_bookmark_group_order(reordered_groups)
                except (InvalidBookmarkDetails, BookmarkStorageError) as error:
                    st.error(f"グループの順番を保存できませんでした。{error}")
                else:
                    st.rerun()

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
            _render_bookmark(bookmark, tab_key, groups)
