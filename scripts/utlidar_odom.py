#!/usr/bin/env python3
"""In-place monitor for Unitree ``/utlidar/robot_odom`` pose.

Sources ``scripts/setup.eth0.sh`` internally (eth0 DDS). Usage:

  ./scripts/utlidar_odom.py

Live commands (type + Enter):
  -r   reset origin to current pose
  q    quit
"""

from __future__ import annotations

import argparse
import math
import os
import shlex
import sys
import threading
import time
from collections import deque
from pathlib import Path

_ENV_MARK = '_UTLIDAR_ODOM_ENV'
_LABEL_W = 14


def _source_ros_env() -> None:
    """Re-exec under bash after sourcing setup.eth0.sh (ROS + CycloneDDS eth0)."""
    if os.environ.get(_ENV_MARK) == '1':
        return
    setup = Path(__file__).resolve().parent / 'setup.eth0.sh'
    if not setup.is_file():
        print(f'error: missing ROS setup: {setup}', file=sys.stderr)
        sys.exit(1)
    self = Path(__file__).resolve()
    cmd = (
        f'set +u; source {shlex.quote(str(setup))} >/dev/null; '
        f'export {_ENV_MARK}=1; '
        f'exec {shlex.quote(sys.executable)} {shlex.quote(str(self))} '
        + ' '.join(shlex.quote(a) for a in sys.argv[1:])
    )
    os.execvp('bash', ['bash', '-c', cmd])


def yaw_deg(q) -> float:
    return math.degrees(
        math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
    )


def wrap_deg(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


def fmt_pose(x: float, y: float, z: float, yaw: float, extra: str = '') -> str:
    return f'x={x:8.3f}  y={y:8.3f}  z={z:8.3f}  yaw={yaw:7.1f}°{extra}'


def relative(abs_pose: tuple[float, float, float, float], origin: tuple[float, float, float, float]):
    x, y, z, yaw = abs_pose
    ox, oy, oz, oyaw = origin
    c = math.cos(math.radians(-oyaw))
    s = math.sin(math.radians(-oyaw))
    dx, dy = x - ox, y - oy
    return (c * dx - s * dy, s * dx + c * dy, z - oz, wrap_deg(yaw - oyaw))


def main() -> int:
    parser = argparse.ArgumentParser(description='Monitor /utlidar/robot_odom pose in-place.')
    parser.add_argument(
        '--topic',
        default='/utlidar/robot_odom',
        help='Odometry topic (default: /utlidar/robot_odom)',
    )
    args = parser.parse_args()

    try:
        import rclpy
        from rclpy.executors import ExternalShutdownException
        from rclpy.node import Node
        from nav_msgs.msg import Odometry
    except ImportError:
        print(
            f'error: ROS 2 Python not available after sourcing {Path(__file__).resolve().parent / "setup.eth0.sh"}',
            file=sys.stderr,
        )
        return 1

    class Monitor(Node):
        def __init__(self) -> None:
            super().__init__('utlidar_odom_mon')
            self._lock = threading.Lock()
            self._abs: tuple[float, float, float, float] | None = None
            self._origin: tuple[float, float, float, float] | None = None
            self._stamps: deque[float] = deque(maxlen=40)
            self._hz = 0.0
            self._running = True
            self._tty = sys.stdin.isatty() and sys.stdout.isatty()
            self.create_subscription(Odometry, args.topic, self._cb, 10)
            self.create_timer(0.1, self._draw)

            print(f'monitoring {args.topic}   commands: -r reset origin   q quit')
            self._print_row('utlidar_odom:', '(waiting)')
            self._print_row('origin_pose:', '(waiting)')
            self._print_row('odom:', '(waiting)')
            if self._tty:
                print('cmd> ', end='', flush=True)
                threading.Thread(target=self._input_loop, name='cmd', daemon=True).start()

        @staticmethod
        def _print_row(label: str, value: str) -> None:
            print(f'\033[2K{label:<{_LABEL_W}}{value}')

        def _cb(self, msg: Odometry) -> None:
            now = time.monotonic()
            p = msg.pose.pose.position
            pose = (p.x, p.y, p.z, yaw_deg(msg.pose.pose.orientation))
            with self._lock:
                self._stamps.append(now)
                if len(self._stamps) >= 2:
                    dt = self._stamps[-1] - self._stamps[0]
                    if dt > 0.0:
                        self._hz = (len(self._stamps) - 1) / dt
                self._abs = pose
                if self._origin is None:
                    self._origin = pose

        def _reset_origin(self) -> None:
            with self._lock:
                if self._abs is None:
                    return
                self._origin = self._abs

        def _input_loop(self) -> None:
            while self._running:
                try:
                    line = sys.stdin.readline()
                except Exception:
                    break
                if not line:
                    break
                cmd = line.strip().lower()
                if cmd in ('-r', 'r', 'reset'):
                    self._reset_origin()
                elif cmd in ('q', 'quit', 'exit'):
                    self._running = False
                    if rclpy.ok():
                        rclpy.shutdown()
                    break
                if self._running and self._tty:
                    print('\r\033[2Kcmd> ', end='', flush=True)

        def _draw(self) -> None:
            if not self._running:
                return
            with self._lock:
                abs_pose = self._abs
                origin = self._origin
                hz = self._hz
            if abs_pose is None:
                return

            ut = fmt_pose(*abs_pose, extra=f'  {hz:5.0f} Hz')
            if origin is None:
                orig_s = '(unset, type -r)'
                odom_s = '—'
            else:
                orig_s = fmt_pose(*origin)
                odom_s = fmt_pose(*relative(abs_pose, origin))

            sys.stdout.write('\033[s\033[3A')
            self._print_row('utlidar_odom:', ut)
            self._print_row('origin_pose:', orig_s)
            self._print_row('odom:', odom_s)
            sys.stdout.write('\033[u')
            sys.stdout.flush()

    rclpy.init(args=None)
    node = Monitor()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node._running = False
        if node._tty:
            print()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == '__main__':
    _source_ros_env()
    sys.exit(main())
