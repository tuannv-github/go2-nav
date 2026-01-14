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
from launch_ros.actions import SetParameter, PushRosNamespace, Node
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, GroupAction, OpaqueFunction
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
    
    # Camera transform parameters (adjust based on your camera mounting)
    declare_camera_x = DeclareLaunchArgument(
        'camera_x',
        default_value='0.0',
        description='X offset of camera from base_link (meters, forward)'
    )
    declare_camera_y = DeclareLaunchArgument(
        'camera_y',
        default_value='0.0',
        description='Y offset of camera from base_link (meters, left)'
    )
    declare_camera_z = DeclareLaunchArgument(
        'camera_z',
        default_value='0.25',
        description='Z offset of camera from base_link (meters, up)'
    )
    declare_camera_roll = DeclareLaunchArgument(
        'camera_roll',
        default_value='0.0',
        description='Roll angle of camera in degrees'
    )
    declare_camera_pitch = DeclareLaunchArgument(
        'camera_pitch',
        default_value='-20.0',
        description='Pitch angle of camera in degrees'
    )
    declare_camera_yaw = DeclareLaunchArgument(
        'camera_yaw',
        default_value='0.0',
        description='Yaw angle of camera in degrees'
    )

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
        declare_camera_x,
        declare_camera_y,
        declare_camera_z,
        declare_camera_roll,
        declare_camera_pitch,
        declare_camera_yaw,
        
        OpaqueFunction(function=launch_setup)
    ])

def launch_setup(context, *args, **kwargs):
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
    
    # Get camera transform parameters
    camera_x = LaunchConfiguration('camera_x').perform(context)
    camera_y = LaunchConfiguration('camera_y').perform(context)
    camera_z = LaunchConfiguration('camera_z').perform(context)
    camera_roll = LaunchConfiguration('camera_roll').perform(context)
    camera_pitch = LaunchConfiguration('camera_pitch').perform(context)
    camera_yaw = LaunchConfiguration('camera_yaw').perform(context)
    
    # Convert Euler angles (in degrees) to quaternion
    import math
    try:
        roll = float(camera_roll) * math.pi / 180.0
        pitch = float(camera_pitch) * math.pi / 180.0
        yaw = float(camera_yaw) * math.pi / 180.0
        
        # Convert Euler to quaternion (ZYX convention)
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
        # Default: no rotation
        qx, qy, qz, qw = 0.0, 0.0, 0.0, 1.0
    
    return [
        # Enable IR emitter for better depth quality
        SetParameter(name='depth_module.emitter_enabled', value=1),
        
        # Static transform from base_link to camera_link
        # This connects the robot base to the camera frame
        # Adjust x, y, z, roll, pitch, yaw based on your camera mounting
        # Default: -0.15m forward (0.15m backward), 0.1m up, no rotation (adjust as needed)
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='base_link_to_camera_link',
            arguments=[str(camera_x), str(camera_y), str(camera_z), 
                      str(qx), str(qy), str(qz), str(qw), 
                      'base_link', 'camera_link']
        ),
        
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
    ]
