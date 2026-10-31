import os
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import TypeVar
from urllib.parse import urlsplit

import turso_serverless


MAX_BOOKMARK_URL_LENGTH = 2048
MAX_BOOKMARK_NAME_LENGTH = 100
MAX_BOOKMARK_GROUP_LENGTH = 50
MAX_BOOKMARKS = 1000
DEFAULT_BOOKMARK_GROUP = "未分類"
ALL_BOOKMARKS_TAB = "すべて"
_DATABASE_LOCK = RLock()
_Result = TypeVar("_Result")


@dataclass(frozen=True)
class Bookmark:
    id: int
    url: str
    site_name: str
    group_name: str


class InvalidBookmarkUrl(ValueError):
    """Raised when a bookmark URL is not a valid HTTP(S) URL."""


class InvalidBookmarkDetails(ValueError):
    """Raised when a bookmark name or group is invalid."""


class BookmarkLimitError(ValueError):
    """Raised when the shared URL list reaches its maximum size."""


class BookmarkStorageError(Exception):
    """Raised when the external bookmark database cannot be used."""


def normalize_bookmark_url(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidBookmarkUrl("URLを入力してください。")

    url = value.strip()
    if not url:
        raise InvalidBookmarkUrl("URLを入力してください。")
    if len(url) > MAX_BOOKMARK_URL_LENGTH:
        raise InvalidBookmarkUrl(
            f"URLは{MAX_BOOKMARK_URL_LENGTH}文字以内で入力してください。"
        )
    if any(character.isspace() for character in url):
        raise InvalidBookmarkUrl("URLに空白を含めないでください。")

    try:
        parsed_url = urlsplit(url)
        hostname = parsed_url.hostname
        parsed_url.port
    except ValueError as error:
        raise InvalidBookmarkUrl("有効なサイトURLを入力してください。") from error

    if (
        parsed_url.scheme.lower() not in {"http", "https"}
        or not parsed_url.netloc
        or not hostname
    ):
        raise InvalidBookmarkUrl(
            "URLは http:// または https:// から始まる有効なサイトURLを入力してください。"
        )
    return url


def _normalize_bookmark_details(
    site_name: object,
    group_name: object,
    url: str,
) -> tuple[str, str]:
    if not isinstance(site_name, str):
        raise InvalidBookmarkDetails("サイト名を文字列で入力してください。")
    normalized_name = site_name.strip() or urlsplit(url).hostname or url
    if len(normalized_name) > MAX_BOOKMARK_NAME_LENGTH:
        raise InvalidBookmarkDetails(
            f"サイト名は{MAX_BOOKMARK_NAME_LENGTH}文字以内で入力してください。"
        )

    if not isinstance(group_name, str):
        raise InvalidBookmarkDetails("グループ名を文字列で入力してください。")
    normalized_group = group_name.strip() or DEFAULT_BOOKMARK_GROUP
    if len(normalized_group) > MAX_BOOKMARK_GROUP_LENGTH:
        raise InvalidBookmarkDetails(
            f"グループ名は{MAX_BOOKMARK_GROUP_LENGTH}文字以内で入力してください。"
        )
    if normalized_group == ALL_BOOKMARKS_TAB:
        raise InvalidBookmarkDetails(
            f"「{ALL_BOOKMARKS_TAB}」は一覧タブに使用しているため、グループ名にできません。"
        )
    return normalized_name, normalized_group


def _open_turso_connection() -> turso_serverless.Connection:
    database_url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    auth_token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    if not database_url or not auth_token:
        raise BookmarkStorageError(
            "Tursoの保存先が未設定です。TURSO_DATABASE_URLとTURSO_AUTH_TOKENを設定してください。"
        )

    return turso_serverless.connect(url=database_url, auth_token=auth_token)


def _ensure_schema(connection: turso_serverless.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS fitting_bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE CHECK (length(url) <= 2048),
            site_name TEXT NOT NULL DEFAULT '',
            group_name TEXT NOT NULL DEFAULT '未分類'
        )
        """
    )
    columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(fitting_bookmarks)"
        ).fetchall()
    }
    if "site_name" not in columns:
        connection.execute(
            "ALTER TABLE fitting_bookmarks "
            "ADD COLUMN site_name TEXT NOT NULL DEFAULT ''"
        )
    if "group_name" not in columns:
        connection.execute(
            "ALTER TABLE fitting_bookmarks "
            "ADD COLUMN group_name TEXT NOT NULL DEFAULT '未分類'"
        )


def _load_unlocked(connection: turso_serverless.Connection) -> list[Bookmark]:
    rows = connection.execute(
        """
        SELECT id, url, site_name, group_name
        FROM fitting_bookmarks
        ORDER BY id DESC
        """
    ).fetchall()
    if len(rows) > MAX_BOOKMARKS:
        raise BookmarkStorageError(
            f"URLリストが上限の{MAX_BOOKMARKS}件を超えています。"
        )

    bookmarks = []
    try:
        for row in rows:
            bookmark_id = int(row[0])
            url = normalize_bookmark_url(row[1])
            site_name, group_name = _normalize_bookmark_details(
                row[2],
                row[3],
                url,
            )
            bookmarks.append(
                Bookmark(
                    id=bookmark_id,
                    url=url,
                    site_name=site_name,
                    group_name=group_name,
                )
            )
    except (IndexError, TypeError, ValueError) as error:
        raise BookmarkStorageError(
            "データベースに不正なブックマーク情報が保存されているため読み込めませんでした。"
        ) from error
    return bookmarks


def _run_database(
    operation: Callable[[turso_serverless.Connection], _Result],
) -> _Result:
    try:
        with _DATABASE_LOCK:
            connection = _open_turso_connection()
            try:
                _ensure_schema(connection)
                result = operation(connection)
                connection.commit()
                return result
            finally:
                connection.close()
    except BookmarkStorageError:
        raise
    except turso_serverless.Error as error:
        raise BookmarkStorageError(
            "Tursoデータベースを操作できませんでした。接続設定とデータベースの状態を確認してください。"
        ) from error


def load_bookmarks() -> list[Bookmark]:
    return _run_database(_load_unlocked)


def add_bookmark(
    value: object,
    site_name: object = "",
    group_name: object = DEFAULT_BOOKMARK_GROUP,
) -> tuple[list[Bookmark], bool]:
    url = normalize_bookmark_url(value)
    normalized_name, normalized_group = _normalize_bookmark_details(
        site_name,
        group_name,
        url,
    )

    def add(
        connection: turso_serverless.Connection,
    ) -> tuple[list[Bookmark], bool]:
        bookmarks = _load_unlocked(connection)
        if any(bookmark.url == url for bookmark in bookmarks):
            return bookmarks, False
        if len(bookmarks) >= MAX_BOOKMARKS:
            raise BookmarkLimitError(
                f"URLは最大{MAX_BOOKMARKS}件まで登録できます。"
            )

        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO fitting_bookmarks (url, site_name, group_name)
            SELECT ?, ?, ? WHERE (
                SELECT COUNT(*) FROM fitting_bookmarks
            ) < ?
            """,
            (url, normalized_name, normalized_group, MAX_BOOKMARKS),
        )
        if cursor.rowcount == 1:
            return _load_unlocked(connection), True

        updated_bookmarks = _load_unlocked(connection)
        if any(bookmark.url == url for bookmark in updated_bookmarks):
            return updated_bookmarks, False
        raise BookmarkLimitError(
            f"URLは最大{MAX_BOOKMARKS}件まで登録できます。"
        )

    return _run_database(add)


def update_bookmark(
    value: object,
    site_name: object,
    group_name: object,
) -> bool:
    url = normalize_bookmark_url(value)
    normalized_name, normalized_group = _normalize_bookmark_details(
        site_name,
        group_name,
        url,
    )

    def update(connection: turso_serverless.Connection) -> bool:
        cursor = connection.execute(
            """
            UPDATE fitting_bookmarks
            SET site_name = ?, group_name = ?
            WHERE url = ?
            """,
            (normalized_name, normalized_group, url),
        )
        return cursor.rowcount == 1

    return _run_database(update)


def delete_bookmark(value: object) -> tuple[list[Bookmark], bool]:
    url = normalize_bookmark_url(value)

    def delete(
        connection: turso_serverless.Connection,
    ) -> tuple[list[Bookmark], bool]:
        bookmarks = _load_unlocked(connection)
        if not any(bookmark.url == url for bookmark in bookmarks):
            return bookmarks, False

        connection.execute(
            "DELETE FROM fitting_bookmarks WHERE url = ?",
            (url,),
        )
        return _load_unlocked(connection), True

    return _run_database(delete)
