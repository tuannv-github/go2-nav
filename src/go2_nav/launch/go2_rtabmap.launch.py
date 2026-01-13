#!/usr/bin/env python3
"""
Launch file for RTAB-Map SLAM for Go2 robot.

This launch file starts RTAB-Map visual SLAM components including:
- RGBD synchronization
- Visual odometry
- RTAB-Map SLAM or localization
- Point cloud processing for obstacle detection

Note: RealSense camera must be launched separately:
    ros2 launch go2_nav realsense.launch.py

Example:
    # First launch RealSense camera:
    ros2 launch go2_nav realsense.launch.py
    
    # Then launch RTAB-Map SLAM (mapping mode):
    ros2 launch go2_nav go2_rtabmap.launch.py use_sim_time:=false
    
    # Localization mode (using existing map):
    ros2 launch go2_nav go2_rtabmap.launch.py use_sim_time:=false localization:=true
    
    # With IMU filtering:
    ros2 launch go2_nav go2_rtabmap.launch.py use_sim_time:=false filter_imu:=true
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition, UnlessCondition
from launch_ros.actions import Node

def launch_setup(context, *args, **kwargs):
    
    localization = LaunchConfiguration('localization')
    use_sim_time = LaunchConfiguration("use_sim_time")
    use_imu_arg = LaunchConfiguration('use_imu')
    
    # Determine if IMU should be used
    # Default: disable IMU if use_sim_time is true, or if explicitly disabled
    use_imu_enabled = use_imu_arg.perform(context) == 'true'
    use_imu_default = use_sim_time.perform(context) not in ["true", "True"]
    use_imu = use_imu_enabled if use_imu_arg.perform(context) in ['true', 'false'] else use_imu_default
    
    # Only wait for IMU initialization if IMU filter is enabled (which computes orientation)
    # Raw IMU from Go2 may not have orientation, so don't wait for it
    filter_imu_enabled = LaunchConfiguration('filter_imu').perform(context) == 'true'
    wait_imu_to_init = use_imu and filter_imu_enabled
    
    # Database path for saving/loading maps
    database_path = LaunchConfiguration('database_path').perform(context) or os.path.expanduser('~/.ros/rtabmap.db')

    vslam_params = {
        'frame_id': 'base_link',
        'guess_frame_id': 'vo',  # Use 'vo' since rgbd_odometry publishes to 'vo', not 'odom'
        'approx_sync': False,
        'use_sim_time': use_sim_time,
        'subscribe_rgbd': True,
        'subscribe_odom_info': True,
        'use_action_for_goal': True,
        'wait_imu_to_init': wait_imu_to_init,
        'wait_for_transform': 0.5,
        'database_path': database_path,
        # RTAB-Map's parameters should be strings
        'Grid/DepthDecimation': '1',
        'Grid/RangeMax': '2',
        'GridGlobal/MinSize': '20',
        'Grid/MinClusterSize': '20',
        'Grid/MaxObstacleHeight': '2',
        'Odom/ResetCountdown': '2',
        'Kp/RoiRatios': '0.0 0.0 0.0 0.4'  # ignore ground for loop closure detection
    }
    
    # IMU topic selection: Always use timestamp-fixed IMU from /input/imu (filtered if filter_imu is enabled)
    imu_topic = '/input/imu/filtered' if filter_imu_enabled else '/input/imu'
    
    vslam_remappings = [
        ('odom', 'vo')
    ]
    
    # Only add IMU remapping if IMU is enabled
    if use_imu:
        vslam_remappings.append(('imu', imu_topic))
    
    return [
        # Static transform from base_link to IMU frame
        # Transform: x y z qx qy qz qw (0 0 0 0 0 0 1 = identity transform)
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='base_link_to_utlidar_imu',
            arguments=['0', '0', '0', '0', '0', '0', '1', 'base_link', 'utlidar_imu']
        ),
        
        # IMU timestamp fixer - republishes IMU with fresh timestamps
        # This fixes issues where IMU timestamps are stale or incorrect
        # Always enabled to ensure proper timestamp synchronization
        Node(
            package='go2_nav',
            executable='imu_timestamp_fixer_node.py',
            name='imu_timestamp_fixer',
            output='screen',
            parameters=[{
                'input_topic': '/utlidar/imu',
                'output_topic': '/input/imu',
                'frame_id': 'utlidar_imu'
            }]
        ),
        
        # Compute imu orientation (if needed, otherwise use raw IMU)
        # Note: Go2's IMU might already be filtered, adjust if needed
        # Always uses timestamp-fixed IMU from /input/imu
        Node(
            package='imu_filter_madgwick',
            executable='imu_filter_madgwick_node',
            output='screen',
            parameters=[{
                'use_mag': False,
                'world_frame': 'enu',
                'publish_tf': False
            }],
            remappings=[
                ('imu/data_raw', '/input/imu'),
                ('imu/data', '/input/imu/filtered')
            ],
            condition=IfCondition(LaunchConfiguration("filter_imu"))
        ),
        
        # VSLAM nodes:
        Node(
            package='rtabmap_sync',
            executable='rgbd_sync',
            output='screen',
            parameters=[vslam_params],
            remappings=[
                ('rgb/image', '/input/camera/camera/color/image_raw'),
                ('rgb/camera_info', '/input/camera/camera/color/camera_info'),
                ('depth/image', '/input/camera/camera/aligned_depth_to_color/image_raw')
            ]
        ),

        Node(
            package='rtabmap_odom',
            executable='rgbd_odometry',
            output='screen',
            parameters=[vslam_params, {'odom_frame_id': 'vo'}],
            remappings=vslam_remappings,
            arguments=["--ros-args", "--log-level", 'info']
        ),

        # SLAM Mode:
        Node(
            condition=UnlessCondition(localization),
            package='rtabmap_slam',
            executable='rtabmap',
            output='screen',
            parameters=[vslam_params],
            remappings=vslam_remappings,
            arguments=['-d']
        ),
            
        # Localization mode:
        Node(
            condition=IfCondition(localization),
            package='rtabmap_slam',
            executable='rtabmap',
            output='screen',
            parameters=[vslam_params, 
                {
                    'Mem/IncrementalMemory': 'False',
                    'Mem/InitWMWithAllNodes': 'True'
                }
            ],
            remappings=vslam_remappings
        ),
    ]

def generate_launch_description():
    
    return LaunchDescription([
        DeclareLaunchArgument(
            name='use_sim_time', 
            default_value='false',
            description='Use simulation (Gazebo) clock if true'
        ),

        DeclareLaunchArgument(
            name='filter_imu',
            default_value='false',
            description='Filter IMU data using imu_filter_madgwick (set to true if IMU needs filtering)'
        ),

        DeclareLaunchArgument(
            name='use_imu',
            default_value='',
            description='Enable/disable IMU usage. Empty = auto (disabled in sim, enabled otherwise). Set to "true" or "false" to override.'
        ),

        DeclareLaunchArgument(
            'localization',
            default_value='false',
            choices=['true', 'false'],
            description='Launch rtabmap in localization mode (a map should have been already created).'
        ),
        
        DeclareLaunchArgument(
            'database_path',
            default_value='',
            description='Path to RTAB-Map database file. Default: ~/.ros/rtabmap.db. The map will be automatically saved here.'
        ),
        
        OpaqueFunction(function=launch_setup)
    ])
