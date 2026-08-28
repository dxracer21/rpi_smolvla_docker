#!/usr/bin/env python3
"""Minimal local web server for the SmolVLA Raspberry Pi control panel."""

from __future__ import annotations

import json
import os
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


STATIC_DIR = Path(__file__).resolve().parent / "static"
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_DIR))

from backend.inference_service import (  # noqa: E402
    BackendBadRequest,
    BackendConflict,
    InferenceService,
)
from backend.system_metrics import SystemMetrics  # noqa: E402
from backend.camera_service import CAMERAS, CameraFrames, CameraService  # noqa: E402

HOST = os.getenv("SMOLVLA_UI_HOST", "0.0.0.0")
PORT = int(os.getenv("SMOLVLA_UI_PORT", "8000"))
METRICS = SystemMetrics()
CAMERA_SERVICE = CameraService()
CAMERA_FRAMES = CameraFrames()
SERVICE = InferenceService(camera_frames=CAMERA_FRAMES)


class SmolVLAHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path
        if path == "/api/health":
            self.send_json(
                {
                    "ok": True,
                    "service": "smolvla-ui",
                    "mode": "DRY_RUN",
                    "backend": "CONNECTED",
                    "model": SERVICE.status()["state"],
                    "robot": "DISCONNECTED",
                }
            )
            return
        if path == "/api/status":
            self.send_json(SERVICE.status())
            return
        if path == "/api/models":
            models_root = Path("/models")
            models = [
                {"name": item.name, "path": str(item)}
                for item in sorted(models_root.iterdir())
                if item.is_dir() and (item / "model.safetensors").is_file()
            ] if models_root.is_dir() else []
            self.send_json({"models": models})
            return
        if path == "/api/system":
            status = SERVICE.status()
            self.send_json(
                METRICS.snapshot(
                    inference_active=status["state"] == "INFERENCING",
                    session_id=status["session_id"],
                )
            )
            return
        if path == "/api/cameras":
            self.send_json(CAMERA_SERVICE.status())
            return
        if path.startswith("/api/camera/stream/"):
            self.stream_camera(path.rsplit("/", 1)[-1])
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path
        try:
            payload = self.read_json_body()
            if path == "/api/load":
                result = SERVICE.load_model(str(payload.get("model", "")))
            elif path == "/api/run":
                result = SERVICE.run_inference(str(payload.get("task", "")), int(payload.get("seed", 0)))
            elif path == "/api/stop":
                result = SERVICE.stop()
            elif path == "/api/reset":
                result = SERVICE.reset()
            elif path.startswith("/api/camera/"):
                _, _, _, camera, action = path.split("/", 4)
                if action == "run":
                    result = CAMERA_SERVICE.start(camera)
                elif action == "stop":
                    result = CAMERA_SERVICE.stop(camera)
                elif action == "restart":
                    result = CAMERA_SERVICE.restart(camera)
                else:
                    raise ValueError(f"Unknown camera action: {action}")
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_json(result, status=HTTPStatus.ACCEPTED)
        except BackendBadRequest as error:
            self.send_json({"ok": False, "error": str(error)}, status=HTTPStatus.BAD_REQUEST)
        except BackendConflict as error:
            self.send_json({"ok": False, "error": str(error)}, status=HTTPStatus.CONFLICT)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            self.send_json({"ok": False, "error": f"Invalid request: {error}"}, status=HTTPStatus.BAD_REQUEST)
        except OSError as error:
            self.send_json({"ok": False, "error": f"Camera process error: {error}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def stream_camera(self, name: str) -> None:
        if name not in CAMERAS:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        sequence = 0
        try:
            while True:
                frame = CAMERA_FRAMES.wait(name, sequence)
                if frame is None:
                    continue
                sequence, jpeg = frame
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                self.wfile.write(jpeg + b"\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass

    def read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > 1_000_000:
            raise BackendBadRequest("Request body is too large")
        if content_length == 0:
            return {}
        payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise BackendBadRequest("JSON body must be an object")
        return payload

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), SmolVLAHandler)
    print(f"SmolVLA UI listening on http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        SERVICE.close()
        CAMERA_SERVICE.close()


if __name__ == "__main__":
    main()
