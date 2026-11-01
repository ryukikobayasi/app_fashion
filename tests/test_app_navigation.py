import base64
import os
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from bookmark_store import Bookmark
from weather import WeatherDataError


APP_FILE = Path(__file__).resolve().parents[1] / "app.py"


def make_jpeg():
    image = Image.new("RGB", (16, 24), color="#7890ab")
    output = BytesIO()
    image.save(output, format="JPEG")
    image.close()
    return output.getvalue()


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
            any("写真なしの今日のおすすめ15コーデ" in title.value for title in app.subheader)
        )
        self.assertFalse(
            any(button.label == "写真から8コーデを提案" for button in app.button)
        )
        self.assertEqual(
            sum(button.label == "このコーデのイメージ画像を生成" for button in app.button),
            15,
        )

    def test_no_photo_image_is_generated_only_for_the_selected_look(self):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "data": [
                {
                    "b64_json": base64.b64encode(make_jpeg()).decode("ascii"),
                }
            ]
        }
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-image-key"}),
            patch("weather.get_weather", side_effect=WeatherDataError("offline")),
            patch(
                "weather.get_historical_monthly_average",
                side_effect=WeatherDataError("offline"),
            ),
            patch("image_generator.requests.post", return_value=response) as image_request,
        ):
            app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
            image_request.assert_not_called()
            image_button = next(
                button
                for button in app.button
                if button.label == "このコーデのイメージ画像を生成"
            )
            image_button.click().run()

        self.assertFalse(app.exception, app.exception)
        image_request.assert_called_once()
        prompt = image_request.call_args.kwargs["json"]["prompt"]
        self.assertIn("No wardrobe photo was provided", prompt)

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
            patch("bookmark_store.load_bookmark_group_order", return_value=[]),
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
            patch(
                "bookmark_store.load_bookmark_group_order",
                side_effect=lambda group_names: list(group_names),
            ),
        ):
            app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
            app.switch_page(str(Path("app_pages") / "bookmarks.py")).run()

        self.assertFalse(app.exception, app.exception)
        self.assertTrue(any(widget.label == "サイト名" for widget in app.text_input))
        self.assertTrue(any(widget.label == "サイトURL" for widget in app.text_input))
        self.assertTrue(
            any(widget.label == "登録済みグループ" for widget in app.selectbox)
        )
        self.assertTrue(
            any(widget.label == "新しいグループ名（任意）" for widget in app.text_input)
        )
        self.assertTrue(any(button.label == "上へ" for button in app.button))
        self.assertTrue(any(button.label == "下へ" for button in app.button))
        self.assertTrue(any(button.label == "1つ上へ" for button in app.button))
        self.assertTrue(any(button.label == "1つ下へ" for button in app.button))
        self.assertTrue(any(button.label == "このサイトを削除" for button in app.button))

    def test_bookmarks_page_submits_edited_url_and_selected_group(self):
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
            patch(
                "bookmark_store.load_bookmark_group_order",
                side_effect=lambda group_names: list(group_names),
            ),
            patch("bookmark_store.update_bookmark", return_value=True) as update_bookmark,
        ):
            app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
            app.switch_page(str(Path("app_pages") / "bookmarks.py")).run()
            next(
                widget
                for widget in app.text_input
                if widget.key == "edit_bookmark_url_all_1"
            ).set_value("https://fashion-updated.example")
            next(
                widget
                for widget in app.selectbox
                if widget.key == "edit_bookmark_all_1_existing_group"
            ).set_value("ヘア")
            next(
                button
                for button in app.button
                if button.key == "save_bookmark_all_1"
            ).click().run()

        self.assertFalse(app.exception, app.exception)
        update_bookmark.assert_called_once_with(
            "https://fashion.example",
            "Fashion",
            "ヘア",
            new_url="https://fashion-updated.example",
        )

    def test_bookmarks_page_deletes_site_from_edit_section(self):
        bookmarks = [
            Bookmark(
                id=1,
                url="https://fashion.example",
                site_name="Fashion",
                group_name="コーデ",
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
            patch(
                "bookmark_store.load_bookmark_group_order",
                side_effect=lambda group_names: list(group_names),
            ),
            patch(
                "bookmark_store.delete_bookmark",
                return_value=([], True),
            ) as delete_bookmark,
        ):
            app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
            app.switch_page(str(Path("app_pages") / "bookmarks.py")).run()
            next(
                button
                for button in app.button
                if button.key == "delete_bookmark_all_1"
            ).click().run()

            self.assertTrue(
                any(
                    warning.value == "このサイトを削除しますか？"
                    for warning in app.warning
                )
            )
            delete_bookmark.assert_not_called()
            next(
                button
                for button in app.button
                if button.key == "confirm_bookmark_delete_all_1"
            ).click().run()

        self.assertFalse(app.exception, app.exception)
        delete_bookmark.assert_called_once_with("https://fashion.example")

    def test_bookmarks_page_persists_group_reordering(self):
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
            patch(
                "bookmark_store.load_bookmark_group_order",
                side_effect=lambda group_names: list(group_names),
            ),
            patch("bookmark_store.save_bookmark_group_order") as save_group_order,
        ):
            app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
            app.switch_page(str(Path("app_pages") / "bookmarks.py")).run()
            next(button for button in app.button if button.label == "下へ").click().run()

        self.assertFalse(app.exception, app.exception)
        save_group_order.assert_called_once_with(["ヘア", "コーデ"])

    def test_bookmarks_page_persists_site_reordering(self):
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
            patch(
                "bookmark_store.load_bookmark_group_order",
                side_effect=lambda group_names: list(group_names),
            ),
            patch("bookmark_store.save_bookmark_order") as save_bookmark_order,
        ):
            app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
            app.switch_page(str(Path("app_pages") / "bookmarks.py")).run()
            next(
                button
                for button in app.button
                if button.key == "move_bookmark_up_2"
            ).click().run()

        self.assertFalse(app.exception, app.exception)
        save_bookmark_order.assert_called_once_with([2, 1])

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
