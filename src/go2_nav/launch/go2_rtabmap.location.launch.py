#!/usr/bin/env python3
"""
Launch file for RTAB-Map SLAM for Go2 robot.

RTAB-Map with RGB-D + Livox fusion plus ``location_publisher``.

Example:
    ros2 launch go2_nav realsense.launch.py
    ros2 launch go2_nav livox_mid360.launch.py
    ros2 launch go2_nav go2_rtabmap.location.launch.py
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
    rtab_cpu_affinity = LaunchConfiguration('rtab_cpu_affinity').perform(context)
    rtab_prefix = f'taskset -c {rtab_cpu_affinity}'

    # Default: disable IMU if use_sim_time is true, or if explicitly disabled
    use_imu_enabled = use_imu_arg.perform(context) == 'true'
    use_imu_default = use_sim_time.perform(context) not in ['true', 'True']
    use_imu = use_imu_enabled if use_imu_arg.perform(context) in ['true', 'false'] else use_imu_default
    
    # Only wait for IMU initialization if IMU filter is enabled (which computes orientation)
    # Raw IMU from Go2 may not have orientation, so don't wait for it
    filter_imu_enabled = LaunchConfiguration('filter_imu').perform(context) == 'true'
    wait_imu_to_init = use_imu and filter_imu_enabled

    scan_cloud_topic = LaunchConfiguration('scan_cloud_topic').perform(context)
    enable_livox_cloud = LaunchConfiguration('enable_livox_cloud').perform(context) == 'true'

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

    base_params = {
        'frame_id': 'base_link',
        'guess_frame_id': 'vo',
        'Reg/Force3DoF': 'true',
        'approx_sync': True,
        'sync_queue_size': 30,
        'topic_queue_size': 30,
        'use_sim_time': use_sim_time,
        'use_action_for_goal': True,
        'wait_imu_to_init': wait_imu_to_init,
        'wait_for_transform': 0.5,
        'database_path': database_path,
        'Grid/DepthDecimation': '1',
        'Grid/RangeMax': '30',
        'GridGlobal/MinSize': '20',
        'Grid/MinClusterSize': '20',
        # 2D occupancy in map frame. After odom reset, z=0 is lowest pose (on ground).
        'Grid/3D': 'false',
        'Grid/MapFrameProjection': 'true',
        'Grid/NormalsSegmentation': 'false',
        'Grid/MinGroundHeight': '-0.20',
        'Grid/MaxGroundHeight': '0.08',
        'Grid/MaxObstacleHeight': '0.5',
        'Grid/RangeMin': '0.45',
        'Grid/FootprintLength': '0.90',
        'Grid/FootprintWidth': '0.50',
        'Grid/FootprintHeight': '0.45',
        'Odom/ResetCountdown': '2',
        'Kp/RoiRatios': '0.0 0.0 0.0 0.4',
    }

    sync_odom_params = {
        **base_params,
        'subscribe_rgbd': True,
        'subscribe_odom_info': True,
    }

    rgbd_sync_params = {
        **sync_odom_params,
        'approx_sync_max_interval': 0.2,
    }

    rtab_params = {
        **base_params,
        'subscribe_rgbd': True,
        'subscribe_scan_cloud': enable_livox_cloud,
        'scan_cloud_is_2d': False,
        'subscribe_odom_info': True,
    }

    imu_topic = '/input/imu/filtered' if filter_imu_enabled else '/input/imu'

    odom_remappings = [('odom', 'vo')]
    if use_imu:
        odom_remappings.append(('imu', imu_topic))

    rtab_remappings = [('odom', 'vo')]
    if enable_livox_cloud:
        rtab_remappings.append(('scan_cloud', scan_cloud_topic))
    if use_imu:
        rtab_remappings.append(('imu', imu_topic))

    return [
        Node(
            package='rtabmap_sync',
            executable='rgbd_sync',
            output='screen',
            prefix=rtab_prefix,
            parameters=[rgbd_sync_params],
            remappings=[
                ('rgb/image', '/input/camera/camera/color/image_raw'),
                ('rgb/camera_info', '/input/camera/camera/color/camera_info'),
                ('depth/image', '/input/camera/camera/aligned_depth_to_color/image_raw'),
            ],
        ),
        Node(
            package='rtabmap_odom',
            executable='rgbd_odometry',
            output='screen',
            prefix=rtab_prefix,
            parameters=[sync_odom_params, {'odom_frame_id': 'vo'}],
            remappings=odom_remappings,
            arguments=['--ros-args', '--log-level', 'info'],
        ),
        Node(
            package='location_publisher',
            executable='location_publisher',
            name='location_publisher',
            output='screen',
        ),
        Node(
            condition=UnlessCondition(localization),
            package='rtabmap_slam',
            executable='rtabmap',
            output='screen',
            prefix=rtab_prefix,
            parameters=[rtab_params] + ([
                {'Mem/InitWMWithAllNodes': 'True'}
            ] if database_exists else []),
            remappings=rtab_remappings,
            arguments=[] if database_exists else ['-d'],
        ),
        Node(
            condition=IfCondition(localization),
            package='rtabmap_slam',
            executable='rtabmap',
            output='screen',
            prefix=rtab_prefix,
            parameters=[rtab_params, {
                'Mem/IncrementalMemory': 'False',
                'Mem/InitWMWithAllNodes': 'True',
            }],
            remappings=rtab_remappings,
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
        DeclareLaunchArgument(
            'rtab_cpu_affinity',
            default_value='0-4',
            description='CPU affinity for RTAB-Map nodes. Default 0-4 keeps RTAB stack within ~500% CPU total.'
        ),
        DeclareLaunchArgument(
            'scan_cloud_topic',
            default_value='/livox/lidar',
            description='Livox PointCloud2 topic for rtabmap scan_cloud.',
        ),
        DeclareLaunchArgument(
            'enable_livox_cloud',
            default_value='true',
            choices=['true', 'false'],
            description='If true, rtabmap subscribes to Livox scan_cloud in addition to RGB-D.',
        ),

        OpaqueFunction(function=launch_setup)
    ])
