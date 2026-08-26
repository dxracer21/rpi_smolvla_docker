# syntax=docker/dockerfile:1
FROM --platform=linux/arm64 ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG PYTHON_VERSION=3.12

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        git \
        libgomp1 \
        python3 \
        python3-pip \
        python3-venv \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv "$VIRTUAL_ENV"

COPY requirements-torch.txt /tmp/requirements-torch.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement /tmp/requirements-torch.txt \
    && rm /tmp/requirements-torch.txt

COPY requirements-lerobot.txt /tmp/requirements-lerobot.txt
RUN python -m pip install --requirement /tmp/requirements-lerobot.txt \
    && rm /tmp/requirements-lerobot.txt \
    && python -m pip check

WORKDIR /workspace

COPY scripts/verify_platform.py /usr/local/bin/verify_platform.py
COPY scripts/verify_runtime.py /usr/local/bin/verify_runtime.py
COPY scripts/verify_lerobot.py /usr/local/bin/verify_lerobot.py

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "/usr/local/bin/verify_lerobot.py"]
