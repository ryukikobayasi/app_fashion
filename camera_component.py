import base64
import binascii
from typing import Literal

import streamlit as st

from photo_recommender import MAX_IMAGE_BYTES


_DATA_URL_PREFIX = "data:image/jpeg;base64,"
_MAX_DATA_URL_LENGTH = len(_DATA_URL_PREFIX) + 4 * ((MAX_IMAGE_BYTES + 2) // 3)

_CAMERA_HTML = """
<div class="camera-widget">
  <div class="camera-frame">
    <video id="camera-video" autoplay playsinline muted aria-label="カメラの映像"></video>
    <img id="camera-snapshot" alt="撮影した写真のプレビュー" hidden />
    <canvas id="camera-canvas" hidden></canvas>
  </div>
  <div class="camera-controls">
    <button id="camera-switch" type="button">前後カメラを切り替え</button>
    <button id="camera-capture" class="primary" type="button" disabled>撮影</button>
    <button id="camera-retry" type="button" hidden>カメラを再試行</button>
    <button id="camera-retake" type="button" hidden>撮り直す</button>
    <button id="camera-add" class="primary" type="button" hidden>撮影した写真を追加</button>
  </div>
  <p id="camera-status" role="status" aria-live="polite">カメラを起動しています。</p>
</div>
"""

_CAMERA_CSS = """
.camera-widget {
  color: var(--st-text-color, #262730);
  font-family: var(--st-font, sans-serif);
}
.camera-frame {
  width: 100%;
  aspect-ratio: 4 / 3;
  max-height: 70vh;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--st-base-radius, 0.5rem);
  background: #111;
}
.camera-frame video,
.camera-frame img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.camera-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
.camera-controls button {
  border: 1px solid var(--st-border-color, #d6d6d8);
  border-radius: var(--st-base-radius, 0.5rem);
  padding: 0.5rem 0.8rem;
  color: var(--st-text-color, #262730);
  background: var(--st-secondary-background-color, #f0f2f6);
  font: inherit;
  cursor: pointer;
}
.camera-controls button.primary {
  border-color: var(--st-primary-color, #ff4b4b);
  color: #fff;
  background: var(--st-primary-color, #ff4b4b);
}
.camera-controls button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.camera-controls button[hidden] {
  display: none;
}
#camera-status {
  min-height: 1.4rem;
  margin: 0.6rem 0 0;
  color: var(--st-text-color, #262730);
  font-size: 0.9rem;
}
"""

_CAMERA_JS = """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  const video = parentElement.querySelector("#camera-video")
  const snapshot = parentElement.querySelector("#camera-snapshot")
  const canvas = parentElement.querySelector("#camera-canvas")
  const switchButton = parentElement.querySelector("#camera-switch")
  const captureButton = parentElement.querySelector("#camera-capture")
  const retryButton = parentElement.querySelector("#camera-retry")
  const retakeButton = parentElement.querySelector("#camera-retake")
  const addButton = parentElement.querySelector("#camera-add")
  const status = parentElement.querySelector("#camera-status")

  if (!video || !snapshot || !canvas || !switchButton || !captureButton ||
      !retryButton || !retakeButton || !addButton || !status) {
    return
  }

  const stateKey = "__fittingCameraState"
  let state = parentElement[stateKey]

  if (!state) {
    state = {
      facingMode: data?.initial_facing_mode || "environment",
      resetToken: data?.reset_token ?? 0,
      requestId: 0,
      starting: false,
      stream: null,
      capturedDataUrl: null,
      setTriggerValue,
      listeners: new AbortController(),
    }
    parentElement[stateKey] = state

    const setStatus = (message) => {
      status.textContent = message
    }

    const stopStream = () => {
      if (state.stream) {
        state.stream.getTracks().forEach((track) => track.stop())
        state.stream = null
      }
      video.srcObject = null
    }

    const startCamera = async () => {
      const requestId = ++state.requestId
      state.starting = true
      captureButton.disabled = true
      retryButton.hidden = true
      setStatus(state.facingMode === "environment"
        ? "背面カメラを起動しています。"
        : "前面カメラを起動しています。")
      stopStream()

      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        state.starting = false
        retryButton.hidden = false
        setStatus("このブラウザーではカメラを使えません。HTTPS接続とカメラ権限を確認してください。")
        return
      }

      const videoOptions = {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        facingMode: { exact: state.facingMode },
      }

      try {
        let stream
        let usedFallbackCamera = false
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: videoOptions,
            audio: false,
          })
        } catch (error) {
          if (!["NotFoundError", "OverconstrainedError"].includes(error.name)) {
            throw error
          }
          usedFallbackCamera = true
          stream = await navigator.mediaDevices.getUserMedia({
            video: {
              width: { ideal: 1280 },
              height: { ideal: 720 },
            },
            audio: false,
          })
        }

        if (requestId !== state.requestId) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }

        state.stream = stream
        video.srcObject = stream
        video.hidden = false
        await video.play()
        state.starting = false
        captureButton.disabled = video.videoWidth === 0

        const track = stream.getVideoTracks()[0]
        const actualFacingMode = track && track.getSettings
          ? track.getSettings().facingMode
          : null
        if (usedFallbackCamera) {
          const direction = state.facingMode === "environment" ? "背面" : "前面"
          setStatus(`${direction}カメラを利用できないため、利用可能なカメラで撮影します。`)
        } else if (actualFacingMode && actualFacingMode !== state.facingMode) {
          setStatus("指定した向きのカメラを利用できないため、別のカメラで撮影します。")
        } else if (state.facingMode === "environment") {
          setStatus("背面カメラで撮影できます。")
        } else {
          setStatus("前面カメラで撮影できます。")
        }
      } catch (error) {
        if (requestId !== state.requestId) {
          return
        }
        state.starting = false
        retryButton.hidden = false
        if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
          setStatus("カメラの使用が許可されていません。ブラウザーの設定でカメラを許可してください。")
        } else if (error.name === "NotFoundError") {
          setStatus("カメラが見つかりません。カメラを接続して再試行してください。")
        } else {
          setStatus("カメラを起動できませんでした。権限を確認して再試行してください。")
        }
      }
    }

    state.startCamera = startCamera
    state.stopStream = stopStream
    video.onloadedmetadata = () => {
      if (!state.capturedDataUrl) {
        captureButton.disabled = false
      }
    }

    switchButton.addEventListener("click", () => {
      if (state.capturedDataUrl) {
        return
      }
      state.facingMode = state.facingMode === "environment" ? "user" : "environment"
      state.startCamera()
    }, { signal: state.listeners.signal })

    retryButton.addEventListener("click", () => {
      state.startCamera()
    }, { signal: state.listeners.signal })

    captureButton.addEventListener("click", () => {
      if (!video.videoWidth || !video.videoHeight) {
        setStatus("カメラ映像を準備しています。少し待ってから撮影してください。")
        return
      }
      const scale = Math.min(1, 1280 / Math.max(video.videoWidth, video.videoHeight))
      canvas.width = Math.round(video.videoWidth * scale)
      canvas.height = Math.round(video.videoHeight * scale)
      const context = canvas.getContext("2d")
      if (!context) {
        setStatus("写真を準備できませんでした。カメラを再起動してください。")
        return
      }
      context.drawImage(video, 0, 0, canvas.width, canvas.height)
      state.capturedDataUrl = canvas.toDataURL("image/jpeg", 0.9)
      snapshot.src = state.capturedDataUrl
      snapshot.hidden = false
      video.hidden = true
      switchButton.disabled = true
      captureButton.hidden = true
      retakeButton.hidden = false
      addButton.hidden = false
      setStatus("写真を確認し、「撮影した写真を追加」を押してください。")
    }, { signal: state.listeners.signal })

    retakeButton.addEventListener("click", () => {
      state.capturedDataUrl = null
      snapshot.removeAttribute("src")
      snapshot.hidden = true
      video.hidden = false
      switchButton.disabled = false
      captureButton.hidden = false
      captureButton.disabled = !state.stream
      retakeButton.hidden = true
      addButton.hidden = true
      setStatus("撮り直す写真を撮影してください。")
    }, { signal: state.listeners.signal })

    addButton.addEventListener("click", () => {
      if (!state.capturedDataUrl) {
        return
      }
      addButton.disabled = true
      setStatus("写真を追加しています。")
      state.setTriggerValue("photo_added", state.capturedDataUrl)
      state.capturedDataUrl = null
      snapshot.removeAttribute("src")
      snapshot.hidden = true
      video.hidden = false
      switchButton.disabled = false
      captureButton.hidden = false
      captureButton.disabled = !state.stream
      retakeButton.hidden = true
      addButton.hidden = true
      addButton.disabled = false
      setStatus("次の写真を撮影できます。")
    }, { signal: state.listeners.signal })

    state.startCamera()
  }

  state.setTriggerValue = setTriggerValue
  if (state.resetToken !== (data?.reset_token ?? 0)) {
    state.resetToken = data?.reset_token ?? 0
    state.capturedDataUrl = null
    snapshot.removeAttribute("src")
    snapshot.hidden = true
    video.hidden = false
    switchButton.disabled = false
    captureButton.hidden = false
    captureButton.disabled = !state.stream
    retakeButton.hidden = true
    addButton.hidden = true
    addButton.disabled = false
    if (state.stream) {
      status.textContent = "次の写真を撮影できます。"
    }
  }

  return () => {
    state.requestId += 1
    state.listeners.abort()
    state.stopStream()
    delete parentElement[stateKey]
  }
}
"""

_CAMERA_COMPONENT = st.components.v2.component(
    "fitting_rear_camera",
    html=_CAMERA_HTML,
    css=_CAMERA_CSS,
    js=_CAMERA_JS,
)


class CameraCaptureError(ValueError):
    """Raised when a camera component result is malformed."""


def capture_camera_photo(
    *,
    reset_token: int,
    key: str = "wardrobe-camera",
    initial_facing_mode: Literal["environment", "user"] = "environment",
):
    if initial_facing_mode not in ("environment", "user"):
        raise ValueError("initial_facing_mode must be 'environment' or 'user'.")

    return _CAMERA_COMPONENT(
        key=key,
        data={"reset_token": reset_token, "initial_facing_mode": initial_facing_mode},
        on_photo_added_change=lambda: None,
    )


def decode_camera_photo(data_url: object) -> bytes:
    if not isinstance(data_url, str) or not data_url.startswith(_DATA_URL_PREFIX):
        raise CameraCaptureError("カメラ写真のデータを読み取れませんでした。もう一度撮影してください。")
    if len(data_url) > _MAX_DATA_URL_LENGTH:
        raise CameraCaptureError("撮影した写真は30MB以下にしてください。")

    try:
        image_bytes = base64.b64decode(data_url[len(_DATA_URL_PREFIX):], validate=True)
    except (binascii.Error, ValueError) as error:
        raise CameraCaptureError("カメラ写真のデータが壊れています。もう一度撮影してください。") from error

    if not image_bytes:
        raise CameraCaptureError("カメラ写真のデータが空です。もう一度撮影してください。")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise CameraCaptureError("撮影した写真は30MB以下にしてください。")
    return image_bytes
