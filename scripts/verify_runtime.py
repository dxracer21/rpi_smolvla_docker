#!/usr/bin/env python3
import json
import platform
import time

import torch
import torchvision


torch.manual_seed(0)
torch.set_num_threads(4)

x = torch.randn(1, 3, 224, 224)
conv = torch.nn.Conv2d(3, 32, kernel_size=3, padding=1).eval()

with torch.inference_mode():
    conv(x)
    started = time.perf_counter()
    for _ in range(20):
        output = conv(x)
    elapsed = time.perf_counter() - started

result = {
    "machine": platform.machine(),
    "torch": torch.__version__,
    "torchvision": torchvision.__version__,
    "cuda_available": torch.cuda.is_available(),
    "torch_threads": torch.get_num_threads(),
    "output_shape": list(output.shape),
    "conv_average_ms": round(elapsed / 20 * 1000, 3),
    "finite_output": bool(torch.isfinite(output).all()),
}
print(json.dumps(result, indent=2))

if platform.machine() not in {"aarch64", "arm64"}:
    raise SystemExit("ERROR: container is not ARM64")
if torch.cuda.is_available():
    raise SystemExit("ERROR: CUDA must be disabled for the Raspberry Pi CPU image")
if not result["finite_output"]:
    raise SystemExit("ERROR: tensor output contains NaN or Inf")

print("PASS: ARM64 CPU PyTorch and torchvision runtime are ready.")
