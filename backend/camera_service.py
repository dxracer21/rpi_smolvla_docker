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

JOINT_NAMES = (
    "joint1",
    "joint2",
    "joint3",
    "joint4",
    "joint5",
    "joint6",
    "rh_r1_joint",
)

JOINT_LIMITS = (
    (-6.28318530718, 6.28318530718),
    (-6.28318530718, 6.28318530718),
    (-6.28318530718, 6.28318530718),
    (-6.28318530718, 6.28318530718),
    (-6.28318530718, 6.28318530718),
    (-6.28318530718, 6.28318530718),
    (0.0, 1.13514578304),
)
COMMAND_TOPIC = "/leader/joint_trajectory"
MAX_COMMAND_DELTA_RAD = 0.08
MAX_OBSERVATION_DRIFT_RAD = 0.05
COMMAND_DURATION_SECONDS = 2


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
        self._frames: dict[str, tuple[int, float, bytes]] = {}
        self._joint_state: tuple[float, dict[str, float]] | None = None
        self._trajectory_publisher: Any = None
        self._started = False

    def start(self) -> None:
        with self._condition:
            if self._started:
                return
            self._started = True
        threading.Thread(target=self._spin, name="camera-preview-ros", daemon=True).start()

    @staticmethod
    def topic(name: str) -> str:
        if name not in CAMERAS:
            raise ValueError(f"Unknown camera: {name}")
        return str(CAMERAS[name]["topic"])

    def wait(self, name: str, sequence: int, timeout: float = 3.0) -> tuple[int, bytes] | None:
        self.start()
        deadline = time.monotonic() + timeout
        with self._condition:
            while time.monotonic() < deadline:
                frame = self._frames.get(name)
                if frame and frame[0] > sequence:
                    return frame[0], frame[2]
                self._condition.wait(deadline - time.monotonic())
        return None

    def latest(self, name: str, max_age: float = 2.0, timeout: float = 5.0) -> tuple[bytes, float]:
        """Return a recent JPEG and its age, waiting briefly for a live frame."""
        if name not in CAMERAS:
            raise ValueError(f"Unknown camera: {name}")
        self.start()
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                frame = self._frames.get(name)
                if frame:
                    age = time.monotonic() - frame[1]
                    if age <= max_age:
                        return frame[2], age
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    topic = CAMERAS[name]["topic"]
                    raise TimeoutError(f"No fresh {name} frame received from {topic}")
                self._condition.wait(remaining)

    def latest_joint_positions(
        self, max_age: float = 1.0, timeout: float = 5.0
    ) -> tuple[list[float], float]:
        """Return positions ordered exactly as the trained seven-joint state."""
        self.start()
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                if self._joint_state:
                    received_at, positions = self._joint_state
                    age = time.monotonic() - received_at
                    missing = [name for name in JOINT_NAMES if name not in positions]
                    if age <= max_age and not missing:
                        return [positions[name] for name in JOINT_NAMES], age
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("No fresh complete /joint_states message received")
                self._condition.wait(remaining)

    def publish_safety_limited_action(
        self, requested: list[float], observed: list[float]
    ) -> dict[str, Any]:
        """Publish one bounded trajectory after validating fresh robot state."""
        import math
        from builtin_interfaces.msg import Duration
        from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

        if len(requested) != len(JOINT_NAMES) or not all(math.isfinite(v) for v in requested):
            raise RuntimeError("Model action must contain seven finite joint values")
        current, age = self.latest_joint_positions(max_age=0.5)
        drift = [abs(now - before) for now, before in zip(current, observed, strict=True)]
        if max(drift) > MAX_OBSERVATION_DRIFT_RAD:
            raise RuntimeError(
                f"Robot moved during inference (max drift {max(drift):.4f} rad); command cancelled"
            )

        commanded: list[float] = []
        for target, now, (lower, upper) in zip(requested, current, JOINT_LIMITS, strict=True):
            limited_target = min(max(float(target), lower), upper)
            delta = min(max(limited_target - now, -MAX_COMMAND_DELTA_RAD), MAX_COMMAND_DELTA_RAD)
            commanded.append(now + delta)

        with self._condition:
            publisher = self._trajectory_publisher
        if publisher is None:
            raise RuntimeError("Robot trajectory publisher is not ready")
        if publisher.get_subscription_count() < 1:
            raise RuntimeError(f"No controller subscribes to {COMMAND_TOPIC}")

        message = JointTrajectory()
        message.joint_names = list(JOINT_NAMES)
        point = JointTrajectoryPoint()
        point.positions = commanded
        point.time_from_start = Duration(sec=COMMAND_DURATION_SECONDS)
        message.points = [point]
        publisher.publish(message)
        return {
            "published": True,
            "topic": COMMAND_TOPIC,
            "requested_positions": [float(value) for value in requested],
            "current_positions": current,
            "commanded_positions": commanded,
            "max_delta_rad": MAX_COMMAND_DELTA_RAD,
            "duration_seconds": COMMAND_DURATION_SECONDS,
            "joint_state_age_seconds": round(age, 4),
            "max_observation_drift_rad": round(max(drift), 4),
        }

    def _spin(self) -> None:
        import rclpy
        from rclpy.node import Node
        from sensor_msgs.msg import CompressedImage
        from sensor_msgs.msg import JointState
        from trajectory_msgs.msg import JointTrajectory

        rclpy.init(args=None)
        node = Node("smolvla_camera_web_preview")
        for name, config in CAMERAS.items():
            node.create_subscription(
                CompressedImage,
                config["topic"],
                lambda message, camera=name: self._receive(camera, message),
                1,
            )
        node.create_subscription(JointState, "/joint_states", self._receive_joint_state, 10)
        with self._condition:
            self._trajectory_publisher = node.create_publisher(
                JointTrajectory, COMMAND_TOPIC, 10
            )
            self._condition.notify_all()
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
            sequence = self._frames.get(name, (0, 0.0, b""))[0] + 1
            self._frames[name] = (sequence, time.monotonic(), jpeg)
            self._condition.notify_all()

    def _receive_joint_state(self, message: Any) -> None:
        positions = {
            name: float(position)
            for name, position in zip(message.name, message.position, strict=False)
        }
        with self._condition:
            self._joint_state = (time.monotonic(), positions)
            self._condition.notify_all()
