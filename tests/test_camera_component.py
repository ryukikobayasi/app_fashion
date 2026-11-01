import unittest
from unittest.mock import patch

from camera_component import _CAMERA_CSS, _CAMERA_JS, capture_camera_photo


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
        self.assertIn("aspect-ratio: 3 / 4;", _CAMERA_CSS)
        self.assertIn("max-height: 65vh;", _CAMERA_CSS)
        self.assertIn("object-fit: cover;", _CAMERA_CSS)
        self.assertIn(".camera-frame [hidden]", _CAMERA_CSS)
        self.assertIn("display: none !important;", _CAMERA_CSS)

    def test_mobile_prefers_a_portrait_camera_resolution(self):
        self.assertIn(
            'window.matchMedia("(max-width: 640px)").matches',
            _CAMERA_JS,
        )
        self.assertIn("width: { ideal: 720 }, height: { ideal: 960 }", _CAMERA_JS)
        self.assertIn("width: { ideal: 960 }, height: { ideal: 1280 }", _CAMERA_JS)
        self.assertIn("aspectRatio: { ideal: portraitAspectRatio }", _CAMERA_JS)

    def test_preview_and_capture_keep_a_portrait_aspect_ratio(self):
        self.assertIn(
            "const portraitAspectRatio = 3 / 4",
            _CAMERA_JS,
        )
        self.assertIn(
            'frame.style.aspectRatio = "3 / 4"',
            _CAMERA_JS,
        )
        self.assertIn(
            "const sourceAspectRatio = video.videoWidth / video.videoHeight",
            _CAMERA_JS,
        )
        self.assertIn(
            "sourceX = (video.videoWidth - sourceWidth) / 2",
            _CAMERA_JS,
        )
        self.assertIn(
            "sourceY = (video.videoHeight - sourceHeight) / 2",
            _CAMERA_JS,
        )
        self.assertIn(
            "context.drawImage(\n        video,\n        sourceX,\n        sourceY,",
            _CAMERA_JS,
        )


if __name__ == "__main__":
    unittest.main()
