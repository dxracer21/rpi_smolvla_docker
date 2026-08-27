"""Thread-safe, dry-run-only SmolVLA inference lifecycle service."""

from __future__ import annotations

import json
import os
import resource
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from backend.zenoh_status import ZenohStatusPublisher


os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


class BackendError(Exception):
    """Base error exposed through the local API."""


class BackendConflict(BackendError):
    """The requested transition is not valid in the current state."""


class BackendBadRequest(BackendError):
    """The request contains invalid user input."""


class InferenceService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="smolvla-worker")
        self._generation = 0
        self._active_worker = False
        self._state = "UNLOADED"
        self._model_path: str | None = None
        self._task: str | None = None
        self._session_id: int | None = None
        self._result: dict[str, Any] | None = None
        self._error: str | None = None
        self._load_seconds: float | None = None
        self._policy: Any = None
        self._config: Any = None
        self._preprocessor: Any = None
        self._postprocessor: Any = None
        self._zenoh = ZenohStatusPublisher(
            endpoint=os.getenv("ZENOH_ENDPOINT", ""),
            key_prefix=os.getenv("ZENOH_KEY_PREFIX", "smolvla"),
        )
        self._publish_status()

    def close(self) -> None:
        self.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._zenoh.close()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked(include_zenoh=True)

    def load_model(self, model_path: str) -> dict[str, Any]:
        path = self._validate_model_path(model_path)
        with self._lock:
            if self._active_worker:
                raise BackendConflict(f"Cannot load a model while state is {self._state}")
            if self._policy is not None and self._model_path == str(path):
                self._state = "IDLE"
                self._error = None
                snapshot = self._snapshot_locked()
            else:
                self._generation += 1
                generation = self._generation
                self._active_worker = True
                self._state = "LOADING"
                self._model_path = str(path)
                self._task = None
                self._session_id = None
                self._result = None
                self._error = None
                self._load_seconds = None
                snapshot = self._snapshot_locked()
                self._executor.submit(self._load_worker, generation, path)
        self._zenoh.publish(snapshot)
        return snapshot

    def run_inference(self, task: str, seed: int = 0) -> dict[str, Any]:
        task = task.strip()
        if not task:
            raise BackendBadRequest("Task instruction must not be empty")
        if len(task) > 500:
            raise BackendBadRequest("Task instruction is too long")
        with self._lock:
            if self._policy is None:
                raise BackendConflict("Load the model before running inference")
            if self._active_worker:
                raise BackendConflict(f"Cannot start inference while state is {self._state}")
            self._generation += 1
            generation = self._generation
            self._session_id = (self._session_id or 0) + 1
            session_id = self._session_id
            self._active_worker = True
            self._state = "INFERENCING"
            self._task = task
            self._result = None
            self._error = None
            snapshot = self._snapshot_locked()
            self._executor.submit(self._inference_worker, generation, session_id, task, seed)
        self._zenoh.publish(snapshot)
        return snapshot

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._generation += 1
            self._result = None
            self._error = None
            if self._active_worker:
                self._state = "STOPPING"
            else:
                self._state = "STOPPED" if self._policy is not None else "UNLOADED"
            snapshot = self._snapshot_locked()
        self._zenoh.publish(snapshot)
        return snapshot

    def reset(self) -> dict[str, Any]:
        with self._lock:
            self._generation += 1
            self._task = None
            self._result = None
            self._error = None
            if self._active_worker:
                self._state = "RESETTING"
            elif self._policy is not None:
                self._policy.reset()
                self._state = "IDLE"
            else:
                self._state = "UNLOADED"
            snapshot = self._snapshot_locked()
        self._zenoh.publish(snapshot)
        return snapshot

    def _load_worker(self, generation: int, model_path: Path) -> None:
        started = time.perf_counter()
        try:
            import torch
            from lerobot.policies.factory import make_pre_post_processors
            from lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig
            from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

            torch.set_grad_enabled(False)
            config = SmolVLAConfig.from_pretrained(
                model_path,
                local_files_only=True,
                device="cpu",
                use_amp=False,
                compile_model=False,
            )
            policy = SmolVLAPolicy.from_pretrained(
                model_path,
                config=config,
                local_files_only=True,
                strict=True,
            )
            policy.eval()
            preprocessor, postprocessor = make_pre_post_processors(
                config,
                pretrained_path=str(model_path),
                preprocessor_overrides={
                    "tokenizer_processor": {"tokenizer_name": str(model_path / "tokenizer")},
                    "device_processor": {"device": "cpu"},
                },
                postprocessor_overrides={"device_processor": {"device": "cpu"}},
            )
            load_seconds = time.perf_counter() - started
            with self._lock:
                self._active_worker = False
                if generation != self._generation:
                    self._finish_cancelled_locked()
                else:
                    self._policy = policy
                    self._config = config
                    self._preprocessor = preprocessor
                    self._postprocessor = postprocessor
                    self._load_seconds = load_seconds
                    self._state = "IDLE"
                    self._error = None
                snapshot = self._snapshot_locked()
        except Exception as error:
            with self._lock:
                self._active_worker = False
                if generation == self._generation:
                    self._state = "ERROR"
                    self._error = f"{type(error).__name__}: {error}"
                else:
                    self._finish_cancelled_locked()
                snapshot = self._snapshot_locked()
        self._zenoh.publish(snapshot)

    def _inference_worker(self, generation: int, session_id: int, task: str, seed: int) -> None:
        try:
            import torch
            from scripts.run_inference import make_dummy_observation

            torch.manual_seed(seed)
            self._policy.reset()
            observation = make_dummy_observation(self._config, task, seed)
            batch = self._preprocessor(observation)
            started = time.perf_counter()
            with torch.inference_mode():
                action = self._policy.select_action(batch)
                action = self._postprocessor(action)
            inference_seconds = time.perf_counter() - started
            action_cpu = action.detach().cpu()
            finite = bool(torch.isfinite(action_cpu).all().item())
            if not finite:
                raise RuntimeError("Inference returned NaN or infinity")
            result = {
                "session_id": session_id,
                "seconds": round(inference_seconds, 6),
                "action_shape": list(action_cpu.shape),
                "action": action_cpu.tolist(),
                "finite": finite,
                "peak_rss_gib": round(self._peak_rss_gib(), 3),
            }
            with self._lock:
                self._active_worker = False
                self._policy.reset()
                if generation != self._generation:
                    self._finish_cancelled_locked()
                    snapshot = self._snapshot_locked()
                else:
                    self._result = result
                    self._state = "RESULT_READY"
                    self._error = None
                    snapshot = self._snapshot_locked()
                    self._save_result(snapshot)
        except Exception as error:
            with self._lock:
                self._active_worker = False
                if self._policy is not None:
                    self._policy.reset()
                if generation == self._generation:
                    self._state = "ERROR"
                    self._error = f"{type(error).__name__}: {error}"
                else:
                    self._finish_cancelled_locked()
                snapshot = self._snapshot_locked()
        self._zenoh.publish(snapshot)

    def _finish_cancelled_locked(self) -> None:
        if self._policy is not None:
            self._policy.reset()
        self._result = None
        self._error = None
        if self._state == "RESETTING":
            self._task = None
            self._state = "IDLE" if self._policy is not None else "UNLOADED"
        elif self._state == "STOPPING":
            self._state = "STOPPED" if self._policy is not None else "UNLOADED"

    def _snapshot_locked(self, include_zenoh: bool = False) -> dict[str, Any]:
        snapshot = {
            "ok": self._state != "ERROR",
            "service": "smolvla-inference",
            "state": self._state,
            "mode": "DRY_RUN",
            "robot": "DISCONNECTED",
            "robot_output_enabled": False,
            "model": self._model_path,
            "task": self._task,
            "session_id": self._session_id,
            "load_seconds": self._load_seconds,
            "result": self._result,
            "error": self._error,
            "active_worker": self._active_worker,
        }
        if include_zenoh:
            snapshot["zenoh"] = self._zenoh.snapshot()
        return snapshot

    def _publish_status(self) -> None:
        with self._lock:
            snapshot = self._snapshot_locked()
        self._zenoh.publish(snapshot)

    @staticmethod
    def _validate_model_path(model_path: str) -> Path:
        path = Path(model_path).expanduser().resolve()
        models_root = Path("/models").resolve()
        if path != models_root and models_root not in path.parents:
            raise BackendBadRequest("Model path must be inside /models")
        required = (
            "config.json",
            "model.safetensors",
            "policy_preprocessor.json",
            "policy_postprocessor.json",
            "tokenizer",
        )
        missing = [name for name in required if not (path / name).exists()]
        if missing:
            raise BackendBadRequest(f"Model is incomplete; missing: {', '.join(missing)}")
        return path

    @staticmethod
    def _peak_rss_gib() -> float:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2)

    @staticmethod
    def _save_result(snapshot: dict[str, Any]) -> None:
        results_dir = Path("/workspace/results")
        results_dir.mkdir(parents=True, exist_ok=True)
        destination = results_dir / f"ui_session_{snapshot['session_id']}.json"
        destination.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
