import os
from collections.abc import Callable
from threading import RLock
from typing import TypeVar
from urllib.parse import urlsplit

import turso_serverless


MAX_BOOKMARK_URL_LENGTH = 2048
MAX_BOOKMARKS = 1000
_DATABASE_LOCK = RLock()
_Result = TypeVar("_Result")


class InvalidBookmarkUrl(ValueError):
    """Raised when a bookmark URL is not a valid HTTP(S) URL."""


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
            url TEXT NOT NULL UNIQUE CHECK (length(url) <= 2048)
        )
        """
    )


def _load_unlocked(connection: turso_serverless.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT url FROM fitting_bookmarks ORDER BY id DESC"
    ).fetchall()
    if len(rows) > MAX_BOOKMARKS:
        raise BookmarkStorageError(
            f"URLリストが上限の{MAX_BOOKMARKS}件を超えています。"
        )

    bookmarks = []
    try:
        for row in rows:
            bookmarks.append(normalize_bookmark_url(row[0]))
    except (InvalidBookmarkUrl, IndexError, TypeError) as error:
        raise BookmarkStorageError(
            "データベースに不正なURLが保存されているため読み込めませんでした。"
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


def load_bookmarks() -> list[str]:
    return _run_database(_load_unlocked)


def add_bookmark(value: object) -> tuple[list[str], bool]:
    url = normalize_bookmark_url(value)

    def add(connection: turso_serverless.Connection) -> tuple[list[str], bool]:
        bookmarks = _load_unlocked(connection)
        if url in bookmarks:
            return bookmarks, False
        if len(bookmarks) >= MAX_BOOKMARKS:
            raise BookmarkLimitError(
                f"URLは最大{MAX_BOOKMARKS}件まで登録できます。"
            )

        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO fitting_bookmarks (url)
            SELECT ? WHERE (
                SELECT COUNT(*) FROM fitting_bookmarks
            ) < ?
            """,
            (url, MAX_BOOKMARKS),
        )
        if cursor.rowcount == 1:
            return [url, *bookmarks], True

        updated_bookmarks = _load_unlocked(connection)
        if url in updated_bookmarks:
            return updated_bookmarks, False
        raise BookmarkLimitError(
            f"URLは最大{MAX_BOOKMARKS}件まで登録できます。"
        )

    return _run_database(add)


def delete_bookmark(value: object) -> tuple[list[str], bool]:
    url = normalize_bookmark_url(value)

    def delete(connection: turso_serverless.Connection) -> tuple[list[str], bool]:
        bookmarks = _load_unlocked(connection)
        if url not in bookmarks:
            return bookmarks, False

        connection.execute(
            "DELETE FROM fitting_bookmarks WHERE url = ?",
            (url,),
        )
        return _load_unlocked(connection), True

    return _run_database(delete)
