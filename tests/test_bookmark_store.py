import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import turso_serverless

from bookmark_store import (
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
    save_bookmark_group_order,
    save_bookmark_order,
    update_bookmark,
)


def _bookmark_details(bookmarks: list[Bookmark]) -> list[tuple[str, str, str]]:
    return [
        (bookmark.url, bookmark.site_name, bookmark.group_name)
        for bookmark in bookmarks
    ]


class BookmarkStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "bookmarks.db"
        self.connection_patch = patch(
            "bookmark_store._open_turso_connection",
            side_effect=lambda: sqlite3.connect(self.database_path),
        )
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)
        self.addCleanup(self.temp_directory.cleanup)

    def test_load_initializes_an_empty_database(self):
        self.assertEqual(load_bookmarks(), [])
        self.assertEqual(load_bookmarks(), [])

    def test_add_normalizes_deduplicates_and_keeps_newest_first(self):
        bookmarks, added = add_bookmark(
            " https://example.com ",
            "Example",
            "Style",
        )
        self.assertTrue(added)
        self.assertEqual(
            _bookmark_details(bookmarks),
            [("https://example.com", "Example", "Style")],
        )

        bookmarks, added = add_bookmark(
            "https://fashion.example",
            "Fashion",
            "Shopping",
        )
        self.assertTrue(added)
        self.assertEqual(
            _bookmark_details(bookmarks),
            [
                ("https://fashion.example", "Fashion", "Shopping"),
                ("https://example.com", "Example", "Style"),
            ],
        )

        bookmarks, added = add_bookmark(
            "https://example.com",
            "Renamed",
            "Other",
        )
        self.assertFalse(added)
        self.assertEqual(
            _bookmark_details(bookmarks),
            [
                ("https://fashion.example", "Fashion", "Shopping"),
                ("https://example.com", "Example", "Style"),
            ],
        )

    def test_empty_site_name_defaults_to_hostname_and_group(self):
        bookmarks, added = add_bookmark("https://example.com")

        self.assertTrue(added)
        self.assertEqual(
            _bookmark_details(bookmarks),
            [("https://example.com", "example.com", "未分類")],
        )

    def test_update_changes_site_name_and_group(self):
        add_bookmark("https://example.com", "Example", "未分類")

        self.assertTrue(
            update_bookmark("https://example.com", "Example Japan", "Fashion")
        )
        self.assertEqual(
            _bookmark_details(load_bookmarks()),
            [("https://example.com", "Example Japan", "Fashion")],
        )
        self.assertFalse(
            update_bookmark("https://missing.example", "Missing", "Other")
        )

    def test_update_changes_url(self):
        add_bookmark("https://example.com", "Example", "未分類")

        self.assertTrue(
            update_bookmark(
                "https://example.com",
                "Example Japan",
                "Fashion",
                new_url="https://fashion.example",
            )
        )
        self.assertEqual(
            _bookmark_details(load_bookmarks()),
            [("https://fashion.example", "Example Japan", "Fashion")],
        )

    def test_update_rejects_a_url_already_used_by_another_bookmark(self):
        add_bookmark("https://example.com", "Example", "Style")
        add_bookmark("https://fashion.example", "Fashion", "Shopping")

        with self.assertRaisesRegex(InvalidBookmarkUrl, "すでに登録"):
            update_bookmark(
                "https://example.com",
                "Example",
                "Style",
                new_url="https://fashion.example",
            )

        self.assertEqual(
            [bookmark.url for bookmark in load_bookmarks()],
            ["https://fashion.example", "https://example.com"],
        )

    def test_group_order_is_persisted_and_new_groups_are_appended(self):
        add_bookmark("https://example.com", "Example", "Style")
        add_bookmark("https://fashion.example", "Fashion", "Shopping")

        save_bookmark_group_order(["Shopping", "Style"])

        self.assertEqual(
            load_bookmark_group_order(["Style", "Shopping", "Hair"]),
            ["Shopping", "Style", "Hair"],
        )

    def test_group_order_rejects_duplicate_and_reserved_groups(self):
        with self.assertRaises(InvalidBookmarkDetails):
            save_bookmark_group_order(["Style", "Style"])
        with self.assertRaises(InvalidBookmarkDetails):
            save_bookmark_group_order(["すべて"])

    def test_bookmark_order_is_persisted(self):
        add_bookmark("https://example.com", "Example", "Style")
        add_bookmark("https://fashion.example", "Fashion", "Shopping")
        add_bookmark("https://hair.example", "Hair", "Beauty")
        bookmark_ids = {
            bookmark.url: bookmark.id
            for bookmark in load_bookmarks()
        }

        save_bookmark_order(
            [
                bookmark_ids["https://example.com"],
                bookmark_ids["https://fashion.example"],
                bookmark_ids["https://hair.example"],
            ]
        )

        self.assertEqual(
            [bookmark.url for bookmark in load_bookmarks()],
            [
                "https://example.com",
                "https://fashion.example",
                "https://hair.example",
            ],
        )

    def test_bookmark_order_requires_all_unique_existing_ids(self):
        add_bookmark("https://example.com", "Example", "Style")
        add_bookmark("https://fashion.example", "Fashion", "Shopping")
        bookmark_ids = [bookmark.id for bookmark in load_bookmarks()]

        with self.assertRaises(InvalidBookmarkOrder):
            save_bookmark_order([bookmark_ids[0], bookmark_ids[0]])
        with self.assertRaises(InvalidBookmarkOrder):
            save_bookmark_order(bookmark_ids[:1])

        self.assertEqual(
            [bookmark.id for bookmark in load_bookmarks()],
            bookmark_ids,
        )

    def test_delete_removes_existing_url_and_reports_missing_url(self):
        add_bookmark("https://example.com", "Example", "Style")
        add_bookmark("https://fashion.example", "Fashion", "Shopping")

        bookmarks, deleted = delete_bookmark("https://example.com")
        self.assertTrue(deleted)
        self.assertEqual(
            _bookmark_details(bookmarks),
            [("https://fashion.example", "Fashion", "Shopping")],
        )

        bookmarks, deleted = delete_bookmark("https://example.com")
        self.assertFalse(deleted)
        self.assertEqual(
            _bookmark_details(bookmarks),
            [("https://fashion.example", "Fashion", "Shopping")],
        )

    def test_migrates_existing_url_only_rows(self):
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                """
                CREATE TABLE fitting_bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE CHECK (length(url) <= 2048)
                )
                """
            )
            connection.execute(
                "INSERT INTO fitting_bookmarks (url) VALUES (?)",
                ("https://legacy.example",),
            )
            connection.execute(
                "INSERT INTO fitting_bookmarks (url) VALUES (?)",
                ("https://legacy-newer.example",),
            )
            connection.commit()
        finally:
            connection.close()

        bookmarks = load_bookmarks()
        self.assertEqual(
            _bookmark_details(bookmarks),
            [
                ("https://legacy-newer.example", "legacy-newer.example", "未分類"),
                ("https://legacy.example", "legacy.example", "未分類"),
            ],
        )

    def test_rejects_non_http_urls(self):
        for url in ("", "ftp://example.com", "https://", "javascript:alert(1)"):
            with self.subTest(url=url):
                with self.assertRaises(InvalidBookmarkUrl):
                    add_bookmark(url)

    def test_rejects_reserved_or_too_long_group_names(self):
        with self.assertRaises(InvalidBookmarkDetails):
            add_bookmark("https://example.com", "Example", "すべて")
        with self.assertRaises(InvalidBookmarkDetails):
            add_bookmark("https://example.com", "Example", "x" * 51)

    def test_enforces_maximum_bookmark_count(self):
        with patch("bookmark_store.MAX_BOOKMARKS", 1):
            add_bookmark("https://example.com")
            with self.assertRaises(BookmarkLimitError):
                add_bookmark("https://fashion.example")

    def test_wraps_remote_database_errors(self):
        with patch(
            "bookmark_store._open_turso_connection",
            side_effect=turso_serverless.OperationalError("offline"),
        ):
            with self.assertRaises(BookmarkStorageError):
                load_bookmarks()


class BookmarkStoreConfigurationTests(unittest.TestCase):
    def test_missing_credentials_produce_an_actionable_error(self):
        with (
            patch.dict(
                os.environ,
                {"TURSO_DATABASE_URL": "", "TURSO_AUTH_TOKEN": ""},
            ),
            patch("bookmark_store.turso_serverless.connect") as connect,
        ):
            with self.assertRaisesRegex(
                BookmarkStorageError,
                "TURSO_DATABASE_URL",
            ):
                load_bookmarks()

        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
