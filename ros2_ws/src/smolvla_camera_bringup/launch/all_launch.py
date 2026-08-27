from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description() -> LaunchDescription:
    package_share = Path(get_package_share_directory("smolvla_camera_bringup"))
    launch_directory = package_share / "launch"

    logitech_camera = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(launch_directory / "logitech_test.py"))
    )
    realsense_camera = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(launch_directory / "realsence_test.py"))
    )

    return LaunchDescription([logitech_camera, realsense_camera])
