#!/usr/bin/env python3
"""
Launch file for Intel RealSense camera.

This launch file starts the RealSense camera driver node.
Supports D400 series cameras (D435, D435i, D455, etc.)

Example:
    ros2 launch go2_nav realsense.launch.py
    ros2 launch go2_nav realsense.launch.py camera_name:=camera serial_no:=123456789012
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch_ros.actions import SetParameter, PushRosNamespace
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, GroupAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    # Launch arguments
    declare_camera_name = DeclareLaunchArgument(
        'camera_name',
        default_value='camera',
        description='Name of the camera (used as namespace)'
    )
    
    declare_serial_no = DeclareLaunchArgument(
        'serial_no',
        default_value='',
        description='Serial number of the camera to use (empty = use first available)'
    )
    
    declare_enable_depth = DeclareLaunchArgument(
        'enable_depth',
        default_value='true',
        description='Enable depth stream'
    )
    
    declare_enable_color = DeclareLaunchArgument(
        'enable_color',
        default_value='true',
        description='Enable color stream'
    )
    
    declare_enable_gyro = DeclareLaunchArgument(
        'enable_gyro',
        default_value='false',
        description='Enable gyroscope (for D435i, D455i, etc.)'
    )
    
    declare_enable_accel = DeclareLaunchArgument(
        'enable_accel',
        default_value='false',
        description='Enable accelerometer (for D435i, D455i, etc.)'
    )
    
    declare_align_depth = DeclareLaunchArgument(
        'align_depth',
        default_value='true',
        description='Align depth to color frame'
    )
    
    declare_enable_sync = DeclareLaunchArgument(
        'enable_sync',
        default_value='true',
        description='Enable synchronized frames'
    )
    
    declare_pointcloud = DeclareLaunchArgument(
        'pointcloud',
        default_value='false',
        description='Enable pointcloud generation'
    )

    # Get launch arguments
    camera_name = LaunchConfiguration('camera_name')
    serial_no = LaunchConfiguration('serial_no')
    enable_depth = LaunchConfiguration('enable_depth')
    enable_color = LaunchConfiguration('enable_color')
    enable_gyro = LaunchConfiguration('enable_gyro')
    enable_accel = LaunchConfiguration('enable_accel')
    align_depth = LaunchConfiguration('align_depth')
    enable_sync = LaunchConfiguration('enable_sync')
    pointcloud = LaunchConfiguration('pointcloud')

    # Launch arguments dictionary
    launch_args = {
        'camera_name': camera_name,
        'enable_depth': enable_depth,
        'enable_color': enable_color,
        'enable_gyro': enable_gyro,
        'enable_accel': enable_accel,
        'align_depth.enable': align_depth,
        'enable_sync': enable_sync,
        'pointcloud.enable': pointcloud,
        'serial_no': serial_no,
    }

    return LaunchDescription([
        # Launch arguments
        declare_camera_name,
        declare_serial_no,
        declare_enable_depth,
        declare_enable_color,
        declare_enable_gyro,
        declare_enable_accel,
        declare_align_depth,
        declare_enable_sync,
        declare_pointcloud,
        
        # Enable IR emitter for better depth quality
        SetParameter(name='depth_module.emitter_enabled', value=1),
        
        # Launch RealSense camera driver under /input/camera namespace
        GroupAction([
            PushRosNamespace('input'),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource([
                    os.path.join(
                        get_package_share_directory('realsense2_camera'),
                        'launch',
                        'rs_launch.py'
                    )
                ]),
                launch_arguments=launch_args.items(),
            ),
        ]),
    ])
