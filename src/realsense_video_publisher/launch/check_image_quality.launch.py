#!/usr/bin/env python3
"""
Launch file for Image Quality Checker.

This launch file starts the image quality checker node that monitors
the realsense camera topic and reports image quality metrics.

Example:
    ros2 launch realsense_video_publisher check_image_quality.launch.py
    ros2 launch realsense_video_publisher check_image_quality.launch.py check_duration:=30.0 save_sample:=true
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    
    # Launch arguments
    input_topic_arg = DeclareLaunchArgument(
        'input_topic',
        default_value='/input/camera/camera/color/image_raw',
        description='ROS2 topic to check image quality from'
    )
    
    check_duration_arg = DeclareLaunchArgument(
        'check_duration',
        default_value='10.0',
        description='Duration in seconds to check image quality'
    )
    
    save_sample_arg = DeclareLaunchArgument(
        'save_sample',
        default_value='false',
        description='Save a sample image to disk'
    )
    
    sample_path_arg = DeclareLaunchArgument(
        'sample_path',
        default_value='/tmp/camera_sample.jpg',
        description='Path to save sample image (if save_sample is true)'
    )
    
    # Node
    image_quality_checker_node = Node(
        package='realsense_video_publisher',
        executable='check_image_quality.py',
        name='image_quality_checker',
        output='screen',
        parameters=[{
            'input_topic': LaunchConfiguration('input_topic'),
            'check_duration': LaunchConfiguration('check_duration'),
            'save_sample': LaunchConfiguration('save_sample'),
            'sample_path': LaunchConfiguration('sample_path'),
        }]
    )
    
    return LaunchDescription([
        input_topic_arg,
        check_duration_arg,
        save_sample_arg,
        sample_path_arg,
        image_quality_checker_node,
    ])
