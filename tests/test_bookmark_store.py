import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import turso_serverless

from bookmark_store import (
    BookmarkLimitError,
    BookmarkStorageError,
    InvalidBookmarkUrl,
    add_bookmark,
    delete_bookmark,
    load_bookmarks,
)


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
        bookmarks, added = add_bookmark(" https://example.com ")
        self.assertTrue(added)
        self.assertEqual(bookmarks, ["https://example.com"])

        bookmarks, added = add_bookmark("https://fashion.example")
        self.assertTrue(added)
        self.assertEqual(
            bookmarks,
            ["https://fashion.example", "https://example.com"],
        )

        bookmarks, added = add_bookmark("https://example.com")
        self.assertFalse(added)
        self.assertEqual(
            bookmarks,
            ["https://fashion.example", "https://example.com"],
        )

    def test_delete_removes_existing_url_and_reports_missing_url(self):
        add_bookmark("https://example.com")
        add_bookmark("https://fashion.example")

        bookmarks, deleted = delete_bookmark("https://example.com")
        self.assertTrue(deleted)
        self.assertEqual(bookmarks, ["https://fashion.example"])

        bookmarks, deleted = delete_bookmark("https://example.com")
        self.assertFalse(deleted)
        self.assertEqual(bookmarks, ["https://fashion.example"])

    def test_rejects_non_http_urls(self):
        for url in ("", "ftp://example.com", "https://", "javascript:alert(1)"):
            with self.subTest(url=url):
                with self.assertRaises(InvalidBookmarkUrl):
                    add_bookmark(url)

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
