#!/usr/bin/env python3
"""
Launch file for Slamtec RPLidar A3 using ``rplidar_ros`` (``rplidar_node``).

The A3 uses **256000** baud on the serial channel. Default ``serial_port`` is
``/dev/rplidar`` (symlink from ``udev/rplidar.rules`` via
``scripts/install_rplidar_udev.sh``). Override with e.g. ``serial_port:=/dev/ttyUSB0``
if you do not use that rule.

If the node prints ``*** buffer overflow detected ***`` and exits (-6), the UART
data is often invalid: wrong baud for the actual lidar model (A1/A2 use 115200),
another process still using the serial port, flaky USB cable, or missing dialout
permissions. Try ``angle_compensate:=false``, confirm the model label on the
sensor, or match the vendor launch:

    ros2 launch rplidar_ros rplidar_a3_launch.py

Example:

    ros2 launch go2_nav rplidar_a3.launch.py

    ros2 launch go2_nav rplidar_a3.launch.py serial_port:=/dev/ttyUSB0

Install dependency (Ubuntu / ROS 2 Humble): ``sudo apt install ros-humble-rplidar-ros``

Serial permissions / stable ``/dev/rplidar`` symlink: ``bash scripts/install_rplidar_udev.sh`` from the repo root (copies ``udev/rplidar.rules`` to ``/etc/udev/rules.d/``).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'channel_type',
            default_value='serial',
            description='Channel type (serial for USB UART).',
        ),
        DeclareLaunchArgument(
            'serial_port',
            default_value='/dev/rplidar',
            description=(
                'Serial device path. Default /dev/rplidar if udev rules installed; '
                'else use /dev/ttyUSB0 or /dev/ttyACM0.'
            ),
        ),
        DeclareLaunchArgument(
            'serial_baudrate',
            default_value='256000',
            description='UART baud rate (RPLidar A3 uses 256000).',
        ),
        DeclareLaunchArgument(
            'frame_id',
            default_value='laser',
            description='TF frame_id written to LaserScan messages.',
        ),
        DeclareLaunchArgument(
            'inverted',
            default_value='false',
            description='Whether to invert scan data.',
        ),
        DeclareLaunchArgument(
            'angle_compensate',
            default_value='true',
            description='Enable angle compensation in the driver.',
        ),
        DeclareLaunchArgument(
            'scan_mode',
            default_value='',
            description=(
                'Named A3 express mode (e.g. Sensitivity). Empty = SDK default '
                'typical scan (often most stable).'
            ),
        ),
        Node(
            package='rplidar_ros',
            executable='rplidar_node',
            name='rplidar_node',
            output='screen',
            parameters=[{
                'channel_type': LaunchConfiguration('channel_type'),
                'serial_port': LaunchConfiguration('serial_port'),
                'serial_baudrate': ParameterValue(
                    LaunchConfiguration('serial_baudrate'), value_type=int),
                'frame_id': LaunchConfiguration('frame_id'),
                'inverted': ParameterValue(
                    LaunchConfiguration('inverted'), value_type=bool),
                'angle_compensate': ParameterValue(
                    LaunchConfiguration('angle_compensate'), value_type=bool),
                'scan_mode': LaunchConfiguration('scan_mode'),
            }],
        ),
    ])
