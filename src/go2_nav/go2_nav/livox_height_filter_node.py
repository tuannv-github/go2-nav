#!/usr/bin/env python3
"""Drop Livox returns that are ground / ceiling before Nav2 costmaps see them.

Nav2 ObstacleLayer filters z in the costmap frame (odom/map). After odom reset,
base_link.z is often ~0.27 m while the floor sheet sits at ~0.12–0.20 m odom,
so a fixed 8–15 cm min_obstacle_height still marks the ground.

This node keeps points by z in ``height_frame`` (default base_link), where the
floor is below z≈0. Output stays in the sensor frame for Nav2 TF.
"""

from __future__ import annotations

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import PointCloud2
from tf2_ros import Buffer, TransformException, TransformListener


# Livox driver publishes RELIABLE; a BEST_EFFORT subscription will not match.
_LIVOX_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)
# Nav2 costmaps subscribe BEST_EFFORT; RELIABLE pub is compatible with that.
_NAV_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


def _quat_to_rot(x: float, y: float, z: float, w: float) -> np.ndarray:
    return np.array(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


class LivoxHeightFilter(Node):
    def __init__(self) -> None:
        super().__init__('livox_height_filter')

        self.declare_parameter('input_topic', '/livox/lidar')
        self.declare_parameter('output_topic', '/livox/lidar_nav')
        self.declare_parameter('height_frame', 'base_link')
        # Floor lobe in base_link is about -0.20..0.00 m while standing.
        self.declare_parameter('min_z', 0.05)
        self.declare_parameter('max_z', 0.50)
        self.declare_parameter('min_range', 0.15)

        self.input_topic = self.get_parameter('input_topic').get_parameter_value().string_value
        self.output_topic = self.get_parameter('output_topic').get_parameter_value().string_value
        self.height_frame = self.get_parameter('height_frame').get_parameter_value().string_value
        self.min_z = self.get_parameter('min_z').get_parameter_value().double_value
        self.max_z = self.get_parameter('max_z').get_parameter_value().double_value
        self.min_range = self.get_parameter('min_range').get_parameter_value().double_value

        self._tf = Buffer()
        self._tf_listener = TransformListener(self._tf, self)
        self._pub = self.create_publisher(PointCloud2, self.output_topic, _NAV_QOS)
        self.create_subscription(PointCloud2, self.input_topic, self._cb, _LIVOX_QOS)

        self._warn_tf = 0
        self._n = 0
        self.get_logger().info(
            f'{self.input_topic} -> {self.output_topic}  keep {self.min_z:.2f} < z_{self.height_frame} < '
            f'{self.max_z:.2f} m, range >= {self.min_range:.2f} m'
        )

    def _cb(self, msg: PointCloud2) -> None:
        try:
            self._filter_cloud(msg)
        except Exception as ex:  # noqa: BLE001 — keep the node alive, log the fault
            self.get_logger().error(f'filter failed: {ex}')

    def _filter_cloud(self, msg: PointCloud2) -> None:
        src_frame = msg.header.frame_id or 'livox_frame'
        try:
            tf = self._tf.lookup_transform(self.height_frame, src_frame, rclpy.time.Time())
        except TransformException as ex:
            self._warn_tf += 1
            if self._warn_tf % 30 == 1:
                self.get_logger().warn(f'Cannot lookup {self.height_frame} <- {src_frame}: {ex}')
            return

        off = {f.name: f.offset for f in msg.fields}
        if not all(k in off for k in ('x', 'y', 'z')):
            self.get_logger().error('PointCloud2 missing x/y/z fields')
            return

        n = msg.width * msg.height
        step = msg.point_step
        if n == 0 or step < 12 or len(msg.data) < n * step:
            return

        raw = np.frombuffer(msg.data, dtype=np.uint8, count=n * step).reshape(n, step)
        xs = raw[:, off['x']:off['x'] + 4].copy().view('<f4').reshape(-1).astype(np.float64)
        ys = raw[:, off['y']:off['y'] + 4].copy().view('<f4').reshape(-1).astype(np.float64)
        zs = raw[:, off['z']:off['z'] + 4].copy().view('<f4').reshape(-1).astype(np.float64)

        t = tf.transform.translation
        q = tf.transform.rotation
        rot = _quat_to_rot(q.x, q.y, q.z, q.w)
        z_h = rot[2, 0] * xs + rot[2, 1] * ys + rot[2, 2] * zs + t.z
        rng = np.sqrt(xs * xs + ys * ys + zs * zs)
        keep = (
            np.isfinite(xs)
            & np.isfinite(ys)
            & np.isfinite(zs)
            & (z_h > self.min_z)
            & (z_h < self.max_z)
            & (rng >= self.min_range)
        )
        kept = raw[keep]

        out = PointCloud2()
        out.header = msg.header
        out.height = 1
        out.width = int(kept.shape[0])
        out.fields = msg.fields
        out.is_bigendian = msg.is_bigendian
        out.point_step = step
        out.row_step = step * out.width
        out.is_dense = True
        out.data = kept.tobytes() if kept.size else b''

        self._pub.publish(out)
        self._n += 1
        if self._n == 1 or self._n % 50 == 0:
            self.get_logger().info(f'kept {out.width}/{n} points for Nav2')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = LivoxHeightFilter()
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
