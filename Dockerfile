# syntax=docker/dockerfile:1
FROM --platform=linux/arm64 ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG PYTHON_VERSION=3.12
ARG ROS_DISTRO=jazzy

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    ROS_DISTRO=${ROS_DISTRO} \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        git \
        gnupg \
        libgomp1 \
        python3 \
        python3-pip \
        python3-venv \
        software-properties-common \
        tini \
        usbutils \
        v4l-utils \
    && add-apt-repository universe \
    && ROS_APT_SOURCE_VERSION="$(curl -fsSL https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
        | grep -F 'tag_name' | awk -F'"' '{print $4}')" \
    && curl -fsSL -o /tmp/ros2-apt-source.deb \
        "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.noble_all.deb" \
    && dpkg -i /tmp/ros2-apt-source.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-colcon-common-extensions \
        ros-${ROS_DISTRO}-compressed-image-transport \
        ros-${ROS_DISTRO}-image-transport \
        ros-${ROS_DISTRO}-realsense2-camera \
        ros-${ROS_DISTRO}-rmw-zenoh-cpp \
        ros-${ROS_DISTRO}-ros-base \
        ros-${ROS_DISTRO}-usb-cam \
    && rm -f /tmp/ros2-apt-source.deb \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv --system-site-packages "$VIRTUAL_ENV"

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
COPY scripts/ros_entrypoint.sh /usr/local/bin/ros_entrypoint.sh
RUN chmod +x /usr/local/bin/ros_entrypoint.sh

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/ros_entrypoint.sh"]
CMD ["python", "/usr/local/bin/verify_lerobot.py"]
