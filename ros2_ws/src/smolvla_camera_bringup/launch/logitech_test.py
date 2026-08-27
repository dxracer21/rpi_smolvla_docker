from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    package_share = Path(get_package_share_directory("smolvla_camera_bringup"))
    parameter_file = package_share / "config" / "logitech.yaml"
    with parameter_file.open(encoding="utf-8") as stream:
        parameters = yaml.safe_load(stream)["/**"]["ros__parameters"]

    configured_device = Path(parameters["video_device"])
    if not configured_device.exists():
        raise RuntimeError(f"Logitech camera device not found: {configured_device}")
    resolved_device = str(configured_device.resolve())

    logitech_camera = Node(
        package="usb_cam",
        executable="usb_cam_node_exe",
        namespace="camera/cam_front/color",
        name="logitech",
        output="screen",
        parameters=[str(parameter_file), {"video_device": resolved_device}],
        remappings=[
            ("image_raw", "image_rect_raw"),
            ("image_raw/compressed", "image_rect_raw/compressed"),
            ("image_raw/compressedDepth", "image_rect_raw/compressedDepth"),
            ("image_raw/theora", "image_rect_raw/theora"),
            ("image_raw/zstd", "image_rect_raw/zstd"),
        ],
    )

    return LaunchDescription([logitech_camera])
