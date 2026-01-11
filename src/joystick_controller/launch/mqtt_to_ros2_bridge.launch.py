#!/usr/bin/env python3
"""
Launch file for MQTT to ROS2 bridge.

This launch file starts the MQTT to ROS2 bridge node that subscribes to MQTT
and publishes WirelessController messages to ROS2.

Example:
    ros2 launch joystick_controller mqtt_to_ros2_bridge.launch.py
    ros2 launch joystick_controller mqtt_to_ros2_bridge.launch.py mqtt_broker:=192.168.1.100
    ros2 launch joystick_controller mqtt_to_ros2_bridge.launch.py mqtt_broker:=mosquitto mqtt_port:=1883 mqtt_topic:=/wirelesscontroller
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    
    # Launch arguments
    mqtt_broker_arg = DeclareLaunchArgument(
        'mqtt_broker',
        default_value='localhost',
        description='MQTT broker address'
    )
    
    mqtt_port_arg = DeclareLaunchArgument(
        'mqtt_port',
        default_value='1883',
        description='MQTT broker port'
    )
    
    mqtt_topic_arg = DeclareLaunchArgument(
        'mqtt_topic',
        default_value='/wirelesscontroller',
        description='MQTT topic to subscribe to'
    )
    
    mqtt_client_id_arg = DeclareLaunchArgument(
        'mqtt_client_id',
        default_value='joystick_controller_bridge',
        description='MQTT client ID'
    )
    
    ros2_topic_arg = DeclareLaunchArgument(
        'ros2_topic',
        default_value='/wirelesscontroller',
        description='ROS2 topic to publish to'
    )
    
    mqtt_retry_interval_arg = DeclareLaunchArgument(
        'mqtt_retry_interval',
        default_value='5.0',
        description='MQTT connection retry interval in seconds'
    )
    
    mqtt_connect_timeout_arg = DeclareLaunchArgument(
        'mqtt_connect_timeout',
        default_value='10.0',
        description='MQTT connection timeout in seconds'
    )
    
    # Node
    mqtt_to_ros2_bridge_node = Node(
        package='joystick_controller',
        executable='mqtt_to_ros2_bridge.py',
        name='mqtt_to_ros2_bridge',
        output='screen',
        parameters=[{
            'mqtt_broker': LaunchConfiguration('mqtt_broker'),
            'mqtt_port': LaunchConfiguration('mqtt_port'),
            'mqtt_topic': LaunchConfiguration('mqtt_topic'),
            'mqtt_client_id': LaunchConfiguration('mqtt_client_id'),
            'ros2_topic': LaunchConfiguration('ros2_topic'),
            'mqtt_retry_interval': LaunchConfiguration('mqtt_retry_interval'),
            'mqtt_connect_timeout': LaunchConfiguration('mqtt_connect_timeout'),
        }]
    )
    
    return LaunchDescription([
        mqtt_broker_arg,
        mqtt_port_arg,
        mqtt_topic_arg,
        mqtt_client_id_arg,
        ros2_topic_arg,
        mqtt_retry_interval_arg,
        mqtt_connect_timeout_arg,
        mqtt_to_ros2_bridge_node,
    ])
