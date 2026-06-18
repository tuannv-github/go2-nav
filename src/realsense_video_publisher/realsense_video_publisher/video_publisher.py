#!/usr/bin/env python3
"""
Realsense Video Publisher Node

Subscribes to realsense camera topics and publishes video stream using GStreamer.
"""

import time
import numpy as np
import cv2
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

Gst.init(None)


class RealsenseVideoPublisher(Node):
    """Node that subscribes to realsense camera and publishes video using GStreamer."""

    def __init__(self):
        super().__init__('realsense_video_publisher')

        self.declare_parameter('input_topic', '/input/camera/camera/color/image_raw')
        self.declare_parameter('stream_host', '10.1.106.210')
        self.declare_parameter('stream_port', 1935)
        self.declare_parameter('stream_path', 'stream/go2/front')
        self.declare_parameter('bitrate', 6000000)
        self.declare_parameter('fps', 30)
        self.declare_parameter('width', 1920)
        self.declare_parameter('height', 1080)
        self.declare_parameter('stream_type', 'rtmp')
        self.declare_parameter('use_nvidia_hw', True)
        self.declare_parameter('auto_detect_resolution', True)
        self.declare_parameter('stall_timeout_sec', 2.0)
        self.declare_parameter('watchdog_period_sec', 0.5)
        self.declare_parameter('restart_cooldown_sec', 2.0)

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
        self.fps = max(fps, 1)
        self.param_width = width
        self.param_height = height
        self.stream_type = stream_type
        self.use_nvidia_hw = use_nvidia_hw
        self.auto_detect_resolution = auto_detect_resolution
        self.stall_timeout_sec = (
            self.get_parameter('stall_timeout_sec').get_parameter_value().double_value
        )
        self._restart_cooldown_sec = (
            self.get_parameter('restart_cooldown_sec').get_parameter_value().double_value
        )

        self.pipeline = None
        self.appsrc = None
        self._pipeline_width = 0
        self._pipeline_height = 0
        self._last_frame_monotonic = None
        self._pipeline_restart_count = 0
        self._stream_frame_index = 0
        self._next_restart_monotonic = 0.0
        self._frames_since_restart = 0

        self.get_logger().info(f'Subscribing to topic: {input_topic}')
        self.get_logger().info(f'Stream type: {stream_type}')
        if stream_type == 'rtmp':
            rtmp_url = f'rtmp://{stream_host}:{stream_port}/{stream_path}'
            self.get_logger().info(f'RTMP URL: {rtmp_url}')
            self.get_logger().info(f'Using NVIDIA hardware acceleration: {use_nvidia_hw}')
            self.get_logger().info(f'Bitrate: {bitrate} bps ({bitrate // 1000} kbps), FPS: {self.fps}')
        else:
            self.get_logger().info(f'Stream destination: {stream_host}:{stream_port}')
            self.get_logger().info(f'Bitrate: {bitrate} kbps, FPS: {self.fps}')
        if auto_detect_resolution:
            self.get_logger().info('Resolution: auto-detect from input frames')
        else:
            self.get_logger().info(f'Resolution: {width}x{height}')

        self.bridge = CvBridge()
        self.subscription = self.create_subscription(
            Image,
            input_topic,
            self.image_callback,
            10,
        )
        self.get_logger().info('Created subscription with queue depth: 10')
        self.get_logger().info('Realsense Video Publisher node started')
        self.frame_count = 0
        self.callback_invoked = False

        watchdog_period = (
            self.get_parameter('watchdog_period_sec').get_parameter_value().double_value
        )
        self.create_timer(watchdog_period, self._watchdog_callback)

    @property
    def pipeline_started(self) -> bool:
        return self.pipeline is not None

    def _watchdog_callback(self):
        if not self.pipeline_started or self._last_frame_monotonic is None:
            return
        gap = time.monotonic() - self._last_frame_monotonic
        if gap > self.stall_timeout_sec:
            self._teardown_pipeline(
                f'no image_raw for {gap:.1f}s (stall_timeout={self.stall_timeout_sec}s)'
            )

    def _poll_bus_messages(self):
        """Drain the bus; tear down on EOS or fatal link errors."""
        if self.pipeline is None:
            return
        bus = self.pipeline.get_bus()
        if bus is None:
            return
        while True:
            msg = bus.pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.EOS)
            if msg is None:
                break
            if msg.type == Gst.MessageType.EOS:
                self.get_logger().warn('GStreamer bus EOS')
                self._teardown_pipeline('bus EOS')
                return
            err, debug = msg.parse_error()
            if 'not-linked' in debug:
                self.get_logger().warning(f'GStreamer not-linked: {debug}')
                self._teardown_pipeline('bus not-linked')
                return
            self.get_logger().warning(f'GStreamer bus error (ignored): {err} debug={debug}')

    def _teardown_pipeline(self, reason: str):
        if self.pipeline is None:
            return
        self._pipeline_restart_count += 1
        self.get_logger().warning(
            f'Tearing down GStreamer pipeline (#{self._pipeline_restart_count}): {reason}'
        )
        pipeline = self.pipeline
        self.pipeline = None
        self.appsrc = None
        self._stream_frame_index = 0
        self._frames_since_restart = 0
        backoff = self._restart_cooldown_sec
        self._next_restart_monotonic = time.monotonic() + backoff
        try:
            pipeline.set_state(Gst.State.NULL)
            pipeline.get_state(2 * Gst.SECOND)
        except Exception as e:
            self.get_logger().error(f'Error stopping pipeline: {e}')

    def _build_pipeline_str(self, width: int, height: int) -> str:
        src = (
            f'appsrc name=source is-live=true format=time do-timestamp=false '
            f'caps=video/x-raw,format=BGR,width={width},height={height},framerate={self.fps}/1 '
            f'! queue max-size-buffers=2 leaky=downstream '
        )
        if self.stream_type == 'rtmp':
            rtmp_url = f'rtmp://{self.stream_host}:{self.stream_port}/{self.stream_path}'
            if self.use_nvidia_hw:
                return (
                    src
                    + '! videoconvert ! video/x-raw,format=NV12 ! '
                    'nvvidconv ! video/x-raw(memory:NVMM),format=NV12 ! '
                    f'nvv4l2h264enc bitrate={self.bitrate} iframeinterval={self.fps} '
                    'insert-sps-pps=true insert-vui=true ! '
                    'h264parse config-interval=1 ! flvmux streamable=true ! '
                    f'rtmpsink location={rtmp_url} sync=false async=false'
                )
            return (
                src
                + '! videoconvert ! '
                f'x264enc bitrate={self.bitrate // 1000} speed-preset=ultrafast tune=zerolatency key-int-max={self.fps} ! '
                f'flvmux streamable=true ! rtmpsink location={rtmp_url} sync=false async=false'
            )
        if self.stream_type == 'udp':
            return (
                src
                + f'! videoconvert ! x264enc bitrate={self.bitrate} speed-preset=ultrafast tune=zerolatency ! '
                f'h264parse ! rtph264pay config-interval=1 pt=96 ! '
                f'udpsink host={self.stream_host} port={self.stream_port}'
            )
        if self.stream_type == 'rtsp':
            return (
                src
                + f'! videoconvert ! x264enc bitrate={self.bitrate} speed-preset=ultrafast tune=zerolatency ! '
                f'h264parse ! rtph264pay config-interval=1 pt=96 ! '
                f'udpsink host={self.stream_host} port={self.stream_port}'
            )
        return (
            src
            + f'! videoconvert ! x264enc bitrate={self.bitrate} speed-preset=ultrafast tune=zerolatency ! '
            f'h264parse ! rtph264pay config-interval=1 pt=96 ! '
            f'udpsink host={self.stream_host} port={self.stream_port}'
        )

    def _setup_pipeline(self, width: int, height: int) -> bool:
        if self.pipeline is not None:
            if width == self._pipeline_width and height == self._pipeline_height:
                return True
            self._teardown_pipeline('resolution change')

        pipeline_str = self._build_pipeline_str(width, height)
        self.get_logger().info(f'GStreamer pipeline: {pipeline_str}')
        try:
            self.pipeline = Gst.parse_launch(pipeline_str)
            appsrc = self.pipeline.get_by_name('source')
            if not appsrc:
                self.get_logger().error('Failed to get appsrc element')
                self.pipeline = None
                return False

            appsrc.set_property('block', False)
            appsrc.set_property('max-buffers', 2)

            if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                self.get_logger().error('Failed to start GStreamer pipeline')
                self.pipeline.set_state(Gst.State.NULL)
                self.pipeline = None
                self.appsrc = None
                return False

            state_ret, state, _pending = self.pipeline.get_state(5 * Gst.SECOND)
            if state_ret == Gst.StateChangeReturn.FAILURE or state != Gst.State.PLAYING:
                self.get_logger().error(
                    f'Pipeline did not reach PLAYING (state={state}, ret={state_ret})'
                )
                self.pipeline.set_state(Gst.State.NULL)
                self.pipeline.get_state(2 * Gst.SECOND)
                self.pipeline = None
                self.appsrc = None
                return False

            self.appsrc = appsrc
            self._pipeline_width = width
            self._pipeline_height = height
            self._stream_frame_index = 0
            self._frames_since_restart = 0
            self.get_logger().info('GStreamer pipeline started successfully')
            return True
        except Exception as e:
            self.get_logger().error(f'Failed to create GStreamer pipeline: {e}')
            import traceback
            self.get_logger().error(f'Traceback: {traceback.format_exc()}')
            return False

    def image_callback(self, msg):
        self._last_frame_monotonic = time.monotonic()

        if not self.callback_invoked:
            self.get_logger().info('Image callback invoked - receiving Image messages!')
            self.get_logger().info(f'Image encoding: {msg.encoding}')
            self.get_logger().info(f'Image size: {msg.width}x{msg.height}')
            self.callback_invoked = True

        if self.pipeline is None:
            cooldown_left = self._next_restart_monotonic - time.monotonic()
            if cooldown_left > 0:
                return
            self.get_logger().info(
                f'Starting pipeline for {msg.width}x{msg.height} '
                f'(restarts so far: {self._pipeline_restart_count})'
            )
            if not self._setup_pipeline(msg.width, msg.height):
                return

        try:
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            height, width, _channels = cv_image.shape

            if not self.auto_detect_resolution:
                if width != self.param_width or height != self.param_height:
                    cv_image = cv2.resize(cv_image, (self.param_width, self.param_height))
                    height, width = self.param_height, self.param_width

            image_data = np.ascontiguousarray(cv_image)
            buffer = Gst.Buffer.new_allocate(None, image_data.nbytes, None)
            buffer.fill(0, image_data.tobytes())

            frame_duration = Gst.SECOND // self.fps
            buffer.pts = self._stream_frame_index * frame_duration
            buffer.duration = frame_duration

            ret = self.appsrc.emit('push-buffer', buffer)
            if ret == Gst.FlowReturn.OK:
                self._stream_frame_index += 1
                self._frames_since_restart += 1
                if self._frames_since_restart == 30:
                    self._next_restart_monotonic = 0.0

            self._poll_bus_messages()

            if ret == Gst.FlowReturn.FLUSHING:
                self.get_logger().warn('Pipeline flushing; will restart on next frame')
                self._teardown_pipeline('push-buffer FLUSHING')
            elif ret == Gst.FlowReturn.EOS:
                self.get_logger().warn('Pipeline EOS from appsrc; will restart on next frame')
                self._teardown_pipeline('push-buffer EOS')
            elif ret != Gst.FlowReturn.OK:
                self.get_logger().warn(f'push-buffer returned {ret}; restarting pipeline')
                self._teardown_pipeline(f'push-buffer {ret}')

            if ret == Gst.FlowReturn.OK:
                self.frame_count += 1
                if self.frame_count % 30 == 0:
                    self.get_logger().info(
                        f'Processed {self.frame_count} frames, '
                        f'last frame size: {width}x{height}, '
                        f'pipeline restarts: {self._pipeline_restart_count}'
                    )

        except Exception as e:
            import traceback
            self.get_logger().error(f'Error processing image frame: {e}')
            self.get_logger().error(f'Traceback: {traceback.format_exc()}')
            self._teardown_pipeline(f'frame error: {e}')

    def destroy_node(self):
        try:
            self._teardown_pipeline('node shutdown')
        except Exception as e:
            self.get_logger().error(f'Error during cleanup: {e}')
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = RealsenseVideoPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
