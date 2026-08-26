#!/usr/bin/env python3
"""
Record waypoints published to /goal_pose (e.g. from RViz '2D Nav Goal' button)
and save them to point.list.csv.

Usage:
  ./record_wps.py                             # Records to point.list.csv with default 2.0s wait time
  ./record_wps.py --csv my_points.csv        # Records to a custom CSV file
  ./record_wps.py --wait-time 3.0            # Set default wait time per recorded pose
  ./record_wps.py --clear                    # Clear existing CSV before recording
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
import math
import sys

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped


class WaypointRecorder(Node):
    def __init__(self, csv_path: str, default_wait_time: float, clear_first: bool):
        super().__init__('waypoint_recorder')
        self.csv_path = csv_path
        self.default_wait_time = default_wait_time
        self.count = 0

        # Initialize CSV file if missing or if --clear is passed
        if clear_first or not os.path.exists(self.csv_path):
            with open(self.csv_path, 'w', encoding='utf-8') as f:
                f.write("# Format: x, y, z, yaw, wait_time\n")
                f.write("x, y, z, yaw, wait_time\n")
            self.get_logger().info(f"Initialized new CSV file: {self.csv_path}")
        else:
            # Count existing waypoints
            with open(self.csv_path, 'r', encoding='utf-8') as f:
                self.count = sum(1 for line in f if line.strip() and not line.strip().startswith('#') and not line.strip().startswith('x'))
            self.get_logger().info(f"Appending to existing CSV: {self.csv_path} ({self.count} waypoints existing)")

        self.sub = self.create_subscription(PoseStamped, '/goal_pose', self.pose_callback, 10)
        self.get_logger().info("Listening on /goal_pose... Click '2D Nav Goal' in RViz to record waypoints. Press Ctrl+C to stop.")

    def pose_callback(self, msg: PoseStamped):
        x = msg.pose.position.x
        y = msg.pose.position.y
        z = msg.pose.position.z

        qx = msg.pose.orientation.x
        qy = msg.pose.orientation.y
        qz = msg.pose.orientation.z
        qw = msg.pose.orientation.w

        # Compute yaw angle in degrees
        yaw_rad = 2.0 * math.atan2(qz, qw)
        yaw_deg = math.degrees(yaw_rad)

        self.count += 1
        with open(self.csv_path, 'a', encoding='utf-8') as f:
            f.write(f"{x:.4f}, {y:.4f}, {z:.4f}, {yaw_deg:.2f}, {self.default_wait_time:.1f}\n")

        self.get_logger().info(
            f"-> [Recorded Waypoint {self.count}] x={x:.4f}, y={y:.4f}, z={z:.4f}, yaw={yaw_deg:.1f}°, wait_time={self.default_wait_time:.1f}s"
        )


def main():
    parser = argparse.ArgumentParser(description="Record RViz goal poses to CSV waypoint file.")
    parser.add_argument('--csv', type=str, default='', help='Path to output CSV file')
    parser.add_argument('--wait-time', type=float, default=2.0, help='Default wait time in seconds for recorded waypoints')
    parser.add_argument('--clear', action='store_true', help='Clear existing CSV file before recording')

    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.realpath(__file__))
    csv_path = args.csv if args.csv else os.path.join(script_dir, 'point.list.csv')

    rclpy.init()
    node = WaypointRecorder(csv_path, default_wait_time=args.wait_time, clear_first=args.clear)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Recorder stopped.")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
