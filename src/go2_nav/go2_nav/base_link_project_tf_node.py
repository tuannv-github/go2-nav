#!/usr/bin/env python3
"""
Publish a projected base frame on the parent XY plane.

This node looks up `parent_frame -> base_frame` and republishes
`parent_frame -> projected_frame` with:
- x, y from base_frame
- z forced to 0
- yaw from base_frame orientation
- roll/pitch forced to 0
"""

import math

import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros import Buffer, TransformBroadcaster, TransformException, TransformListener


def yaw_from_quat(x: float, y: float, z: float, w: float) -> float:
    """Extract yaw (Z axis rotation) from quaternion."""
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


def quat_from_yaw(yaw: float) -> tuple[float, float, float, float]:
    """Create quaternion (x,y,z,w) for yaw-only rotation."""
    half = 0.5 * yaw
    return 0.0, 0.0, math.sin(half), math.cos(half)


class BaseLinkProjectTF(Node):
    def __init__(self):
        super().__init__('base_link_project_tf')

        self.declare_parameter('parent_frame', 'vo')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('projected_frame', 'base_link_project')
        self.declare_parameter('publish_rate_hz', 30.0)

        self.parent_frame = self.get_parameter('parent_frame').get_parameter_value().string_value
        self.base_frame = self.get_parameter('base_frame').get_parameter_value().string_value
        self.projected_frame = self.get_parameter('projected_frame').get_parameter_value().string_value
        rate_hz = self.get_parameter('publish_rate_hz').get_parameter_value().double_value

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.tf_broadcaster = TransformBroadcaster(self)

        period = 1.0 / max(rate_hz, 1.0)
        self.create_timer(period, self._publish_projected_tf)

        self._warn_count = 0
        self.get_logger().info(
            f'Publishing projected TF: {self.parent_frame} -> {self.projected_frame} '
            f'(source base frame: {self.base_frame}, z=0, yaw only)'
        )

    def _publish_projected_tf(self):
        try:
            src = self.tf_buffer.lookup_transform(
                self.parent_frame,
                self.base_frame,
                rclpy.time.Time(),
            )
        except TransformException as ex:
            # Keep logs readable on startup while TF tree is stabilizing.
            self._warn_count += 1
            if self._warn_count % 30 == 1:
                self.get_logger().warn(
                    f'Cannot lookup {self.parent_frame} -> {self.base_frame}: {ex}'
                )
            return

        q = src.transform.rotation
        yaw = yaw_from_quat(q.x, q.y, q.z, q.w)
        qx, qy, qz, qw = quat_from_yaw(yaw)

        out = TransformStamped()
        out.header.stamp = self.get_clock().now().to_msg()
        out.header.frame_id = self.parent_frame
        out.child_frame_id = self.projected_frame
        out.transform.translation.x = src.transform.translation.x
        out.transform.translation.y = src.transform.translation.y
        out.transform.translation.z = 0.0
        out.transform.rotation.x = qx
        out.transform.rotation.y = qy
        out.transform.rotation.z = qz
        out.transform.rotation.w = qw

        self.tf_broadcaster.sendTransform(out)


def main(args=None):
    rclpy.init(args=args)
    node = BaseLinkProjectTF()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
