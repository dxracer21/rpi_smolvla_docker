#!/usr/bin/env bash

set -Eeuo pipefail

if [[ -f "/opt/ros/${ROS_DISTRO}/setup.bash" ]]; then
    # shellcheck disable=SC1090
    source "/opt/ros/${ROS_DISTRO}/setup.bash"
fi

if [[ -f /workspace/ros2_ws/install/setup.bash ]]; then
    # shellcheck disable=SC1091
    source /workspace/ros2_ws/install/setup.bash
fi

exec "$@"
