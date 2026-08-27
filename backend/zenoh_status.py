"""Optional, non-blocking Zenoh status publisher."""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any


class ZenohStatusPublisher:
    def __init__(self, endpoint: str, key_prefix: str = "smolvla") -> None:
        self.endpoint = endpoint.strip()
        self.key_prefix = key_prefix.strip("/") or "smolvla"
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._connected = False
        self._router_ids: list[str] = []
        self._last_error: str | None = None
        self._last_publish_at: float | None = None
        self._thread: threading.Thread | None = None

        if self.endpoint:
            self._thread = threading.Thread(target=self._run, name="zenoh-status", daemon=True)
            self._thread.start()

    def publish(self, payload: dict[str, Any]) -> None:
        if not self.endpoint:
            return
        message = dict(payload)
        while True:
            try:
                self._queue.put_nowait(message)
                return
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    return

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": bool(self.endpoint),
                "connected": self._connected,
                "endpoint": self.endpoint or None,
                "router_ids": list(self._router_ids),
                "last_error": self._last_error,
                "last_publish_at": self._last_publish_at,
            }

    def close(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _set_connection(
        self,
        connected: bool,
        *,
        router_ids: list[str] | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            self._connected = connected
            self._router_ids = router_ids or []
            self._last_error = error

    def _run(self) -> None:
        try:
            import zenoh
        except ImportError as error:
            self._set_connection(False, error=f"eclipse-zenoh is not installed: {error}")
            return

        while not self._stop_event.is_set():
            session = None
            try:
                config = zenoh.Config.from_json5(
                    json.dumps(
                        {
                            "mode": "client",
                            "connect": {
                                "endpoints": [self.endpoint],
                                "timeout_ms": 3000,
                            },
                        }
                    )
                )
                session = zenoh.open(config)
                router_ids = [str(router_id) for router_id in session.info.routers_zid()]
                self._set_connection(True, router_ids=router_ids)

                while not self._stop_event.is_set():
                    try:
                        payload = self._queue.get(timeout=1)
                    except queue.Empty:
                        continue
                    self._put_status(session, payload)
            except Exception as error:
                self._set_connection(False, error=str(error))
                self._stop_event.wait(3)
            finally:
                if session is not None:
                    try:
                        session.close()
                    except Exception:
                        pass

    def _put_status(self, session: Any, payload: dict[str, Any]) -> None:
        session.put(
            f"{self.key_prefix}/status",
            json.dumps(payload, separators=(",", ":")),
            encoding="application/json",
        )
        session_payload = {
            key: payload.get(key)
            for key in ("state", "session_id", "task", "model", "mode")
        }
        session.put(
            f"{self.key_prefix}/session",
            json.dumps(session_payload, separators=(",", ":")),
            encoding="application/json",
        )
        if payload.get("state") == "RESULT_READY" and payload.get("result"):
            session.put(
                f"{self.key_prefix}/result",
                json.dumps(payload["result"], separators=(",", ":")),
                encoding="application/json",
            )
        with self._lock:
            self._last_publish_at = time.time()
            self._last_error = None
