#!/usr/bin/env python3
"""
Single-node Go2 controller bridge.

Publishes ``unitree_go/WirelessController`` on ``ros2_topic`` (default ``/wirelesscontroller``)
for the robot over DDS (e.g. eth0). MQTT JSON teleop has priority; after ``mqtt_timeout_sec`` without
MQTT, Nav2 ``cmd_vel`` is converted to ``WirelessController``.
If there is no new MQTT and no new ``cmd_vel`` for ``input_idle_timeout_sec``, all-zero
``WirelessController`` is published (set to ``0`` to disable).

Example::

    ros2 launch go2_controller go2_controller.launch.py
    ros2 launch go2_controller go2_controller.launch.py mqtt_broker:=localhost
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('mqtt_broker', default_value='10.1.106.210'),
        DeclareLaunchArgument('mqtt_port', default_value='1883'),
        DeclareLaunchArgument('mqtt_topic', default_value='/wirelesscontroller'),
        DeclareLaunchArgument('mqtt_client_id', default_value='go2_controller_bridge'),
        DeclareLaunchArgument('mqtt_retry_interval', default_value='5.0'),
        DeclareLaunchArgument('mqtt_connect_timeout', default_value='10.0'),
        DeclareLaunchArgument('ros2_topic', default_value='/wirelesscontroller'),
        DeclareLaunchArgument('cmd_vel_topic', default_value='/cmd_vel'),
        DeclareLaunchArgument('mqtt_timeout_sec', default_value='1.0'),
        DeclareLaunchArgument('publish_rate', default_value='50.0'),
        DeclareLaunchArgument('log_each_mqtt_message', default_value='true'),
        DeclareLaunchArgument('log_each_nav_publish', default_value='false'),
        DeclareLaunchArgument('log_each_wireless_publish', default_value='true'),
        DeclareLaunchArgument('input_idle_timeout_sec', default_value='1.0'),
        DeclareLaunchArgument('log_idle_zero_publish', default_value='false'),

        Node(
            package='go2_controller',
            executable='go2_controller_bridge.py',
            name='go2_controller_bridge',
            output='screen',
            parameters=[{
                'mqtt_broker': LaunchConfiguration('mqtt_broker'),
                'mqtt_port': LaunchConfiguration('mqtt_port'),
                'mqtt_topic': LaunchConfiguration('mqtt_topic'),
                'mqtt_client_id': LaunchConfiguration('mqtt_client_id'),
                'mqtt_retry_interval': LaunchConfiguration('mqtt_retry_interval'),
                'mqtt_connect_timeout': LaunchConfiguration('mqtt_connect_timeout'),
                'ros2_topic': LaunchConfiguration('ros2_topic'),
                'cmd_vel_topic': LaunchConfiguration('cmd_vel_topic'),
                'mqtt_timeout_sec': LaunchConfiguration('mqtt_timeout_sec'),
                'publish_rate': LaunchConfiguration('publish_rate'),
                'log_each_mqtt_message': LaunchConfiguration('log_each_mqtt_message'),
                'log_each_nav_publish': LaunchConfiguration('log_each_nav_publish'),
                'log_each_wireless_publish': LaunchConfiguration('log_each_wireless_publish'),
                'input_idle_timeout_sec': LaunchConfiguration('input_idle_timeout_sec'),
                'log_idle_zero_publish': LaunchConfiguration('log_idle_zero_publish'),
            }],
        ),
    ])
