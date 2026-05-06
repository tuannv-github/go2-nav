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
    ros2 launch go2_nav go2_rtabmap.location.launch.py

    # Localization mode (using existing map):
    ros2 launch go2_nav go2_rtabmap.location.launch.py localization:=true

    # With IMU filtering:
    ros2 launch go2_nav go2_rtabmap.location.launch.py filter_imu:=true
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch.conditions import IfCondition, UnlessCondition
from launch_ros.actions import Node

def get_workspace_root():
    """Get workspace root directory by finding the directory containing 'src'."""
    # Get the launch file's directory
    launch_file_path = os.path.abspath(__file__)
    current_dir = os.path.dirname(launch_file_path)
    
    # Go up until we find a directory with 'src' subdirectory (workspace root)
    # This works for both source and installed packages
    max_levels = 10  # Safety limit to avoid infinite loops
    level = 0
    while level < max_levels and current_dir != os.path.dirname(current_dir):
        if os.path.exists(os.path.join(current_dir, 'src')):
            return current_dir
        current_dir = os.path.dirname(current_dir)
        level += 1
    
    # Fallback: go up 3 levels from launch file location
    # (src/go2_nav/launch -> workspace root)
    launch_file_dir = os.path.dirname(launch_file_path)
    return os.path.dirname(os.path.dirname(os.path.dirname(launch_file_dir)))

def launch_setup(context, *args, **kwargs):
    
    localization = LaunchConfiguration('localization')
    use_sim_time = LaunchConfiguration('use_sim_time')
    use_imu_arg = LaunchConfiguration('use_imu')

    # Default: disable IMU if use_sim_time is true, or if explicitly disabled
    use_imu_enabled = use_imu_arg.perform(context) == 'true'
    use_imu_default = use_sim_time.perform(context) not in ['true', 'True']
    use_imu = use_imu_enabled if use_imu_arg.perform(context) in ['true', 'false'] else use_imu_default
    
    # Only wait for IMU initialization if IMU filter is enabled (which computes orientation)
    # Raw IMU from Go2 may not have orientation, so don't wait for it
    filter_imu_enabled = LaunchConfiguration('filter_imu').perform(context) == 'true'
    wait_imu_to_init = use_imu and filter_imu_enabled
    
    # Database path for saving/loading maps
    # Only use database from PROJECT_ROOT_DIR/map, don't fall back to ~/.ros/rtabmap.db
    provided_db_path = LaunchConfiguration('database_path').perform(context)
    database_exists = False
    
    if provided_db_path:
        # Use explicitly provided database path
        database_path = provided_db_path
        database_exists = os.path.exists(database_path)
        if database_exists:
            print(f"[go2_rtabmap] Using provided RTAB-Map database: {database_path}")
        else:
            print(f"[go2_rtabmap] Provided database path does not exist, will create new: {database_path}")
    else:
        # Only use database from project map directory
        workspace_dir = get_workspace_root()
        map_db_path = os.path.join(workspace_dir, 'map', 'rtabmap.db')
        database_path = map_db_path
        
        if os.path.exists(map_db_path):
            database_exists = True
            print(f"[go2_rtabmap] RTAB-Map database found in map directory: {database_path}")
        else:
            database_exists = False
            print(f"[go2_rtabmap] No database found in map directory, will create new: {database_path}")
            print(f"  (Database will be saved to: {database_path})")

    vslam_params = {
        'frame_id': 'base_link',
        'guess_frame_id': 'vo',  # Use 'vo' since rgbd_odometry publishes to 'vo', not 'odom'
        'Reg/Force3DoF': 'true',  # Constrain visual odometry to planar motion (z/roll/pitch fixed)
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
        'Grid/RangeMax': '3',
        'GridGlobal/MinSize': '20',
        'Grid/MinClusterSize': '20',
        'Grid/MaxObstacleHeight': '2',
        'Odom/ResetCountdown': '2',
        'Kp/RoiRatios': '0.0 0.0 0.0 0.4'  # ignore ground for loop closure detection
    }
    
    # IMU topic selection: use timestamp-fixed IMU (filtered if filter_imu is enabled)
    imu_topic = '/input/imu/filtered' if filter_imu_enabled else '/input/imu'
    
    vslam_remappings = [
        ('odom', 'vo')
    ]
    
    # Only add IMU remapping if IMU is enabled
    if use_imu:
        vslam_remappings.append(('imu', imu_topic))
    
    return [
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

        Node(
            package='location_publisher',
            executable='location_publisher',
            name='location_publisher',
            output='screen'
        ),

        # SLAM Mode:
        Node(
            condition=UnlessCondition(localization),
            package='rtabmap_slam',
            executable='rtabmap',
            output='screen',
            parameters=[vslam_params] + ([
                {'Mem/InitWMWithAllNodes': 'True'}  # Load all nodes from existing database
            ] if database_exists else []),
            remappings=vslam_remappings,
            arguments=[] if database_exists else ['-d']  # Don't delete if database exists
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
    # Set up log directory in project root (for tee redirection)
    workspace_dir = get_workspace_root()
    log_dir = os.path.join(workspace_dir, 'log')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'go2_rtabmap.launch.log')
    print(f"[go2_rtabmap] Use tee to capture logs: ros2 launch go2_nav go2_rtabmap.launch.py 2>&1 | tee -a {log_file}")
    
    return LaunchDescription([
        DeclareLaunchArgument(
            name='use_sim_time',
            default_value='false',
            choices=['true', 'false'],
            description='Simulation / bag replay clock: true uses /clock. Default false (wall clock / robot).',
        ),
        DeclareLaunchArgument(
            name='filter_imu',
            default_value='false',
            description='Filter IMU data using imu_filter_madgwick (set to true if IMU needs filtering)'
        ),

        DeclareLaunchArgument(
            name='use_imu',
            default_value='false',
            description='Enable/disable IMU usage. Empty = auto (disabled when use_sim_time is true, enabled otherwise). Set to "true" or "false" to override.',
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
            description='Path to RTAB-Map database file. If not provided, uses PROJECT_ROOT_DIR/map/rtabmap.db. The map will be automatically saved to the specified or default location.'
        ),
        
        OpaqueFunction(function=launch_setup)
    ])
