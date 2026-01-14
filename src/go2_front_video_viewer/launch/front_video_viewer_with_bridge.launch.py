#!/usr/bin/env python3
"""
Launch file for Front Video Viewer with Bridge.

This launch file starts:
1. A bridge node that converts Go2FrontVideoData to CompressedImage
2. The video viewer that displays CompressedImage using GStreamer

This approach avoids CycloneDDS deserialization issues by using standard ROS messages.

Example:
    ros2 launch go2_front_video_viewer front_video_viewer_with_bridge.launch.py
    ros2 launch go2_front_video_viewer front_video_viewer_with_bridge.launch.py display_width:=1920 display_height:=1080
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    
    # Launch arguments
    input_topic_arg = DeclareLaunchArgument(
        'input_topic',
        default_value='/frontvideostream',
        description='Input topic (Go2FrontVideoData)'
    )
    
    output_topic_arg = DeclareLaunchArgument(
        'output_topic',
        default_value='/frontvideostream/compressed',
        description='Output topic (CompressedImage)'
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
    
    # Bridge node - converts Go2FrontVideoData to CompressedImage
    video_bridge_node = Node(
        package='go2_front_video_viewer',
        executable='video_bridge_node.py',
        name='video_bridge',
        output='screen',
        parameters=[{
            'input_topic': LaunchConfiguration('input_topic'),
            'output_topic': LaunchConfiguration('output_topic'),
            'use_720p': True,
        }]
    )
    
    # Video viewer node - displays CompressedImage
    front_video_viewer_node = Node(
        package='go2_front_video_viewer',
        executable='front_video_viewer_node.py',
        name='front_video_viewer',
        output='screen',
        parameters=[{
            'topic': LaunchConfiguration('output_topic'),
            'display_width': LaunchConfiguration('display_width'),
            'display_height': LaunchConfiguration('display_height'),
        }]
    )
    
    return LaunchDescription([
        input_topic_arg,
        output_topic_arg,
        display_width_arg,
        display_height_arg,
        video_bridge_node,
        front_video_viewer_node,
    ])
