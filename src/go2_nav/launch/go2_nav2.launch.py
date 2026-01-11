#!/usr/bin/env python3
"""
Launch file for Nav2 navigation for Go2 robot.

This launch file starts Nav2 navigation stack configured for Go2 robot.
It uses visual odometry from RTAB-Map and segmented point clouds for costmaps.
Includes point cloud processing nodes for Nav2 costmap layers.

Example:
    ros2 launch go2_nav go2_nav2.launch.py use_sim_time:=false
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.substitutions import FindPackageShare
from launch_ros.actions import Node

def generate_launch_description():
    
    navigation_launch_path = PathJoinSubstitution(
        [FindPackageShare('nav2_bringup'), 'launch', 'navigation_launch.py']
    )
    
    nav2_params_file = PathJoinSubstitution(
        [FindPackageShare('go2_nav'), 'params', 'go2_nav2_params.yaml']
    )
    
    use_sim_time = LaunchConfiguration("use_sim_time")
    
    # Parameters for point cloud processing (used by obstacles_detection)
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
        'Kp/RoiRatios': '0.0 0.0 0.0 0.4'
    }
    
    return LaunchDescription([
        DeclareLaunchArgument(
            name='use_sim_time', 
            default_value='false',
            description='Use simulation (Gazebo) clock if true'
        ),

        # Compute ground/obstacle clouds for nav2 voxel layers
        Node(
            package='rtabmap_util',
            executable='point_cloud_xyz',
            output='screen',
            parameters=[{
                'decimation': 2,
                'max_depth': 3.0,
                'voxel_size': 0.02
            }],
            remappings=[
                ('depth/image', '/input/camera/camera/aligned_depth_to_color/image_raw'),
                ('depth/camera_info', '/input/camera/camera/aligned_depth_to_color/camera_info'),
                ('cloud', '/input/camera/cloud')
            ]
        ),
        
        Node(
            package='rtabmap_util',
            executable='obstacles_detection',
            output='screen',
            parameters=[vslam_params],
            remappings=[
                ('cloud', '/input/camera/cloud'),
                ('obstacles', '/output/obstacles'),
                ('ground', '/output/ground')
            ]
        ),

        # Launch Nav2 navigation
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(navigation_launch_path),
            launch_arguments={
                'use_sim_time': use_sim_time,
                'params_file': nav2_params_file
            }.items()
        ),
    ])
