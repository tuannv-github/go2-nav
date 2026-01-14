#!/usr/bin/env python3
"""
Launch file for Front Video Viewer.

This launch file starts the front video viewer node that subscribes to /frontvideostream
and displays the video using GStreamer.

Example:
    ros2 launch go2_front_video_viewer front_video_viewer.launch.py
    ros2 launch go2_front_video_viewer front_video_viewer.launch.py topic:=/frontvideostream display_width:=1920 display_height:=1080

Note: Only video720p is used. video360p and video180p are ignored due to CycloneDDS
deserialization issues with large arrays. CycloneDDS errors may still appear in logs
but won't prevent video playback.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    
    # Launch arguments
    topic_arg = DeclareLaunchArgument(
        'topic',
        default_value='/frontvideostream',
        description='ROS2 topic to subscribe to for video stream'
    )
    
    display_width_arg = DeclareLaunchArgument(
        'display_width',
        default_value='1280',
        description='Display window width in pixels'
    )
    
    display_height_arg = DeclareLaunchArgument(
        'display_height',
        default_value='720',
        description='Display window height in pixels'
    )
    
    # Node
    front_video_viewer_node = Node(
        package='go2_front_video_viewer',
        executable='front_video_viewer_node.py',
        name='front_video_viewer',
        output='screen',
        parameters=[{
            'topic': LaunchConfiguration('topic'),
            'display_width': LaunchConfiguration('display_width'),
            'display_height': LaunchConfiguration('display_height'),
        }]
    )
    
    return LaunchDescription([
        topic_arg,
        display_width_arg,
        display_height_arg,
        front_video_viewer_node,
    ])
