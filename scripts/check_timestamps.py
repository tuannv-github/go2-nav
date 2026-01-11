#!/usr/bin/env python3
"""
Diagnostic script to check IMU and camera timestamps.
This helps diagnose synchronization issues between IMU and camera data.
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu, Image, CameraInfo
import time

class TimestampChecker(Node):
    def __init__(self):
        super().__init__('timestamp_checker')
        
        # Subscribers
        self.imu_sub = self.create_subscription(
            Imu,
            '/utlidar/imu',
            self.imu_callback,
            10
        )
        
        self.camera_color_sub = self.create_subscription(
            Image,
            '/input/camera/camera/color/image_raw',
            self.camera_color_callback,
            10
        )
        
        self.camera_info_sub = self.create_subscription(
            CameraInfo,
            '/input/camera/camera/color/camera_info',
            self.camera_info_callback,
            10
        )
        
        # State
        self.last_imu_time = None
        self.last_camera_time = None
        self.last_camera_info_time = None
        self.imu_count = 0
        self.camera_count = 0
        
        # Timer to print status
        self.timer = self.create_timer(2.0, self.print_status)
        
        self.get_logger().info('Timestamp checker started. Monitoring:')
        self.get_logger().info('  IMU: /utlidar/imu')
        self.get_logger().info('  Camera: /input/camera/camera/color/image_raw')
        self.get_logger().info('  Camera Info: /input/camera/camera/color/camera_info')
        
    def imu_callback(self, msg):
        self.imu_count += 1
        stamp = msg.header.stamp
        self.last_imu_time = stamp.sec + stamp.nanosec * 1e-9
        current_time = self.get_clock().now().nanoseconds / 1e9
        
        if self.imu_count <= 5 or self.imu_count % 50 == 0:
            time_diff = current_time - self.last_imu_time
            self.get_logger().info(
                f'IMU #{self.imu_count}: stamp={self.last_imu_time:.6f}, '
                f'now={current_time:.6f}, diff={time_diff:.6f}s, '
                f'frame_id={msg.header.frame_id}'
            )
    
    def camera_color_callback(self, msg):
        self.camera_count += 1
        stamp = msg.header.stamp
        self.last_camera_time = stamp.sec + stamp.nanosec * 1e-9
        current_time = self.get_clock().now().nanoseconds / 1e9
        
        if self.camera_count <= 5 or self.camera_count % 30 == 0:
            time_diff = current_time - self.last_camera_time
            self.get_logger().info(
                f'Camera #{self.camera_count}: stamp={self.last_camera_time:.6f}, '
                f'now={current_time:.6f}, diff={time_diff:.6f}s, '
                f'frame_id={msg.header.frame_id}, size={msg.width}x{msg.height}'
            )
    
    def camera_info_callback(self, msg):
        stamp = msg.header.stamp
        self.last_camera_info_time = stamp.sec + stamp.nanosec * 1e-9
    
    def print_status(self):
        current_time = self.get_clock().now().nanoseconds / 1e9
        
        self.get_logger().info('=' * 60)
        self.get_logger().info(f'Current system time: {current_time:.6f}')
        
        if self.last_imu_time is not None:
            imu_age = current_time - self.last_imu_time
            self.get_logger().info(
                f'IMU: last_stamp={self.last_imu_time:.6f}, '
                f'age={imu_age:.6f}s ({imu_age/60:.2f} min), count={self.imu_count}'
            )
        else:
            self.get_logger().warn('IMU: No messages received yet!')
        
        if self.last_camera_time is not None:
            camera_age = current_time - self.last_camera_time
            self.get_logger().info(
                f'Camera: last_stamp={self.last_camera_time:.6f}, '
                f'age={camera_age:.6f}s, count={self.camera_count}'
            )
        else:
            self.get_logger().warn('Camera: No messages received yet!')
        
        if self.last_imu_time is not None and self.last_camera_time is not None:
            time_diff = self.last_imu_time - self.last_camera_time
            self.get_logger().info(
                f'Time difference (IMU - Camera): {time_diff:.6f}s ({time_diff/60:.2f} min)'
            )
            if abs(time_diff) > 1.0:
                self.get_logger().error(
                    f'⚠️  WARNING: Large timestamp difference detected! '
                    f'This will cause synchronization issues.'
                )
        self.get_logger().info('=' * 60)

def main(args=None):
    rclpy.init(args=args)
    node = TimestampChecker()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
