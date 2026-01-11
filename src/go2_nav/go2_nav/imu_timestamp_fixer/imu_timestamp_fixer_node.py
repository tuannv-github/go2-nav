#!/usr/bin/env python3
"""
IMU Timestamp Fixer Node

Subscribes to IMU data and republishes it with current timestamps.
This fixes issues where IMU timestamps are stale or incorrect.
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu


class ImuTimestampFixer(Node):
    def __init__(self):
        super().__init__('imu_timestamp_fixer')
        
        # Parameters
        self.declare_parameter('input_topic', '/utlidar/imu')
        self.declare_parameter('output_topic', '/input/imu')
        self.declare_parameter('frame_id', 'utlidar_imu')  # Keep original frame_id
        
        input_topic = self.get_parameter('input_topic').get_parameter_value().string_value
        output_topic = self.get_parameter('output_topic').get_parameter_value().string_value
        self.frame_id = self.get_parameter('frame_id').get_parameter_value().string_value
        
        # Subscriber
        self.subscription = self.create_subscription(
            Imu,
            input_topic,
            self.imu_callback,
            10
        )
        
        # Publisher
        self.publisher = self.create_publisher(
            Imu,
            output_topic,
            10
        )
        
        self.get_logger().info(f'IMU Timestamp Fixer started: {input_topic} -> {output_topic}')
        self.orientation_warned = False
    
    def imu_callback(self, msg):
        # Create new message with current timestamp
        new_msg = Imu()
        
        # Copy all IMU data
        new_msg.orientation = msg.orientation
        new_msg.orientation_covariance = msg.orientation_covariance
        new_msg.angular_velocity = msg.angular_velocity
        new_msg.angular_velocity_covariance = msg.angular_velocity_covariance
        new_msg.linear_acceleration = msg.linear_acceleration
        new_msg.linear_acceleration_covariance = msg.linear_acceleration_covariance
        
        # Check if orientation is valid (not all zeros)
        orientation_valid = not (msg.orientation.x == 0.0 and msg.orientation.y == 0.0 and 
                                 msg.orientation.z == 0.0 and msg.orientation.w == 0.0)
        
        if not orientation_valid and not self.orientation_warned:
            self.get_logger().warn(
                f'IMU orientation is invalid (all zeros). '
                f'RTAB-Map wait_imu_to_init may wait indefinitely. '
                f'Consider disabling wait_imu_to_init if IMU does not provide orientation.'
            )
            self.orientation_warned = True
        
        # Set fresh timestamp
        new_msg.header.stamp = self.get_clock().now().to_msg()
        new_msg.header.frame_id = self.frame_id
        
        # Publish
        self.publisher.publish(new_msg)


def main(args=None):
    rclpy.init(args=args)
    node = ImuTimestampFixer()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
