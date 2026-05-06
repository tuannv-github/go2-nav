#!/usr/bin/env python3
"""
Launch file for RTAB-Map visualization.

This launch file starts RTAB-Map visualization tool for viewing maps, graphs, and statistics.

Example:
    ros2 launch go2_nav go2_rtabmap_viz.launch.py
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def launch_setup(context, *args, **kwargs):
    use_sim_time = LaunchConfiguration('use_sim_time')
    filter_imu_enabled = LaunchConfiguration('filter_imu').perform(context) == 'true'

    vslam_params = {
        'frame_id': 'base_link',
        'guess_frame_id': 'odom',
        'approx_sync': False,
        'use_sim_time': use_sim_time,
        'subscribe_rgbd': True,
        'subscribe_odom_info': True,
        'use_action_for_goal': True,
        'wait_for_transform': 0.5,
        # RTAB-Map's parameters should be strings
        'Grid/DepthDecimation': '1',
        'Grid/RangeMax': '2',
        'GridGlobal/MinSize': '20',
        'Grid/MinClusterSize': '20',
        'Grid/MaxObstacleHeight': '2',
        'Odom/ResetCountdown': '2',
        'Kp/RoiRatios': '0.0 0.0 0.0 0.4'  # ignore ground for loop closure detection
    }
    
    # IMU topic selection logic:
    # Always use timestamp-fixed IMU from /input/imu (filtered if filter_imu is enabled)
    imu_topic = '/input/imu/filtered' if filter_imu_enabled else '/input/imu'
    
    # Allow override via launch argument
    imu_topic_override = LaunchConfiguration('imu_topic').perform(context)
    if imu_topic_override and imu_topic_override != '':
        imu_topic = imu_topic_override
    
    vslam_remappings = [
        ('imu', imu_topic),
        ('odom', 'vo')
    ]
    
    return [
        Node(
            package='rtabmap_viz',
            executable='rtabmap_viz',
            name='rtabmap_viz',
            output='screen',
            parameters=[vslam_params],
            remappings=vslam_remappings
        ),
    ]


def generate_launch_description():
    
    return LaunchDescription([
        DeclareLaunchArgument(
            name='use_sim_time',
            default_value='false',
            choices=['true', 'false'],
            description='Simulation / bag replay clock: true uses /clock. Default false (wall clock / robot).',
        ),
        DeclareLaunchArgument(
            name='imu_topic',
            default_value='',
            description='IMU topic to use (empty = auto-select based on filter_imu, always uses timestamp-fixed /input/imu)'
        ),
        
        DeclareLaunchArgument(
            name='filter_imu',
            default_value='false',
            description='Filter IMU data using imu_filter_madgwick (set to true if IMU needs filtering)'
        ),
        
        OpaqueFunction(function=launch_setup)
    ])
