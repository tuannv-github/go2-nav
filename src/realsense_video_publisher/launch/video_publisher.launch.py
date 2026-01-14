#!/usr/bin/env python3
"""
Launch file for Realsense Video Publisher.

This launch file starts the video publisher node that subscribes to realsense camera
and publishes video stream using GStreamer.

Example:
    ros2 launch realsense_video_publisher video_publisher.launch.py
    ros2 launch realsense_video_publisher video_publisher.launch.py stream_path:=live/mystream
    ros2 launch realsense_video_publisher video_publisher.launch.py use_nvidia_hw:=false
    ros2 launch realsense_video_publisher video_publisher.launch.py stream_type:=udp stream_host:=192.168.1.100 stream_port:=5000
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
        description='ROS2 topic to subscribe to for camera images'
    )
    
    stream_host_arg = DeclareLaunchArgument(
        'stream_host',
        default_value='129.126.114.218',
        description='Host address for video stream (RTMP/UDP/RTP)'
    )
    
    stream_port_arg = DeclareLaunchArgument(
        'stream_port',
        default_value='1935',
        description='Port for video stream (RTMP default: 1935, UDP/RTP: 5000)'
    )
    
    stream_path_arg = DeclareLaunchArgument(
        'stream_path',
        default_value='stream/go2/front',
        description='RTMP stream path/key (e.g., stream/go2/front, live/stream)'
    )
    
    bitrate_arg = DeclareLaunchArgument(
        'bitrate',
        default_value='2000000',
        description='Video bitrate in bps (for NVIDIA encoder) or kbps (for software encoder). Default: 2000000 (2Mbps)'
    )
    
    fps_arg = DeclareLaunchArgument(
        'fps',
        default_value='30',
        description='Target frames per second'
    )
    
    width_arg = DeclareLaunchArgument(
        'width',
        default_value='640',
        description='Output video width in pixels'
    )
    
    height_arg = DeclareLaunchArgument(
        'height',
        default_value='480',
        description='Output video height in pixels'
    )
    
    stream_type_arg = DeclareLaunchArgument(
        'stream_type',
        default_value='rtmp',
        description='Stream type: rtmp (default), udp, rtp, or rtsp'
    )
    
    use_nvidia_hw_arg = DeclareLaunchArgument(
        'use_nvidia_hw',
        default_value='true',
        description='Use NVIDIA hardware acceleration for encoding (requires NVIDIA GPU)'
    )
    
    # Node
    video_publisher_node = Node(
        package='realsense_video_publisher',
        executable='video_publisher.py',
        name='realsense_video_publisher',
        output='screen',
        parameters=[{
            'input_topic': LaunchConfiguration('input_topic'),
            'stream_host': LaunchConfiguration('stream_host'),
            'stream_port': LaunchConfiguration('stream_port'),
            'stream_path': LaunchConfiguration('stream_path'),
            'bitrate': LaunchConfiguration('bitrate'),
            'fps': LaunchConfiguration('fps'),
            'width': LaunchConfiguration('width'),
            'height': LaunchConfiguration('height'),
            'stream_type': LaunchConfiguration('stream_type'),
            'use_nvidia_hw': LaunchConfiguration('use_nvidia_hw'),
        }]
    )
    
    return LaunchDescription([
        input_topic_arg,
        stream_host_arg,
        stream_port_arg,
        stream_path_arg,
        bitrate_arg,
        fps_arg,
        width_arg,
        height_arg,
        stream_type_arg,
        use_nvidia_hw_arg,
        video_publisher_node,
    ])
