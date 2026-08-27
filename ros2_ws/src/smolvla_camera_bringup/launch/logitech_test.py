from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    package_share = Path(get_package_share_directory("smolvla_camera_bringup"))
    parameter_file = package_share / "config" / "logitech.yaml"

    logitech_camera = Node(
        package="usb_cam",
        executable="usb_cam_node_exe",
        namespace="camera/cam_front/color",
        name="logitech",
        output="screen",
        parameters=[str(parameter_file)],
        remappings=[
            ("image_raw", "image_rect_raw"),
        ],
    )

    return LaunchDescription([logitech_camera])
