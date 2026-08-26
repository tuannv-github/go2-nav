#!/usr/bin/env python3
"""
Publish and execute a list of waitpoints/waypoints from a CSV file for ROS 2 Nav2.

CSV Format Options:
  Header supported: x, y, z, yaw, wait_time  (or qx, qy, qz, qw)
  No header supported:
    - 2 cols: x, y
    - 3 cols: x, y, yaw (degrees)
    - 4 cols: x, y, yaw, wait_time (seconds)
    - 5 cols: x, y, z, yaw, wait_time
    - 7 cols: x, y, z, qx, qy, qz, qw
    - 8 cols: x, y, z, qx, qy, qz, qw, wait_time

Usage:
  ./publish_wps.py                                  # Default CSV (point.list.csv), auto mode
  ./publish_wps.py --csv /path/to/my_points.csv     # Custom CSV file
  ./publish_wps.py --mode follow_waypoints          # Batch follow_waypoints action
  ./publish_wps.py --mode sequential                # Per-point NavigateToPose + wait_time
  ./publish_wps.py --vis-only                       # Only publish to RViz for visualization
"""

from __future__ import annotations

import os

# Ensure CycloneDDS is configured to match go2-nav environment before rclpy import
if 'RMW_IMPLEMENTATION' not in os.environ:
    os.environ['RMW_IMPLEMENTATION'] = 'rmw_cyclonedds_cpp'

_script_dir = os.path.dirname(os.path.realpath(__file__))
_cyclonedds_xml = os.path.join(os.path.dirname(_script_dir), 'cyclonedds', 'cyclonedds.local.xml')
if 'CYCLONEDDS_URI' not in os.environ and os.path.exists(_cyclonedds_xml):
    os.environ['CYCLONEDDS_URI'] = f'file://{_cyclonedds_xml}'

import argparse
import csv
import math
import sys
import time
from typing import NamedTuple, List, Tuple

import rclpy
from rclpy.node import Node
from rclpy.duration import Duration
from rclpy.qos import QoSProfile, DurabilityPolicy

from geometry_msgs.msg import PoseStamped, PoseArray, Pose, Quaternion
from visualization_msgs.msg import Marker, MarkerArray
from std_msgs.msg import ColorRGBA

from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult


class Waypoint(NamedTuple):
    x: float
    y: float
    z: float
    qx: float
    qy: float
    qz: float
    qw: float
    wait_time: float


def euler_to_quaternion(yaw_deg: float) -> Tuple[float, float, float, float]:
    """Convert yaw angle in degrees to quaternion (qx, qy, qz, qw)."""
    rad = math.radians(yaw_deg)
    qz = math.sin(rad / 2.0)
    qw = math.cos(rad / 2.0)
    return 0.0, 0.0, qz, qw


def parse_csv(csv_path: str, default_wait_time: float = 0.0) -> List[Waypoint]:
    """Parse waypoints CSV file into a list of Waypoint objects."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    waypoints: List[Waypoint] = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]

    header = None
    reader = csv.reader(lines)
    for row_idx, clean_row in enumerate(reader):
        clean_row = [c.strip() for c in clean_row if c.strip()]
        if not clean_row:
            continue

        # Check if header row (contains field names instead of float numbers)
        if header is None and any(col.lower() in ('x', 'y', 'z', 'yaw', 'wait_time', 'pause', 'qx', 'qw') for col in clean_row):
            header = [c.lower() for c in clean_row]
            continue

        try:
            if header:
                row_dict = {k: float(v) for k, v in zip(header, clean_row) if k and v}
                x = row_dict.get('x', 0.0)
                y = row_dict.get('y', 0.0)
                z = row_dict.get('z', 0.0)
                wait_t = row_dict.get('wait_time', row_dict.get('pause', default_wait_time))

                if 'qx' in row_dict and 'qw' in row_dict:
                    qx = row_dict.get('qx', 0.0)
                    qy = row_dict.get('qy', 0.0)
                    qz = row_dict.get('qz', 0.0)
                    qw = row_dict.get('qw', 1.0)
                elif 'yaw' in row_dict or 'yaw_deg' in row_dict:
                    yaw_val = row_dict.get('yaw', row_dict.get('yaw_deg', 0.0))
                    qx, qy, qz, qw = euler_to_quaternion(yaw_val)
                else:
                    qx, qy, qz, qw = 0.0, 0.0, 0.0, 1.0
            else:
                # Positional parsing without header
                vals = [float(v) for v in clean_row]
                num = len(vals)
                x, y = vals[0], vals[1]
                z = 0.0
                wait_t = default_wait_time
                qx, qy, qz, qw = 0.0, 0.0, 0.0, 1.0

                if num == 3:  # x, y, yaw
                    qx, qy, qz, qw = euler_to_quaternion(vals[2])
                elif num == 4:  # x, y, yaw, wait_time
                    qx, qy, qz, qw = euler_to_quaternion(vals[2])
                    wait_t = vals[3]
                elif num == 5:  # x, y, z, yaw, wait_time
                    z = vals[2]
                    qx, qy, qz, qw = euler_to_quaternion(vals[3])
                    wait_t = vals[4]
                elif num == 7:  # x, y, z, qx, qy, qz, qw
                    z = vals[2]
                    qx, qy, qz, qw = vals[3], vals[4], vals[5], vals[6]
                elif num >= 8:  # x, y, z, qx, qy, qz, qw, wait_time
                    z = vals[2]
                    qx, qy, qz, qw = vals[3], vals[4], vals[5], vals[6]
                    wait_t = vals[7]

            waypoints.append(Waypoint(x, y, z, qx, qy, qz, qw, wait_t))
        except ValueError as e:
            print(f"[Warning] Line {row_idx + 1} skipped due to parse error: {e}")

    return waypoints


def publish_visualization(node: Node, waypoints: List[Waypoint], frame_id: str):
    """Publish PoseArray and MarkerArray for visualization in RViz2."""
    qos = QoSProfile(depth=1)
    qos.durability = DurabilityPolicy.TRANSIENT_LOCAL

    pose_pub = node.create_publisher(PoseArray, '/waypoints', qos)
    marker_pub = node.create_publisher(MarkerArray, '/waypoint_markers', qos)

    now = node.get_clock().now().to_msg()

    # Create PoseArray
    pa = PoseArray()
    pa.header.frame_id = frame_id
    pa.header.stamp = now

    # Create MarkerArray
    ma = MarkerArray()

    for idx, wp in enumerate(waypoints):
        pose = Pose()
        pose.position.x = wp.x
        pose.position.y = wp.y
        pose.position.z = wp.z
        pose.orientation.x = wp.qx
        pose.orientation.y = wp.qy
        pose.orientation.z = wp.qz
        pose.orientation.w = wp.qw
        pa.poses.append(pose)

        # Arrow marker
        arrow = Marker()
        arrow.header.frame_id = frame_id
        arrow.header.stamp = now
        arrow.ns = "waypoint_arrows"
        arrow.id = idx
        arrow.type = Marker.ARROW
        arrow.action = Marker.ADD
        arrow.pose = pose
        arrow.scale.x = 0.5  # arrow length
        arrow.scale.y = 0.08 # arrow width
        arrow.scale.z = 0.08 # arrow height
        arrow.color = ColorRGBA(r=0.0, g=0.8, b=1.0, a=0.9) # Cyan
        ma.markers.append(arrow)

        # Text label marker (index + wait time)
        text = Marker()
        text.header.frame_id = frame_id
        text.header.stamp = now
        text.ns = "waypoint_labels"
        text.id = idx + 1000
        text.type = Marker.TEXT_VIEW_FACING
        text.action = Marker.ADD
        text.pose.position.x = wp.x
        text.pose.position.y = wp.y
        text.pose.position.z = wp.z + 0.4
        text.scale.z = 0.25  # Text height
        text.color = ColorRGBA(r=1.0, g=1.0, b=1.0, a=1.0)
        text.text = f"WP {idx + 1}\n({wp.wait_time:.1f}s)" if wp.wait_time > 0 else f"WP {idx + 1}"
        ma.markers.append(text)

    # Give publishers time to connect and retain transient_local msg
    pose_pub.publish(pa)
    marker_pub.publish(ma)
    node.get_logger().info(f"Published {len(waypoints)} waypoints to /waypoints and /waypoint_markers")


def _waitUntilNav2Active(self, navigator='bt_navigator', localizer=None):
    """Block until Nav2 is active without checking AMCL (configured for SLAM/RTAB-Map)."""
    self.info('Waiting for Nav2 to activate (SLAM mode, ignoring AMCL)...')
    if not self.nav_to_pose_client.wait_for_server(timeout_sec=10.0):
        self.error('Nav2 action server navigate_to_pose is not available!')
        return
    if not self.follow_waypoints_client.wait_for_server(timeout_sec=10.0):
        self.error('Nav2 action server follow_waypoints is not available!')
        return
    self.info('Nav2 is ready for use!')

# Update BasicNavigator.waitUntilNav2Active so it never uses AMCL
BasicNavigator.waitUntilNav2Active = _waitUntilNav2Active


def main():
    parser = argparse.ArgumentParser(description="Publish and execute Nav2 waitpoints from CSV.")
    parser.add_argument('--csv', type=str, default='', help='Path to CSV file (default: point.list.csv in waitpoints dir)')
    parser.add_argument('--frame-id', type=str, default='map', help='Reference frame ID (default: map)')
    parser.add_argument('--mode', type=str, choices=['auto', 'follow_waypoints', 'sequential'], default='auto',
                        help='Execution mode: follow_waypoints (batch action), sequential (per-point wait), auto')
    parser.add_argument('--default-wait-time', type=float, default=0.0, help='Default wait time in seconds if unassigned')
    parser.add_argument('--vis-only', action='store_true', help='Only publish waypoints for visualization without driving')
    parser.add_argument('--loop', type=int, default=1, help='Number of loops to execute waypoints (default: 1)')

    args = parser.parse_args()

    # Determine CSV file path
    script_dir = os.path.dirname(os.path.realpath(__file__))
    csv_path = args.csv if args.csv else os.path.join(script_dir, 'point.list.csv')

    print(f"Reading waypoints from: {csv_path}")
    waypoints = parse_csv(csv_path, default_wait_time=args.default_wait_time)

    if not waypoints:
        print("[Error] No valid waypoints found in CSV.")
        sys.exit(1)

    print(f"Loaded {len(waypoints)} waypoints:")
    for idx, wp in enumerate(waypoints):
        yaw_deg = math.degrees(2.0 * math.atan2(wp.qz, wp.qw))
        print(f"  WP {idx + 1}: x={wp.x:.2f}, y={wp.y:.2f}, z={wp.z:.2f}, yaw={yaw_deg:.1f}°, wait_time={wp.wait_time:.1f}s")

    rclpy.init()
    navigator = BasicNavigator()

    # Publish visualization markers first
    publish_visualization(navigator, waypoints, args.frame_id)

    if args.vis_only:
        print("Visualization mode active. Waypoints published to RViz. Exiting without navigation.")
        rclpy.shutdown()
        return

    # Determine mode
    has_varying_wait_times = any(wp.wait_time > 0 for wp in waypoints)
    mode = args.mode
    if mode == 'auto':
        mode = 'sequential' if has_varying_wait_times else 'follow_waypoints'

    # Wait for Nav2 without AMCL
    navigator.waitUntilNav2Active()
    print(f"Starting navigation in '{mode}' mode...")

    # Convert Waypoints to PoseStamped list
    pose_list: List[PoseStamped] = []
    for wp in waypoints:
        p = PoseStamped()
        p.header.frame_id = args.frame_id
        p.header.stamp = navigator.get_clock().now().to_msg()
        p.pose.position.x = wp.x
        p.pose.position.y = wp.y
        p.pose.position.z = wp.z
        p.pose.orientation.x = wp.qx
        p.pose.orientation.y = wp.qy
        p.pose.orientation.z = wp.qz
        p.pose.orientation.w = wp.qw
        pose_list.append(p)

    for loop_cnt in range(args.loop):
        print(f"\n--- Starting Waypoint Loop {loop_cnt + 1} / {args.loop} ---")

        if mode == 'follow_waypoints':
            # Batch followWaypoints
            navigator.followWaypoints(pose_list)
            while not navigator.isTaskComplete():
                feedback = navigator.getFeedback()
                if feedback:
                    print(f"Executing followWaypoints... Current index: {feedback.current_waypoint}", end='\r')
                time.sleep(0.5)

            result = navigator.getResult()
            if result == TaskResult.SUCCEEDED:
                print(f"\nLoop {loop_cnt + 1} completed successfully!")
            else:
                print(f"\nLoop {loop_cnt + 1} failed or canceled (Result code: {result})")
                break
        else: # sequential
            for idx, (pose, wp) in enumerate(zip(pose_list, waypoints)):
                print(f"Navigating to Waypoint {idx + 1} / {len(waypoints)} (x={wp.x:.2f}, y={wp.y:.2f})...")
                navigator.goToPose(pose)

                while not navigator.isTaskComplete():
                    feedback = navigator.getFeedback()
                    time.sleep(0.5)

                result = navigator.getResult()
                if result == TaskResult.SUCCEEDED:
                    print(f"Reached Waypoint {idx + 1}!")
                    if wp.wait_time > 0:
                        print(f"Waiting at Waypoint {idx + 1} for {wp.wait_time:.1f} seconds...")
                        time.sleep(wp.wait_time)
                else:
                    print(f"Failed to reach Waypoint {idx + 1}!")
                    break

    print("Waypoint navigation execution finished.")
    rclpy.shutdown()


if __name__ == '__main__':
    main()
