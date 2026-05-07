#!/usr/bin/env python3
"""
Livox MID-360 (``livox_ros_driver2``) for go2_nav.

Network JSON lives under this package: ``share/go2_nav/config/MID360_config.json``.
Edit host / lidar IPs there to match your robot and sensor.

Publishes static TF ``tf_parent`` → ``frame_id`` (default ``base_link`` → ``livox_frame``)
using ``livox_x``/``livox_y``/``livox_z`` (m) and ``livox_roll``/``livox_pitch``/``livox_yaw`` (deg).
Defaults match the stock ``realsense.launch.py`` mount (0, 0, 0.5 m, 0°) if you had aligned LiDAR with the camera; override for the real Livox pose.

Example::

    ros2 launch go2_nav livox_mid360.launch.py

    ros2 launch go2_nav livox_mid360.launch.py rviz:=true

Requires ``livox_ros_driver2`` built/installed and Livox SDK on the system.

"""

import math
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
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
        description='frame_id for published clouds / child frame for Livox static TF.',
    )
    user_config_path = DeclareLaunchArgument(
        'user_config_path',
        default_value=default_config,
        description='Path to MID360 JSON (host_net_info + lidar_configs).',
    )
    rviz = DeclareLaunchArgument(
        'rviz',
        default_value='false',
        description='If true, start rviz2 with Livox point-cloud layout.',
    )
    rviz_config = DeclareLaunchArgument(
        'rviz_config',
        default_value=default_rviz_cfg,
        description='RViz display config (default: go2_nav/rviz/livox_mid360.rviz).',
    )

    tf_parent = DeclareLaunchArgument(
        'tf_parent',
        default_value='base_link',
        description='Parent frame for Livox static TF.',
    )
    livox_x = DeclareLaunchArgument(
        'livox_x',
        default_value='-0.2',
        description='Translation X from tf_parent to Livox frame (m, forward).',
    )
    livox_y = DeclareLaunchArgument(
        'livox_y',
        default_value='0.0',
        description='Translation Y from tf_parent (m, left).',
    )
    livox_z = DeclareLaunchArgument(
        'livox_z',
        default_value='0.35',
        description='Translation Z from tf_parent (m, up). Default matches stock realsense camera height.',
    )
    livox_roll = DeclareLaunchArgument(
        'livox_roll',
        default_value='0.0',
        description='Static TF roll from tf_parent to Livox (deg, ZYX order).',
    )
    livox_pitch = DeclareLaunchArgument(
        'livox_pitch',
        default_value='15.0',
        description='Static TF pitch (deg).',
    )
    livox_yaw = DeclareLaunchArgument(
        'livox_yaw',
        default_value='0.0',
        description='Static TF yaw (deg).',
    )

    return LaunchDescription([
        xfer_format,
        multi_topic,
        publish_freq,
        frame_id,
        user_config_path,
        rviz,
        rviz_config,
        tf_parent,
        livox_x,
        livox_y,
        livox_z,
        livox_roll,
        livox_pitch,
        livox_yaw,
        OpaqueFunction(function=launch_setup),
    ])


def launch_setup(context, *args, **kwargs):
    """Euler (deg, ZYX) -> quaternion for Livox static TF."""
    tx = LaunchConfiguration('livox_x').perform(context)
    ty = LaunchConfiguration('livox_y').perform(context)
    tz = LaunchConfiguration('livox_z').perform(context)
    rpy_roll = LaunchConfiguration('livox_roll').perform(context)
    rpy_pitch = LaunchConfiguration('livox_pitch').perform(context)
    rpy_yaw = LaunchConfiguration('livox_yaw').perform(context)

    try:
        roll = float(rpy_roll) * math.pi / 180.0
        pitch = float(rpy_pitch) * math.pi / 180.0
        yaw = float(rpy_yaw) * math.pi / 180.0
        cy = math.cos(yaw * 0.5)
        sy = math.sin(yaw * 0.5)
        cp = math.cos(pitch * 0.5)
        sp = math.sin(pitch * 0.5)
        cr = math.cos(roll * 0.5)
        sr = math.sin(roll * 0.5)
        qw = cr * cp * cy + sr * sp * sy
        qx = sr * cp * cy - cr * sp * sy
        qy = cr * sp * cy + sr * cp * sy
        qz = cr * cp * sy - sr * sp * cy
    except (ValueError, TypeError):
        qx, qy, qz, qw = 0.0, 0.0, 0.0, 1.0

    parent = LaunchConfiguration('tf_parent').perform(context)
    child = LaunchConfiguration('frame_id').perform(context)

    tf_livox = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_link_to_livox_frame',
        arguments=[
            tx, ty, tz,
            str(qx), str(qy), str(qz), str(qw),
            parent, child,
        ],
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

    return [tf_livox, livox_driver, livox_rviz]
