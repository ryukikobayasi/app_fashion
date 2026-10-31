import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from weather import WeatherDataError


APP_FILE = Path(__file__).resolve().parents[1] / "app.py"


class AppNavigationTests(unittest.TestCase):
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
