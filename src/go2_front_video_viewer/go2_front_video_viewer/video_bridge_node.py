#!/usr/bin/env python3
"""
Video Bridge Node

Converts Go2FrontVideoData messages to sensor_msgs/CompressedImage.
This helps avoid CycloneDDS deserialization issues with large byte arrays.
"""

import rclpy
from rclpy.node import Node
from unitree_go.msg import Go2FrontVideoData
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import Header


class VideoBridge(Node):
    """Bridge node that converts Go2FrontVideoData to CompressedImage."""
    
    def __init__(self):
        super().__init__('video_bridge')
        
        # Declare parameters
        self.declare_parameter('input_topic', '/frontvideostream')
        self.declare_parameter('output_topic', '/frontvideostream/compressed')
        self.declare_parameter('use_720p', True)
        
        input_topic = self.get_parameter('input_topic').get_parameter_value().string_value
        output_topic = self.get_parameter('output_topic').get_parameter_value().string_value
        self.use_720p = self.get_parameter('use_720p').get_parameter_value().bool_value
        
        # Create publisher
        self.publisher_ = self.create_publisher(
            CompressedImage,
            output_topic,
            10
        )
        
        # Create subscription - only access video720p to avoid deserialization errors
        self.subscription = self.create_subscription(
            Go2FrontVideoData,
            input_topic,
            self.video_callback,
            10
        )
        
        self.get_logger().info(f'Video Bridge started: {input_topic} -> {output_topic}')
        self.get_logger().info(f'Using video720p only: {self.use_720p}')
        self.frame_count = 0
    
    def video_callback(self, msg):
        """Callback when video data is received."""
        try:
            # Only use video720p to avoid CycloneDDS deserialization errors
            # Don't access video360p or video180p - they cause errors
            if len(msg.video720p) == 0:
                return
            
            # Create CompressedImage message
            compressed_msg = CompressedImage()
            
            # Set header
            compressed_msg.header = Header()
            compressed_msg.header.stamp = self.get_clock().now().to_msg()
            compressed_msg.header.frame_id = 'front_camera'
            
            # Set format - H.264 video data
            compressed_msg.format = 'h264'
            
            # Set data - copy video720p data
            compressed_msg.data = list(msg.video720p)
            
            # Publish
            self.publisher_.publish(compressed_msg)
            
            self.frame_count += 1
            if self.frame_count % 30 == 0:
                self.get_logger().info(
                    f'Bridged {self.frame_count} frames, '
                    f'last size: {len(msg.video720p)} bytes'
                )
                
        except Exception as e:
            import traceback
            self.get_logger().error(f'Error in video bridge: {e}')
            self.get_logger().error(f'Traceback: {traceback.format_exc()}')


def main(args=None):
    """Main function."""
    rclpy.init(args=args)
    
    node = VideoBridge()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
