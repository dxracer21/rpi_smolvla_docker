from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import GroupAction, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import SetRemap


def generate_launch_description() -> LaunchDescription:
    package_share = Path(get_package_share_directory("smolvla_camera_bringup"))
    parameter_file = package_share / "config" / "realsense.yaml"

    realsense_share = Path(get_package_share_directory("realsense2_camera"))
    realsense_launch = realsense_share / "launch" / "rs_launch.py"

    realsense_camera = GroupAction(
        actions=[
            SetRemap(
                src="/camera/cam_wrist/color/image_raw",
                dst="/camera/cam_wrist/color/image_rect_raw",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(str(realsense_launch)),
                launch_arguments={"config_file": str(parameter_file)}.items(),
            ),
        ]
    )

    return LaunchDescription([realsense_camera])
