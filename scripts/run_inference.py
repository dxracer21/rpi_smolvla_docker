#!/usr/bin/env python3
"""Run a local SmolVLA checkpoint on CPU with generated test observations."""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any

# Prevent Transformers/Hugging Face libraries from making network requests.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import torch
from lerobot.policies.factory import make_pre_post_processors
from lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy


DEFAULT_TASK = "Pick up the object"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load a local SmolVLA checkpoint and run CPU dummy inference."
    )
    parser.add_argument(
        "--model",
        required=True,
        type=Path,
        help="Checkpoint's pretrained_model directory (for example /models/task_20_quant_285000)",
    )
    parser.add_argument("--task", default=DEFAULT_TASK, help="Natural-language task instruction")
    parser.add_argument("--runs", type=int, default=1, help="Number of full model inferences (default: 1)")
    parser.add_argument("--seed", type=int, default=0, help="Random seed used for dummy images")
    parser.add_argument(
        "--dtype",
        choices=("checkpoint", "float32"),
        default="checkpoint",
        help="Use checkpoint dtypes or cast all floating-point model parameters to FP32",
    )
    parser.add_argument("--output-json", type=Path, help="Optional path for a JSON result file")
    return parser.parse_args()


def validate_model_dir(model_dir: Path) -> Path:
    model_dir = model_dir.expanduser().resolve()
    required = (
        "config.json",
        "model.safetensors",
        "policy_preprocessor.json",
        "policy_postprocessor.json",
        "tokenizer",
    )
    missing = [name for name in required if not (model_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Invalid model directory: {model_dir}\nMissing: {', '.join(missing)}"
        )
    return model_dir


def make_dummy_observation(config: SmolVLAConfig, task: str, seed: int) -> dict[str, Any]:
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed)
    observation: dict[str, Any] = {"task": task}

    for name, feature in config.input_features.items():
        shape = tuple(feature.shape)
        feature_type = str(feature.type).upper()
        if "VISUAL" in feature_type:
            observation[name] = torch.rand(shape, generator=generator, dtype=torch.float32)
        else:
            observation[name] = torch.zeros(shape, dtype=torch.float32)

    return observation


def peak_rss_gib() -> float:
    # Linux reports ru_maxrss in KiB. This script runs inside the Linux container.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2)


def main() -> int:
    args = parse_args()
    if args.runs < 1:
        raise ValueError("--runs must be at least 1")

    torch.manual_seed(args.seed)
    torch.set_grad_enabled(False)
    model_dir = validate_model_dir(args.model)

    print(f"[INFO] model: {model_dir}", flush=True)
    print(f"[INFO] task: {args.task!r}", flush=True)
    print(f"[INFO] torch: {torch.__version__}, device: cpu", flush=True)

    load_started = time.perf_counter()
    config = SmolVLAConfig.from_pretrained(
        model_dir,
        local_files_only=True,
        device="cpu",
        use_amp=False,
        compile_model=False,
    )

    policy = SmolVLAPolicy.from_pretrained(
        model_dir,
        config=config,
        local_files_only=True,
        strict=True,
    )
    if args.dtype == "float32":
        policy = policy.to(dtype=torch.float32)
    policy.eval()

    preprocessor, postprocessor = make_pre_post_processors(
        config,
        pretrained_path=str(model_dir),
        preprocessor_overrides={
            "tokenizer_processor": {"tokenizer_name": str(model_dir / "tokenizer")},
            "device_processor": {"device": "cpu"},
        },
        postprocessor_overrides={"device_processor": {"device": "cpu"}},
    )
    load_seconds = time.perf_counter() - load_started
    print(f"[INFO] model loaded in {load_seconds:.3f}s", flush=True)
    print(f"[INFO] inference dtype mode: {args.dtype}", flush=True)

    run_results = []
    for run_number in range(1, args.runs + 1):
        observation = make_dummy_observation(config, args.task, args.seed)
        batch = preprocessor(observation)
        torch.manual_seed(args.seed)
        policy.reset()  # Force a new action chunk instead of consuming the previous queue.

        started = time.perf_counter()
        with torch.inference_mode():
            action = policy.select_action(batch)
            action = postprocessor(action)
        inference_seconds = time.perf_counter() - started

        action_cpu = action.detach().cpu()
        finite = bool(torch.isfinite(action_cpu).all().item())
        result = {
            "run": run_number,
            "seconds": round(inference_seconds, 6),
            "action_shape": list(action_cpu.shape),
            "action": action_cpu.tolist(),
            "finite": finite,
        }
        run_results.append(result)
        print(
            f"[RESULT] run={run_number} time={inference_seconds:.3f}s "
            f"shape={tuple(action_cpu.shape)} finite={finite}",
            flush=True,
        )
        print(f"[RESULT] action={action_cpu}", flush=True)
        if not finite:
            raise RuntimeError("Inference returned NaN or infinity")

    report = {
        "model": str(model_dir),
        "task": args.task,
        "seed": args.seed,
        "dtype": args.dtype,
        "load_seconds": round(load_seconds, 6),
        "peak_rss_gib": round(peak_rss_gib(), 3),
        "runs": run_results,
    }
    print(f"[INFO] peak RSS: {report['peak_rss_gib']:.3f} GiB", flush=True)

    if args.output_json:
        output_path = args.output_json.expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"[INFO] report saved: {output_path}", flush=True)

    print("PASS: SmolVLA CPU inference completed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
