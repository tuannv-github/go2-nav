#!/usr/bin/env python3
"""
Launch file for IMU timestamp fixer.

Runs imu_timestamp_fixer as a standalone process so it can use
its own DDS/network profile independently from camera/SLAM nodes.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    input_topic_arg = DeclareLaunchArgument(
        'input_topic',
        default_value='/utlidar/imu',
        description='Input IMU topic to read from',
    )
    output_topic_arg = DeclareLaunchArgument(
        'output_topic',
        default_value='/input/imu',
        description='Output IMU topic with refreshed timestamps',
    )
    frame_id_arg = DeclareLaunchArgument(
        'frame_id',
        default_value='utlidar_imu',
        description='Frame id to set on republished IMU message',
    )
    invert_gyro_z_arg = DeclareLaunchArgument(
        'invert_gyro_z',
        default_value='true',
        description='Invert IMU angular_velocity.z sign to match robot yaw convention',
    )
    imu_timestamp_fixer_node = Node(
        package='go2_nav',
        executable='imu_timestamp_fixer_node.py',
        name='imu_timestamp_fixer',
        namespace='input',
        output='screen',
        parameters=[{
            'input_topic': LaunchConfiguration('input_topic'),
            'output_topic': LaunchConfiguration('output_topic'),
            'frame_id': LaunchConfiguration('frame_id'),
            'invert_gyro_z': LaunchConfiguration('invert_gyro_z'),
        }],
    )
    return LaunchDescription([
        input_topic_arg,
        output_topic_arg,
        frame_id_arg,
        invert_gyro_z_arg,
        imu_timestamp_fixer_node,
    ])
