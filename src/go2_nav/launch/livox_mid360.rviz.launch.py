#!/usr/bin/env python3
"""
Livox MID-360 (``livox_ros_driver2``) for go2_nav.

Network JSON lives under this package: ``share/go2_nav/config/MID360_config.json``.
Edit host / lidar IPs there to match your robot and sensor.

Example::

    ros2 launch go2_nav livox_mid360.launch.py

    ros2 launch go2_nav livox_mid360.launch.py rviz:=true

Requires ``livox_ros_driver2`` built/installed and Livox SDK on the system.

"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    go2_nav_share = get_package_share_directory('go2_nav')

    default_config = os.path.join(go2_nav_share, 'config', 'MID360_config.json')
    default_rviz_cfg = os.path.join(go2_nav_share, 'rviz', 'livox_mid360.rviz')

    xfer_format = DeclareLaunchArgument(
        'xfer_format',
        default_value='0',
        description='0=PointCloud2 (PointXYZRTL), 1=Livox custom pointcloud.',
    )
    multi_topic = DeclareLaunchArgument(
        'multi_topic',
        default_value='0',
        description='0=single topic for all units, 1=one topic per LiDAR.',
    )
    publish_freq = DeclareLaunchArgument(
        'publish_freq',
        default_value='10.0',
        description='Point cloud publish rate (Hz).',
    )
    frame_id = DeclareLaunchArgument(
        'frame_id',
        default_value='livox_frame',
        description='frame_id for published clouds.',
    )
    user_config_path = DeclareLaunchArgument(
        'user_config_path',
        default_value=default_config,
        description='Path to MID360 JSON (host_net_info + lidar_configs).',
    )
    rviz = DeclareLaunchArgument(
        'rviz',
        default_value='true',
        description='If true, start rviz2 with Livox point-cloud layout.',
    )
    rviz_config = DeclareLaunchArgument(
        'rviz_config',
        default_value=default_rviz_cfg,
        description='RViz display config (default: go2_nav/rviz/livox_mid360.rviz).',
    )

    livox_driver = Node(
        package='livox_ros_driver2',
        executable='livox_ros_driver2_node',
        name='livox_lidar_publisher',
        output='screen',
        parameters=[{
            'xfer_format': LaunchConfiguration('xfer_format'),
            'multi_topic': LaunchConfiguration('multi_topic'),
            'data_src': 0,
            'publish_freq': LaunchConfiguration('publish_freq'),
            'output_data_type': 0,
            'frame_id': LaunchConfiguration('frame_id'),
            'lvx_file_path': '/home/livox/livox_test.lvx',
            'user_config_path': LaunchConfiguration('user_config_path'),
            'cmdline_input_bd_code': 'livox0000000001',
        }],
    )

    livox_rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='livox_rviz2',
        output='screen',
        arguments=['--display-config', LaunchConfiguration('rviz_config')],
        condition=IfCondition(LaunchConfiguration('rviz')),
    )

    return LaunchDescription([
        xfer_format,
        multi_topic,
        publish_freq,
        frame_id,
        user_config_path,
        rviz,
        rviz_config,
        livox_driver,
        livox_rviz,
    ])
