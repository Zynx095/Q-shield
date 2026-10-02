"""Frame sources. `read()` returns a BGR uint8 ndarray, or None when no frame could be read."""
from __future__ import annotations

from typing import Iterable, Protocol


class FrameSource(Protocol):
    def read(self): ...
    def release(self) -> None: ...


STREAM_SCHEMES = ("http://", "https://", "rtsp://", "rtmp://", "udp://", "tcp://")


def describe_source(source: int | str):
    """What a configured camera source is, for the observation's `source` field and the signer's source id:
    a device index is a local (USB or built-in) camera, a URL is a network camera stream (an ESP32-CAM serves MJPEG
    over HTTP), anything else is a video file. Returns (Source, source_id, live)."""
    from backend.protocol.observation import Source

    if isinstance(source, int):
        return Source.USB_WEBCAM, f"usb_webcam:{source}", True
    if source.lower().startswith(STREAM_SCHEMES):
        host = source.split("://", 1)[1].split("/", 1)[0].rsplit("@", 1)[-1]     # never keep credentials in an id
        return Source.NETWORK_CAMERA, f"network_camera:{host}", True
    return Source.VIDEO_FILE, "video_file", False


class OpenCVSource:
    """USB webcam (index), video file, or stream URL via OpenCV. Frames are not saved."""

    def __init__(self, source: int | str = 0, backend: str = "auto", width: int = 640, height: int = 480):
        import cv2

        api = {"auto": cv2.CAP_ANY, "dshow": getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY),
               "msmf": getattr(cv2, "CAP_MSMF", cv2.CAP_ANY)}[backend]
        self._cap = cv2.VideoCapture(source, api)
        if not self._cap.isOpened():
            self._cap.release()
            raise RuntimeError(f"cannot open camera source {source!r} (backend={backend})")
        if isinstance(source, int):  # request a size from live cameras only
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def read(self):
        ok, frame = self._cap.read()
        return frame if ok else None

    def release(self) -> None:
        self._cap.release()


def warm_up(source: FrameSource, frames: int) -> int:
    """Read and discard a live camera's first frames while auto-exposure and white balance settle.

    Webcams commonly deliver dark or black frames for about a second after opening. Fed to the camera-health monitor
    those read as an obstructed lens, and the resulting (signed) observation would cost the device trust before
    anything happened. A lens that is really covered stays dark after the warm-up and is still reported.
    Returns the number of frames read."""
    for _ in range(max(0, frames)):
        source.read()
    return max(0, frames)


class SequenceSource:
    """Yields preloaded frames (None entries simulate read failures); for tests and replays."""

    def __init__(self, frames: Iterable):
        self._it = iter(frames)

    def read(self):
        return next(self._it, None)

    def release(self) -> None:
        pass
