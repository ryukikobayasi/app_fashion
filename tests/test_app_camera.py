import base64
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from weather import WeatherDataError


APP_FILE = Path(__file__).resolve().parents[1] / "app.py"


class CameraCaptureTests(unittest.TestCase):
    def test_multiple_camera_photos_can_be_added(self):
        image = Image.new("RGB", (32, 24), color="#7799aa")
        output = BytesIO()
        image.save(output, format="JPEG")
        photo_bytes = output.getvalue()
        data_url = "data:image/jpeg;base64," + base64.b64encode(photo_bytes).decode("ascii")
        pending_photos = []

        def fake_camera_capture(**_):
            photo_added = pending_photos.pop(0) if pending_photos else None
            return SimpleNamespace(photo_added=photo_added)

        with (
            patch("weather.get_weather", side_effect=WeatherDataError("offline")),
            patch(
                "weather.get_historical_monthly_average",
                side_effect=WeatherDataError("offline"),
            ),
            patch("camera_component.capture_camera_photo", side_effect=fake_camera_capture),
        ):
            app = AppTest.from_file(str(APP_FILE), default_timeout=10).run()
            app.radio[0].set_value("カメラで撮影").run()
            pending_photos.append(data_url)
            app.run()
            pending_photos.append(data_url)
            app.run()

        self.assertFalse(app.exception, app.exception)
        self.assertEqual(app.session_state["camera_photos"], [photo_bytes, photo_bytes])
        self.assertEqual(app.session_state["camera_capture_index"], 2)


if __name__ == "__main__":
    unittest.main()
