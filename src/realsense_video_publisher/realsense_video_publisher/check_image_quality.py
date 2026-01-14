#!/usr/bin/env python3
"""
Image Quality Checker for Realsense Camera

Subscribes to camera image topic and reports image quality metrics:
- Resolution
- Encoding format
- Frame rate
- Data size
- Timestamp information
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
import numpy as np
from cv_bridge import CvBridge
import cv2
import time
from collections import deque


class ImageQualityChecker(Node):
    """Node that checks image quality from camera topic."""
    
    def __init__(self):
        super().__init__('image_quality_checker')
        
        # Declare parameters
        self.declare_parameter('input_topic', '/input/camera/camera/color/image_raw')
        self.declare_parameter('check_duration', 10.0)  # seconds
        self.declare_parameter('save_sample', False)
        self.declare_parameter('sample_path', '/tmp/camera_sample.jpg')
        
        input_topic = self.get_parameter('input_topic').get_parameter_value().string_value
        self.check_duration = self.get_parameter('check_duration').get_parameter_value().double_value
        self.save_sample = self.get_parameter('save_sample').get_parameter_value().bool_value
        self.sample_path = self.get_parameter('sample_path').get_parameter_value().string_value
        
        # Initialize CV bridge
        self.bridge = CvBridge()
        
        # Statistics
        self.frame_count = 0
        self.start_time = None
        self.last_timestamp = None
        self.timestamps = deque(maxlen=100)
        self.resolutions = set()
        self.encodings = set()
        self.data_sizes = deque(maxlen=100)
        self.first_image = None
        
        # Create subscription
        self.subscription = self.create_subscription(
            Image,
            input_topic,
            self.image_callback,
            10
        )
        
        # Timer to print summary
        self.timer = self.create_timer(1.0, self.print_status)
        
        self.get_logger().info(f'Image Quality Checker started')
        self.get_logger().info(f'Subscribing to: {input_topic}')
        self.get_logger().info(f'Will check for {self.check_duration} seconds')
        self.get_logger().info('Press Ctrl+C to stop early')
    
    def image_callback(self, msg):
        """Callback when image is received."""
        current_time = time.time()
        
        if self.start_time is None:
            self.start_time = current_time
            self.get_logger().info('First image received!')
        
        # Update statistics
        self.frame_count += 1
        
        # Record timestamp
        stamp = msg.header.stamp
        timestamp_sec = stamp.sec + stamp.nanosec * 1e-9
        self.timestamps.append(timestamp_sec)
        self.last_timestamp = timestamp_sec
        
        # Record resolution
        resolution = (msg.width, msg.height)
        self.resolutions.add(resolution)
        
        # Record encoding
        self.encodings.add(msg.encoding)
        
        # Record data size
        data_size = len(msg.data)
        self.data_sizes.append(data_size)
        
        # Save first image if requested
        if self.first_image is None and self.save_sample:
            try:
                cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
                self.first_image = cv_image
                cv2.imwrite(self.sample_path, cv_image)
                self.get_logger().info(f'Saved sample image to: {self.sample_path}')
            except Exception as e:
                self.get_logger().warn(f'Failed to save sample image: {e}')
        
        # Print first few frames
        if self.frame_count <= 5:
            self.get_logger().info(
                f'Frame #{self.frame_count}: '
                f'{msg.width}x{msg.height}, '
                f'encoding={msg.encoding}, '
                f'size={data_size} bytes, '
                f'step={msg.step}, '
                f'is_bigendian={msg.is_bigendian}'
            )
        
        # Check if duration exceeded
        elapsed = current_time - self.start_time
        if elapsed >= self.check_duration:
            self.print_final_summary()
            rclpy.shutdown()
    
    def calculate_fps(self):
        """Calculate frames per second from timestamps."""
        if len(self.timestamps) < 2:
            return 0.0
        
        time_diffs = []
        for i in range(1, len(self.timestamps)):
            diff = self.timestamps[i] - self.timestamps[i-1]
            if diff > 0:
                time_diffs.append(diff)
        
        if not time_diffs:
            return 0.0
        
        avg_interval = np.mean(time_diffs)
        return 1.0 / avg_interval if avg_interval > 0 else 0.0
    
    def print_status(self):
        """Print current status."""
        if self.frame_count == 0:
            self.get_logger().warn('No images received yet...')
            return
        
        elapsed = time.time() - self.start_time if self.start_time else 0
        current_fps = self.calculate_fps()
        avg_fps = self.frame_count / elapsed if elapsed > 0 else 0
        
        self.get_logger().info(
            f'Status: {self.frame_count} frames, '
            f'{elapsed:.1f}s elapsed, '
            f'FPS: {current_fps:.2f} (avg: {avg_fps:.2f})'
        )
    
    def print_final_summary(self):
        """Print final summary of image quality."""
        self.get_logger().info('=' * 60)
        self.get_logger().info('IMAGE QUALITY SUMMARY')
        self.get_logger().info('=' * 60)
        
        # Basic info
        elapsed = time.time() - self.start_time if self.start_time else 0
        avg_fps = self.frame_count / elapsed if elapsed > 0 else 0
        current_fps = self.calculate_fps()
        
        self.get_logger().info(f'Total frames received: {self.frame_count}')
        self.get_logger().info(f'Duration: {elapsed:.2f} seconds')
        self.get_logger().info(f'Average FPS: {avg_fps:.2f}')
        self.get_logger().info(f'Current FPS: {current_fps:.2f}')
        
        # Resolution
        self.get_logger().info('')
        self.get_logger().info('Resolution(s):')
        for res in sorted(self.resolutions):
            self.get_logger().info(f'  {res[0]}x{res[1]}')
        
        # Encoding
        self.get_logger().info('')
        self.get_logger().info('Encoding(s):')
        for enc in sorted(self.encodings):
            self.get_logger().info(f'  {enc}')
        
        # Data size statistics
        if self.data_sizes:
            avg_size = np.mean(self.data_sizes)
            min_size = np.min(self.data_sizes)
            max_size = np.max(self.data_sizes)
            self.get_logger().info('')
            self.get_logger().info('Data size statistics:')
            self.get_logger().info(f'  Average: {avg_size:.0f} bytes ({avg_size/1024:.2f} KB)')
            self.get_logger().info(f'  Min: {min_size} bytes ({min_size/1024:.2f} KB)')
            self.get_logger().info(f'  Max: {max_size} bytes ({max_size/1024:.2f} KB)')
        
        # Timestamp analysis
        if len(self.timestamps) >= 2:
            time_diffs = []
            for i in range(1, len(self.timestamps)):
                diff = self.timestamps[i] - self.timestamps[i-1]
                if diff > 0:
                    time_diffs.append(diff)
            
            if time_diffs:
                avg_interval = np.mean(time_diffs)
                min_interval = np.min(time_diffs)
                max_interval = np.max(time_diffs)
                std_interval = np.std(time_diffs)
                
                self.get_logger().info('')
                self.get_logger().info('Frame interval statistics:')
                self.get_logger().info(f'  Average: {avg_interval*1000:.2f} ms')
                self.get_logger().info(f'  Min: {min_interval*1000:.2f} ms')
                self.get_logger().info(f'  Max: {max_interval*1000:.2f} ms')
                self.get_logger().info(f'  Std Dev: {std_interval*1000:.2f} ms')
        
        # Image quality assessment
        self.get_logger().info('')
        self.get_logger().info('Quality Assessment:')
        
        if self.resolutions:
            res = next(iter(self.resolutions))
            if res[0] >= 1920 and res[1] >= 1080:
                self.get_logger().info('  ✓ Resolution: 1080p or higher')
            elif res[0] >= 1280 and res[1] >= 720:
                self.get_logger().info('  ✓ Resolution: 720p or higher')
            else:
                self.get_logger().info(f'  ⚠ Resolution: {res[0]}x{res[1]} (below 720p)')
        
        if current_fps >= 29:
            self.get_logger().info(f'  ✓ Frame rate: {current_fps:.1f} FPS (good)')
        elif current_fps >= 15:
            self.get_logger().info(f'  ⚠ Frame rate: {current_fps:.1f} FPS (moderate)')
        else:
            self.get_logger().info(f'  ✗ Frame rate: {current_fps:.1f} FPS (low)')
        
        if self.data_sizes:
            avg_size = np.mean(self.data_sizes)
            expected_size_1080p = 1920 * 1080 * 3  # RGB
            if avg_size >= expected_size_1080p * 0.9:
                self.get_logger().info('  ✓ Data size: Consistent with 1080p RGB')
            elif avg_size >= expected_size_1080p * 0.5:
                self.get_logger().info('  ⚠ Data size: May be compressed or lower resolution')
            else:
                self.get_logger().info('  ⚠ Data size: Smaller than expected')
        
        self.get_logger().info('=' * 60)


def main(args=None):
    """Main function."""
    rclpy.init(args=args)
    
    node = ImageQualityChecker()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.print_final_summary()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
