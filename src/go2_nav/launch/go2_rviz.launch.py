#!/usr/bin/env python3
"""
Launch file for RViz visualization for Go2 navigation.

This launch file starts RViz2 with the Go2 navigation configuration.

Example:
    ros2 launch go2_nav go2_rviz.launch.py
    ros2 launch go2_nav go2_rviz.launch.py use_sim_time:=true
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
from launch_ros.actions import Node


def generate_launch_description():
    
    rviz_config_path = PathJoinSubstitution(
        [FindPackageShare('go2_nav'), 'rviz', 'go2_navigation.rviz']
    )
    
    use_sim_time = LaunchConfiguration("use_sim_time")
    
    return LaunchDescription([
        DeclareLaunchArgument(
            name='use_sim_time', 
            default_value='false',
            description='Use simulation (Gazebo) clock if true'
        ),
        
        DeclareLaunchArgument(
            name='rviz_config',
            default_value=rviz_config_path,
            description='Path to RViz config file'
        ),

        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            output='screen',
            arguments=['-d', LaunchConfiguration('rviz_config')],
            parameters=[{'use_sim_time': use_sim_time}]
        ),
    ])
