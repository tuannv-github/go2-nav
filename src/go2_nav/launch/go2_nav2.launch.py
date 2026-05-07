#!/usr/bin/env python3
"""
Launch Nav2 navigation stack for Unitree Go2 using ``go2_nav2_params.yaml``.

This includes only ``navigation_launch.py`` from ``nav2_bringup`` (controller, planner,
behaviors, BT navigator, waypoint follower, velocity smoother). It does **not** start
``map_server`` or AMCL; run SLAM/localization separately (e.g. RTAB-Map) so ``/map``
and the ``map`` → odometry frame chain exist before navigating.

Prerequisites (typical on-hardware flow):

1. ``ros2 launch go2_nav realsense.launch.py``
2. ``ros2 launch go2_nav go2_rtabmap.launch.py`` (or ``localization:=true`` with a map DB)
3. ``ros2 launch go2_nav go2_nav2.launch.py``

Optional RViz: ``ros2 launch go2_nav go2_rviz.launch.py``

Example:

    ros2 launch go2_nav go2_nav2.launch.py

    ros2 launch go2_nav go2_nav2.launch.py use_sim_time:=true

    ros2 launch go2_nav go2_nav2.launch.py params_file:=/path/to/custom.yaml
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')
    navigation_launch = os.path.join(nav2_bringup_dir, 'launch', 'navigation_launch.py')

    default_params = PathJoinSubstitution(
        [FindPackageShare('go2_nav'), 'params', 'go2_nav2_params.yaml'])

    return LaunchDescription([
        DeclareLaunchArgument(
            'namespace',
            default_value='',
            description='Top-level namespace for Nav2 (empty = root).',
        ),
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            choices=['true', 'false'],
            description='Use /clock when replaying bags or simulation.',
        ),
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Nav2 parameters YAML (default: go2_nav2_params.yaml in go2_nav).',
        ),
        DeclareLaunchArgument(
            'autostart',
            default_value='true',
            description='Lifecycle manager autostart for navigation nodes.',
        ),
        DeclareLaunchArgument(
            'use_composition',
            default_value='False',
            choices=['True', 'False'],
            description=(
                'If True, load Nav2 nodes into an existing component container '
                '(requires a separate container launch). Default False for this wrapper. '
                'Must be capitalized True/False (Nav2 PythonExpression).'
            ),
        ),
        DeclareLaunchArgument(
            'use_respawn',
            default_value='False',
            choices=['True', 'False'],
            description=(
                'Respawn Nav2 nodes on exit (non-composed mode). '
                'Use capitalized True/False to match Nav2 defaults.'
            ),
        ),
        DeclareLaunchArgument(
            'container_name',
            default_value='nav2_container',
            description='Target component container name when use_composition is true.',
        ),
        DeclareLaunchArgument(
            'log_level',
            default_value='info',
            description='ROS logging level for Nav2 nodes.',
        ),
        DeclareLaunchArgument(
            'project_parent_frame',
            default_value='map',
            description='Parent frame for base_link_project (z=0 is enforced in this frame).',
        ),
        DeclareLaunchArgument(
            'project_base_frame',
            default_value='base_link',
            description='Input base frame to project onto parent XY plane.',
        ),
        DeclareLaunchArgument(
            'projected_frame',
            default_value='base_link_project',
            description='Output projected frame name (z=0, yaw only).',
        ),
        DeclareLaunchArgument(
            'project_tf_rate_hz',
            default_value='30.0',
            description='Publish rate for base_link_project TF.',
        ),
        DeclareLaunchArgument(
            'enable_goal_server',
            default_value='true',
            choices=['true', 'false'],
            description='Launch REST goal server that publishes to /goal_pose.',
        ),
        DeclareLaunchArgument(
            'goal_server_host',
            default_value='0.0.0.0',
            description='REST goal server bind host.',
        ),
        DeclareLaunchArgument(
            'goal_server_port',
            default_value='8080',
            description='REST goal server bind port.',
        ),
        DeclareLaunchArgument(
            'goal_server_frame_id',
            default_value='map',
            description='Default frame_id for goals received from REST API.',
        ),
        Node(
            package='go2_nav',
            executable='base_link_project_tf',
            name='base_link_project_tf',
            output='screen',
            parameters=[{
                'parent_frame': LaunchConfiguration('project_parent_frame'),
                'base_frame': LaunchConfiguration('project_base_frame'),
                'projected_frame': LaunchConfiguration('projected_frame'),
                'publish_rate_hz': LaunchConfiguration('project_tf_rate_hz'),
            }],
        ),
        Node(
            package='go2_nav',
            executable='goal_server',
            name='goal_server',
            output='screen',
            condition=IfCondition(LaunchConfiguration('enable_goal_server')),
            additional_env={'PYTHONNOUSERSITE': '1'},
            parameters=[{
                'goal_topic': '/goal_pose',
                'default_frame_id': LaunchConfiguration('goal_server_frame_id'),
                'api_host': LaunchConfiguration('goal_server_host'),
                'api_port': LaunchConfiguration('goal_server_port'),
            }],
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(navigation_launch),
            launch_arguments={
                'namespace': LaunchConfiguration('namespace'),
                'use_sim_time': LaunchConfiguration('use_sim_time'),
                'params_file': LaunchConfiguration('params_file'),
                'autostart': LaunchConfiguration('autostart'),
                'use_composition': LaunchConfiguration('use_composition'),
                'use_respawn': LaunchConfiguration('use_respawn'),
                'container_name': LaunchConfiguration('container_name'),
                'log_level': LaunchConfiguration('log_level'),
            }.items(),
        ),
    ])
