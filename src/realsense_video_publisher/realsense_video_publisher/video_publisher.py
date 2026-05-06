#!/usr/bin/env python3
"""
Realsense Video Publisher Node

Subscribes to realsense camera topics and publishes video stream using GStreamer.
"""

import sys
import threading
import numpy as np
import cv2
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import Gst, GstApp, GLib

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge


class RealsenseVideoPublisher(Node):
    """Node that subscribes to realsense camera and publishes video using GStreamer."""
    
    def __init__(self):
        super().__init__('realsense_video_publisher')
        
        # Declare parameters
        self.declare_parameter('input_topic', '/input/camera/camera/color/image_raw')
        self.declare_parameter('stream_host', '129.126.114.218')
        self.declare_parameter('stream_port', 1935)  # RTMP default port
        self.declare_parameter('stream_path', 'stream/go2/front')  # RTMP stream path/key
        self.declare_parameter('bitrate', 6000000)  # 6Mbps in bps for NVIDIA encoder
        self.declare_parameter('fps', 30)
        self.declare_parameter('width', 1920)
        self.declare_parameter('height', 1080)
        self.declare_parameter('stream_type', 'rtmp')  # 'rtmp', 'udp', 'rtsp', 'rtp'
        self.declare_parameter('use_nvidia_hw', True)  # Use NVIDIA hardware acceleration
        self.declare_parameter('auto_detect_resolution', True)
        
        input_topic = self.get_parameter('input_topic').get_parameter_value().string_value
        stream_host = self.get_parameter('stream_host').get_parameter_value().string_value
        stream_port = self.get_parameter('stream_port').get_parameter_value().integer_value
        stream_path = self.get_parameter('stream_path').get_parameter_value().string_value
        bitrate = self.get_parameter('bitrate').get_parameter_value().integer_value
        fps = self.get_parameter('fps').get_parameter_value().integer_value
        width = self.get_parameter('width').get_parameter_value().integer_value
        height = self.get_parameter('height').get_parameter_value().integer_value
        stream_type = self.get_parameter('stream_type').get_parameter_value().string_value
        use_nvidia_hw = self.get_parameter('use_nvidia_hw').get_parameter_value().bool_value
        auto_detect_resolution = self.get_parameter('auto_detect_resolution').get_parameter_value().bool_value

        self.input_topic = input_topic
        self.stream_host = stream_host
        self.stream_port = stream_port
        self.stream_path = stream_path
        self.bitrate = bitrate
        self.fps = fps
        self.param_width = width
        self.param_height = height
        self.stream_type = stream_type
        self.use_nvidia_hw = use_nvidia_hw
        self.auto_detect_resolution = auto_detect_resolution
        self.pipeline_started = False
        
        self.get_logger().info(f'Subscribing to topic: {input_topic}')
        self.get_logger().info(f'Stream type: {stream_type}')
        if stream_type == 'rtmp':
            rtmp_url = f'rtmp://{stream_host}:{stream_port}/{stream_path}'
            self.get_logger().info(f'RTMP URL: {rtmp_url}')
            self.get_logger().info(f'Using NVIDIA hardware acceleration: {use_nvidia_hw}')
        else:
            self.get_logger().info(f'Stream destination: {stream_host}:{stream_port}')
        if use_nvidia_hw and stream_type == 'rtmp':
            self.get_logger().info(f'Bitrate: {bitrate} bps ({bitrate // 1000} kbps), FPS: {fps}')
        else:
            self.get_logger().info(f'Bitrate: {bitrate} kbps, FPS: {fps}')
        if auto_detect_resolution:
            self.get_logger().info('Resolution: auto-detect from input frames')
        else:
            self.get_logger().info(f'Resolution: {width}x{height}')
        
        # Initialize CV bridge for image conversion
        self.bridge = CvBridge()
        
        # Initialize GStreamer
        Gst.init(None)
        if not self.auto_detect_resolution:
            self._setup_pipeline(self.param_width, self.param_height)
        
        # Create subscription for Image
        self.subscription = self.create_subscription(
            Image,
            input_topic,
            self.image_callback,
            10  # Queue depth
        )
        
        self.get_logger().info(f'Created subscription with queue depth: 10')
        self.get_logger().info('Realsense Video Publisher node started')
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

    def _setup_pipeline(self, width: int, height: int):
        """Create and start GStreamer pipeline."""
        if self.stream_type == 'rtmp':
            rtmp_url = f'rtmp://{self.stream_host}:{self.stream_port}/{self.stream_path}'
            if self.use_nvidia_hw:
                pipeline_str = (
                    f'appsrc name=source is-live=true format=time do-timestamp=true '
                    f'caps=video/x-raw,format=BGR,width={width},height={height},framerate={self.fps}/1 ! '
                    f'videoconvert ! '
                    f'video/x-raw,format=NV12 ! '
                    f'nvvidconv ! '
                    f'video/x-raw(memory:NVMM),format=NV12 ! '
                    f'nvv4l2h264enc bitrate={self.bitrate} iframeinterval=1 ! '
                    f'h264parse ! '
                    f'flvmux streamable=true ! '
                    f'rtmpsink location={rtmp_url} sync=false'
                )
            else:
                pipeline_str = (
                    f'appsrc name=source is-live=true format=time do-timestamp=true '
                    f'caps=video/x-raw,format=BGR,width={width},height={height},framerate={self.fps}/1 ! '
                    f'videoconvert ! '
                    f'x264enc bitrate={self.bitrate // 1000} speed-preset=ultrafast tune=zerolatency key-int-max=30 ! '
                    f'flvmux streamable=true name=mux ! '
                    f'rtmpsink location={rtmp_url} sync=false'
                )
        elif self.stream_type == 'udp':
            pipeline_str = (
                f'appsrc name=source is-live=true format=time do-timestamp=true '
                f'caps=video/x-raw,format=BGR,width={width},height={height},framerate={self.fps}/1 ! '
                f'videoconvert ! '
                f'x264enc bitrate={self.bitrate} speed-preset=ultrafast tune=zerolatency ! '
                f'h264parse ! '
                f'rtph264pay config-interval=1 pt=96 ! '
                f'udpsink host={self.stream_host} port={self.stream_port}'
            )
        elif self.stream_type == 'rtsp':
            pipeline_str = (
                f'appsrc name=source is-live=true format=time do-timestamp=true '
                f'caps=video/x-raw,format=BGR,width={width},height={height},framerate={self.fps}/1 ! '
                f'videoconvert ! '
                f'x264enc bitrate={self.bitrate} speed-preset=ultrafast tune=zerolatency ! '
                f'h264parse ! '
                f'rtph264pay config-interval=1 pt=96 ! '
                f'udpsink host={self.stream_host} port={self.stream_port}'
            )
        else:  # rtp
            pipeline_str = (
                f'appsrc name=source is-live=true format=time do-timestamp=true '
                f'caps=video/x-raw,format=BGR,width={width},height={height},framerate={self.fps}/1 ! '
                f'videoconvert ! '
                f'x264enc bitrate={self.bitrate} speed-preset=ultrafast tune=zerolatency ! '
                f'h264parse ! '
                f'rtph264pay config-interval=1 pt=96 ! '
                f'udpsink host={self.stream_host} port={self.stream_port}'
            )

        self.get_logger().info(f'GStreamer pipeline: {pipeline_str}')
        try:
            self.pipeline = Gst.parse_launch(pipeline_str)
            self.appsrc = self.pipeline.get_by_name('source')
            if not self.appsrc:
                self.get_logger().error('Failed to get appsrc element')
                sys.exit(1)

            self.appsrc.set_property('block', True)
            self.appsrc.set_property('max-bytes', 0)

            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                self.get_logger().error('Failed to start GStreamer pipeline')
                sys.exit(1)

            self.pipeline_started = True
            self.get_logger().info('GStreamer pipeline started successfully')
        except Exception as e:
            self.get_logger().error(f'Failed to create GStreamer pipeline: {e}')
            import traceback
            self.get_logger().error(f'Traceback: {traceback.format_exc()}')
            sys.exit(1)
    
    def image_callback(self, msg):
        """Callback when image is received."""
        # Log that callback was invoked (to verify messages are getting through)
        if not self.callback_invoked:
            self.get_logger().info('Image callback invoked - receiving Image messages!')
            self.get_logger().info(f'Image encoding: {msg.encoding}')
            self.get_logger().info(f'Image size: {msg.width}x{msg.height}')
            self.callback_invoked = True

        if self.auto_detect_resolution and not self.pipeline_started:
            self.get_logger().info(
                f'Auto-detected input resolution: {msg.width}x{msg.height}; initializing pipeline'
            )
            self._setup_pipeline(msg.width, msg.height)
        
        try:
            # Convert ROS Image message to OpenCV format
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            
            # Get image dimensions
            height, width, channels = cv_image.shape
            
            # Resize only when auto-detect is disabled.
            if not self.auto_detect_resolution:
                if width != self.param_width or height != self.param_height:
                    cv_image = cv2.resize(cv_image, (self.param_width, self.param_height))
                    height, width = self.param_height, self.param_width
            
            # Convert to numpy array and ensure contiguous memory
            image_data = np.ascontiguousarray(cv_image)
            
            # Create GStreamer buffer from image data
            buffer = Gst.Buffer.new_allocate(None, image_data.nbytes, None)
            buffer.fill(0, image_data.tobytes())
            
            # Set timestamp
            timestamp = self.get_clock().now().nanoseconds
            buffer.pts = timestamp
            buffer.dts = timestamp
            
            # Estimate duration based on frame rate
            param_fps = self.get_parameter('fps').get_parameter_value().integer_value
            buffer.duration = Gst.SECOND // param_fps
            
            # Push buffer to AppSrc
            ret = self.appsrc.emit('push-buffer', buffer)
            
            if ret == Gst.FlowReturn.FLUSHING:
                self.get_logger().warn('Pipeline is flushing, stopping push')
            elif ret != Gst.FlowReturn.OK:
                self.get_logger().warn(f'Failed to push buffer: {ret}')
            
            self.frame_count += 1
            if self.frame_count % 30 == 0:
                self.get_logger().info(
                    f'Processed {self.frame_count} frames, '
                    f'last frame size: {width}x{height}'
                )
                
        except Exception as e:
            import traceback
            self.get_logger().error(f'Error processing image frame: {e}')
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
    
    node = RealsenseVideoPublisher()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
