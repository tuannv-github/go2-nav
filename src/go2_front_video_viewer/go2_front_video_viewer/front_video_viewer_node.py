#!/usr/bin/env python3
"""
Front Video Viewer Node

Subscribes to /frontvideostream topic and displays the video using GStreamer.
"""

import sys
import threading
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import Gst, GstApp, GLib

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage


class FrontVideoViewer(Node):
    """Node that subscribes to front video stream and displays it using GStreamer."""
    
    def __init__(self):
        super().__init__('front_video_viewer')
        
        # Declare parameters
        self.declare_parameter('topic', '/frontvideostream/compressed')
        self.declare_parameter('display_width', 1280)
        self.declare_parameter('display_height', 720)
        
        topic = self.get_parameter('topic').get_parameter_value().string_value
        display_width = self.get_parameter('display_width').get_parameter_value().integer_value
        display_height = self.get_parameter('display_height').get_parameter_value().integer_value
        
        self.get_logger().info(f'Subscribing to topic: {topic}')
        self.get_logger().info(f'Expecting sensor_msgs/CompressedImage with H.264 data')
        self.get_logger().info(f'Display size: {display_width}x{display_height}')
        
        # Initialize GStreamer
        Gst.init(None)
        
        # Create GStreamer pipeline
        # Pipeline: appsrc -> h264parse -> avdec_h264 -> videoconvert -> autovideosink
        # Using byte-stream format for H.264 with start codes (0x00 0x00 0x00 0x01)
        pipeline_str = (
            'appsrc name=source is-live=true format=time do-timestamp=true '
            'caps=video/x-h264,stream-format=byte-stream,alignment=au ! '
            'h264parse ! '
            'avdec_h264 ! '
            'videoconvert ! '
            f'video/x-raw,width={display_width},height={display_height} ! '
            'autovideosink sync=false'
        )
        
        self.get_logger().info(f'GStreamer pipeline: {pipeline_str}')
        
        try:
            self.pipeline = Gst.parse_launch(pipeline_str)
            self.appsrc = self.pipeline.get_by_name('source')
            
            if not self.appsrc:
                self.get_logger().error('Failed to get appsrc element')
                sys.exit(1)
            
            # Set appsrc properties
            self.appsrc.set_property('block', True)
            self.appsrc.set_property('max-bytes', 0)  # No limit
            
            # Start the pipeline
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                self.get_logger().error('Failed to start GStreamer pipeline')
                sys.exit(1)
            
            self.get_logger().info('GStreamer pipeline started successfully')
            
        except Exception as e:
            self.get_logger().error(f'Failed to create GStreamer pipeline: {e}')
            sys.exit(1)
        
        # Create subscription for CompressedImage
        self.subscription = self.create_subscription(
            CompressedImage,
            topic,
            self.video_callback,
            10  # Queue depth
        )
        
        self.get_logger().info(f'Created subscription with queue depth: 10')
        
        self.get_logger().info('Front Video Viewer node started')
        self.frame_count = 0
        self.callback_invoked = False
        
        # Start GStreamer main loop in a separate thread
        self.loop = GLib.MainLoop()
        self.loop_thread = threading.Thread(target=self._run_gst_loop, daemon=True)
        self.loop_thread.start()
    
    def _run_gst_loop(self):
        """Run GStreamer main loop in a separate thread."""
        try:
            self.loop.run()
        except Exception as e:
            self.get_logger().error(f'GStreamer loop error: {e}')
    
    def video_callback(self, msg):
        """Callback when compressed image is received."""
        # Log that callback was invoked (to verify messages are getting through)
        if not self.callback_invoked:
            self.get_logger().info('Video callback invoked - receiving CompressedImage messages!')
            self.get_logger().info(f'Image format: {msg.format}')
            self.callback_invoked = True
        
        try:
            # Extract video data from CompressedImage
            if len(msg.data) == 0:
                if self.frame_count % 100 == 0:  # Log occasionally to avoid spam
                    self.get_logger().debug('Received empty CompressedImage data')
                return
            
            # Convert list to bytes
            video_data = bytes(msg.data)
            
            # Create GStreamer buffer from video data
            buffer = Gst.Buffer.new_allocate(None, len(video_data), None)
            buffer.fill(0, video_data)
            
            # Set timestamp - use current time for live streaming
            # time_frame appears to be in microseconds, but we'll use current time for sync
            current_time = self.get_clock().now()
            timestamp = current_time.nanoseconds
            buffer.pts = timestamp
            buffer.dts = timestamp
            # Estimate duration based on typical frame rate (30 fps = ~33ms)
            buffer.duration = Gst.NSECOND // 30  # ~33ms per frame
            
            # Push buffer to AppSrc using emit method
            ret = self.appsrc.emit('push-buffer', buffer)
            
            if ret == Gst.FlowReturn.FLUSHING:
                self.get_logger().warn('Pipeline is flushing, stopping push')
            elif ret != Gst.FlowReturn.OK:
                self.get_logger().warn(f'Failed to push buffer: {ret}')
            
            self.frame_count += 1
            if self.frame_count % 30 == 0:
                self.get_logger().info(
                    f'Processed {self.frame_count} frames, '
                    f'last frame size: {len(video_data)} bytes'
                )
                
        except Exception as e:
            import traceback
            self.get_logger().error(f'Error processing video frame: {e}')
            self.get_logger().error(f'Traceback: {traceback.format_exc()}')
    
    def destroy_node(self):
        """Cleanup on node destruction."""
        try:
            if hasattr(self, 'pipeline'):
                self.pipeline.set_state(Gst.State.NULL)
            if hasattr(self, 'loop'):
                self.loop.quit()
        except Exception as e:
            self.get_logger().error(f'Error during cleanup: {e}')
        super().destroy_node()


def main(args=None):
    """Main function."""
    rclpy.init(args=args)
    
    node = FrontVideoViewer()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
