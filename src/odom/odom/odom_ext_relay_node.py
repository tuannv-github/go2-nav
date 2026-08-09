#!/usr/bin/env python3
"""Publish ``/odom`` on all NICs (0.0.0.0) from the eth0 bridge named pipe.

A second Cyclone participant is required so eth0 Unitree SPDP is not mixed
into the same process as the external bus.
"""

from __future__ import annotations

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rclpy.serialization import deserialize_message
from tf2_ros import TransformBroadcaster

from odom.fifo_ipc import FifoReader

_PUB_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


class OdomExtRelay(Node):
    def __init__(self) -> None:
        super().__init__('odom_ext_relay')

        self.declare_parameter('output_topic', '/odom')
        self.declare_parameter('publish_tf', True)
        self.declare_parameter('relay_pipe', '/tmp/go2_odom.fifo')

        topic = self.get_parameter('output_topic').get_parameter_value().string_value
        self.publish_tf = self.get_parameter('publish_tf').get_parameter_value().bool_value
        pipe = self.get_parameter('relay_pipe').get_parameter_value().string_value

        self._pub = self.create_publisher(Odometry, topic, _PUB_QOS)
        self._tf = TransformBroadcaster(self) if self.publish_tf else None
        self._n = 0
        self._fifo = FifoReader(pipe)
        self.create_timer(0.005, self._poll)

        self.get_logger().info(f'ext /odom relay listening fifo {pipe} -> {topic}')

    def destroy_node(self) -> bool:
        self._fifo.close()
        return super().destroy_node()

    def _poll(self) -> None:
        try:
            frames = self._fifo.read_messages()
        except OSError as exc:
            self.get_logger().warn(f'relay fifo: {exc}')
            return
        for data in frames:
            try:
                msg = deserialize_message(data, Odometry)
            except Exception as exc:  # noqa: BLE001
                self.get_logger().warn(f'relay deserialize: {exc}')
                continue
            self._n += 1
            self._pub.publish(msg)
            if self._n == 1 or self._n % 200 == 0:
                self.get_logger().info(f'ext published /odom n={self._n}')
            if self._tf is None:
                continue
            t = TransformStamped()
            t.header = msg.header
            t.child_frame_id = msg.child_frame_id
            t.transform.translation.x = msg.pose.pose.position.x
            t.transform.translation.y = msg.pose.pose.position.y
            t.transform.translation.z = msg.pose.pose.position.z
            t.transform.rotation = msg.pose.pose.orientation
            self._tf.sendTransform(t)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = OdomExtRelay()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
