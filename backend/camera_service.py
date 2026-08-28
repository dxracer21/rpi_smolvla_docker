"""Lifecycle and browser-preview support for the two ROS camera launches."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CAMERAS = {
    "realsense": {
        "label": "RealSense",
        "launch": "realsence_test.py",
        "topic": "/camera/cam_wrist/color/image_rect_raw/compressed",
    },
    "logitech": {
        "label": "Logitech",
        "launch": "logitech_test.py",
        "topic": "/camera/cam_front/color/image_rect_raw/compressed",
    },
}


@dataclass
class CameraProcess:
    process: subprocess.Popen[str] | None = None
    started_at: float | None = None
    error: str | None = None


class CameraService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cameras = {name: CameraProcess() for name in CAMERAS}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"cameras": {name: self._camera_status(name) for name in CAMERAS}}

    def start(self, name: str) -> dict[str, Any]:
        self._validate(name)
        with self._lock:
            state = self._cameras[name]
            if state.process and state.process.poll() is None:
                return self._camera_status(name)
            command = (
                "source /opt/ros/${ROS_DISTRO}/setup.bash && "
                "source /workspace/ros2_ws/install/setup.bash && "
                f"exec ros2 launch smolvla_camera_bringup {CAMERAS[name]['launch']}"
            )
            log_dir = Path("/workspace/results/camera_logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            log = open(log_dir / f"{name}.log", "a", encoding="utf-8")
            try:
                state.process = subprocess.Popen(
                    ["bash", "-lc", command],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
                state.started_at = time.time()
                state.error = None
            except Exception as error:
                log.close()
                state.error = str(error)
                raise
            return self._camera_status(name)

    def stop(self, name: str) -> dict[str, Any]:
        self._validate(name)
        with self._lock:
            state = self._cameras[name]
            process = state.process
            if process and process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=3)
            state.process = None
            state.started_at = None
            return self._camera_status(name)

    def restart(self, name: str) -> dict[str, Any]:
        self.stop(name)
        return self.start(name)

    def close(self) -> None:
        for name in CAMERAS:
            try:
                self.stop(name)
            except Exception:
                pass

    def _camera_status(self, name: str) -> dict[str, Any]:
        state = self._cameras[name]
        running = state.process is not None and state.process.poll() is None
        if state.process and not running and state.error is None:
            state.error = f"Launch exited with code {state.process.returncode}"
        return {
            "name": name,
            "label": CAMERAS[name]["label"],
            "state": "RUNNING" if running else "STOPPED",
            "topic": CAMERAS[name]["topic"],
            "pid": state.process.pid if running else None,
            "started_at": state.started_at if running else None,
            "error": state.error,
        }

    @staticmethod
    def _validate(name: str) -> None:
        if name not in CAMERAS:
            raise ValueError(f"Unknown camera: {name}")


class CameraFrames:
    """Forward ROS JPEG payloads directly into an MJPEG browser stream."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._frames: dict[str, tuple[int, bytes]] = {}
        self._started = False

    def start(self) -> None:
        with self._condition:
            if self._started:
                return
            self._started = True
        threading.Thread(target=self._spin, name="camera-preview-ros", daemon=True).start()

    def wait(self, name: str, sequence: int, timeout: float = 3.0) -> tuple[int, bytes] | None:
        self.start()
        deadline = time.monotonic() + timeout
        with self._condition:
            while time.monotonic() < deadline:
                frame = self._frames.get(name)
                if frame and frame[0] > sequence:
                    return frame
                self._condition.wait(deadline - time.monotonic())
        return None

    def _spin(self) -> None:
        import rclpy
        from rclpy.node import Node
        from sensor_msgs.msg import CompressedImage

        rclpy.init(args=None)
        node = Node("smolvla_camera_web_preview")
        for name, config in CAMERAS.items():
            node.create_subscription(
                CompressedImage,
                config["topic"],
                lambda message, camera=name: self._receive(camera, message),
                1,
            )
        try:
            rclpy.spin(node)
        finally:
            node.destroy_node()
            rclpy.shutdown()

    def _receive(self, name: str, message: Any) -> None:
        jpeg = bytes(message.data)
        if not jpeg:
            return
        with self._condition:
            sequence = self._frames.get(name, (0, b""))[0] + 1
            self._frames[name] = (sequence, jpeg)
            self._condition.notify_all()
