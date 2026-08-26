#!/usr/bin/env python3
import json
from importlib.metadata import version

import torch
import torchvision
from lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy


config = SmolVLAConfig()
result = {
    "torch": torch.__version__,
    "torchvision": torchvision.__version__,
    "lerobot": version("lerobot"),
    "transformers": version("transformers"),
    "accelerate": version("accelerate"),
    "cuda_available": torch.cuda.is_available(),
    "policy_class": SmolVLAPolicy.__name__,
    "config_class": type(config).__name__,
}
print(json.dumps(result, indent=2))

if not torch.__version__.endswith("+cpu"):
    raise SystemExit("ERROR: PyTorch was replaced by a non-CPU wheel")
if torch.cuda.is_available():
    raise SystemExit("ERROR: CUDA must be disabled for Raspberry Pi")

print("PASS: LeRobot and SmolVLA imports are ready on ARM64 CPU.")
