import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from bookmark_store import Bookmark
from weather import WeatherDataError


APP_FILE = Path(__file__).resolve().parents[1] / "app.py"


class AppNavigationTests(unittest.TestCase):
    def test_wardrobe_recommends_without_a_photo(self):
        with (
            patch("weather.get_weather", side_effect=WeatherDataError("offline")),
            patch(
                "weather.get_historical_monthly_average",
                side_effect=WeatherDataError("offline"),
            ),
        ):
            app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()

        self.assertFalse(app.exception, app.exception)
        self.assertTrue(
            any("写真なしの今日のおすすめ5コーデ" in title.value for title in app.subheader)
        )
        self.assertFalse(
            any(button.label == "写真から8コーデを提案" for button in app.button)
        )

    def test_bookmarks_page_is_registered_and_renders(self):
        with (
            patch("weather.get_weather", side_effect=WeatherDataError("offline")),
            patch(
                "weather.get_historical_monthly_average",
                side_effect=WeatherDataError("offline"),
            ),
            patch(
                "camera_component.capture_camera_photo",
                return_value=SimpleNamespace(photo_added=None),
            ),
            patch("bookmark_store.load_bookmarks", return_value=[]) as load_bookmarks,
        ):
            app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
            app.switch_page(str(Path("app_pages") / "bookmarks.py")).run()

        self.assertFalse(app.exception, app.exception)
        self.assertTrue(any("お気に入りサイト" in title.value for title in app.title))
        self.assertFalse(any("利用者全員で共有" in item.value for item in app.warning))
        load_bookmarks.assert_called_once()

    def test_bookmarks_page_renders_group_tabs_and_edit_forms(self):
        bookmarks = [
            Bookmark(
                id=1,
                url="https://fashion.example",
                site_name="Fashion",
                group_name="コーデ",
            ),
            Bookmark(
                id=2,
                url="https://hair.example",
                site_name="Hair",
                group_name="ヘア",
            ),
        ]
        with (
            patch("weather.get_weather", side_effect=WeatherDataError("offline")),
            patch(
                "weather.get_historical_monthly_average",
                side_effect=WeatherDataError("offline"),
            ),
            patch(
                "camera_component.capture_camera_photo",
                return_value=SimpleNamespace(photo_added=None),
            ),
            patch("bookmark_store.load_bookmarks", return_value=bookmarks),
        ):
            app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
            app.switch_page(str(Path("app_pages") / "bookmarks.py")).run()

        self.assertFalse(app.exception, app.exception)
        self.assertTrue(any(widget.label == "サイト名" for widget in app.text_input))
        self.assertTrue(any(widget.label == "グループ" for widget in app.text_input))

    def test_hairstyle_page_is_registered_and_renders(self):
        with (
            patch("weather.get_weather", side_effect=WeatherDataError("offline")),
            patch(
                "weather.get_historical_monthly_average",
                side_effect=WeatherDataError("offline"),
            ),
            patch(
                "camera_component.capture_camera_photo",
                return_value=SimpleNamespace(photo_added=None),
            ) as camera_capture,
        ):
            app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
            app.switch_page(str(Path("app_pages") / "hairstyles.py")).run()

        self.assertFalse(app.exception, app.exception)
        self.assertTrue(any("自分に似合う" in title.value for title in app.title))
        self.assertEqual(
            camera_capture.call_args.kwargs["initial_facing_mode"],
            "user",
        )


if __name__ == "__main__":
    unittest.main()
