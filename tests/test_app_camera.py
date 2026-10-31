import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from weather import WeatherDataError


APP_FILE = Path(__file__).resolve().parents[1] / "app.py"


class CameraCaptureTests(unittest.TestCase):
    def test_multiple_camera_photos_can_be_added(self):
        image = Image.new("RGB", (32, 24), color="#7799aa")
        output = BytesIO()
        image.save(output, format="PNG")
        photo_bytes = output.getvalue()

        with (
            patch("weather.get_weather", side_effect=WeatherDataError("offline")),
            patch(
                "weather.get_historical_monthly_average",
                side_effect=WeatherDataError("offline"),
            ),
            patch("streamlit.camera_input", return_value=BytesIO(photo_bytes)),
        ):
            app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
            app.radio[0].set_value("カメラで撮影").run()
            app.button(key="add_camera_photo_0").click().run()
            app.button(key="add_camera_photo_1").click().run()

        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.session_state["camera_photos"], [photo_bytes, photo_bytes])
        self.assertEqual(app.session_state["camera_capture_index"], 2)


if __name__ == "__main__":
    unittest.main()
