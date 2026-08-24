#!/usr/bin/env python3
"""Print ROS /cmd_vel Twist as one line (vx vy wz + expected sticks).

Examples:
  ./scripts/print_cmd_vel.sh
  ./scripts/print_cmd_vel.sh --topic /cmd_vel
  ./scripts/print_cmd_vel.sh --raw
"""

from __future__ import annotations

import argparse

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import qos_profile_system_default

# Match go2_controller_bridge defaults.
CMD_VEL_SCALE_VX = 0.85
CMD_VEL_SCALE_VY = 1.25
CMD_VEL_SCALE_W = 1.25
INVERT_LATERAL = True


def _sticks(vx: float, vy: float, wz: float) -> tuple[float, float, float]:
    ly = vx * CMD_VEL_SCALE_VX
    lx = (-vy if INVERT_LATERAL else vy) * CMD_VEL_SCALE_VY
    rx = (-wz) * CMD_VEL_SCALE_W
    return lx, ly, rx


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--topic', default='/cmd_vel')
    p.add_argument('--raw', action='store_true', help='YAML dump like ros2 topic echo')
    return p.parse_args()


class CmdVelPrinter(Node):
    def __init__(self, topic: str, raw: bool):
        super().__init__('print_cmd_vel')
        self._raw = raw
        self._n = 0
        self.create_subscription(Twist, topic, self._on_twist, qos_profile_system_default)
        print(
            f'Listening {topic}  scale vx×{CMD_VEL_SCALE_VX} vy×{CMD_VEL_SCALE_VY} '
            f'w×{CMD_VEL_SCALE_W:.5f}  invert_lat={INVERT_LATERAL}  Ctrl-C stop',
            flush=True,
        )

    def _on_twist(self, msg: Twist) -> None:
        self._n += 1
        if self._raw:
            print(msg, flush=True)
            return
        vx = float(msg.linear.x)
        vy = float(msg.linear.y)
        wz = float(msg.angular.z)
        lx, ly, rx = _sticks(vx, vy, wz)
        stamp = self.get_clock().now().nanoseconds / 1e9
        print(
            f'{self._n:5d}  t={stamp:.3f}  '
            f'vx={vx:+.3f} vy={vy:+.3f} wz={wz:+.3f}  '
            f'stick lx={lx:+.3f} ly={ly:+.3f} rx={rx:+.3f}',
            flush=True,
        )


def main() -> int:
    args = _parse_args()
    rclpy.init()
    node = CmdVelPrinter(args.topic, args.raw)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
