import unittest
from unittest.mock import patch

from camera_component import _CAMERA_CSS, capture_camera_photo


class CameraComponentTests(unittest.TestCase):
    @patch("camera_component._CAMERA_COMPONENT")
    def test_rear_camera_remains_the_default(self, component):
        capture_camera_photo(reset_token=0)

        self.assertEqual(
            component.call_args.kwargs["data"]["initial_facing_mode"],
            "environment",
        )

    @patch("camera_component._CAMERA_COMPONENT")
    def test_selfie_page_can_start_with_the_front_camera(self, component):
        capture_camera_photo(
            reset_token=0,
            key="hairstyle-selfie",
            initial_facing_mode="user",
        )

        self.assertEqual(component.call_args.kwargs["key"], "hairstyle-selfie")
        self.assertEqual(component.call_args.kwargs["data"]["initial_facing_mode"], "user")

    def test_rejects_unsupported_camera_direction(self):
        with self.assertRaisesRegex(ValueError, "initial_facing_mode"):
            capture_camera_photo(reset_token=0, initial_facing_mode="sideways")

    def test_preview_size_is_capped_for_both_camera_modes(self):
        self.assertIn("max-width: 480px;", _CAMERA_CSS)
        self.assertIn("max-height: 45vh;", _CAMERA_CSS)


if __name__ == "__main__":
    unittest.main()
