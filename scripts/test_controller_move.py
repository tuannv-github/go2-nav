#!/usr/bin/env python3
"""Go2 controller motion test: drive and yaw via the same paths as Nav2 / REST.

Motions (ROS body frame): forward, backward, left, right, turn_left, turn_right.

Examples:
  ./scripts/test_controller_move.sh
  ./scripts/test_controller_move.sh --action all
  ./scripts/test_controller_move.sh --action forward --distance 1.0 --v 0.2
  ./scripts/test_controller_move.sh --action left --distance 0.4 --v 0.2
  ./scripts/test_controller_move.sh --action right --distance 0.4 --v 0.2
  ./scripts/test_controller_move.sh --action turn_left --angle 90 --w 0.5
  ./scripts/test_controller_move.sh --action turn_right --angle 90 --w 0.5
  ./scripts/test_controller_move.sh --via rest
  ./scripts/test_controller_move.sh --via wireless
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.request

# Match go2_controller_bridge / vlaa calib (invert_cmd_vel_lateral default True).
CMD_VEL_SCALE_VX = 0.85
CMD_VEL_SCALE_VY = 1.25
CMD_VEL_SCALE_W = 1.25
INVERT_LATERAL = True

ACTIONS = (
    'forward',
    'backward',
    'left',
    'right',
    'turn_left',
    'turn_right',
)


def _twist_to_sticks(vx: float, vy: float, wz: float) -> tuple[float, float, float]:
    ly = vx * CMD_VEL_SCALE_VX
    lx = (-vy if INVERT_LATERAL else vy) * CMD_VEL_SCALE_VY
    rx = (-wz) * CMD_VEL_SCALE_W
    return lx, ly, rx


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        '--action',
        choices=(*ACTIONS, 'all'),
        default='all',
        help='One motion or all six in sequence (default: all)',
    )
    p.add_argument('--v', type=float, default=0.2, dest='speed', help='Linear |v| m/s (default: 0.2)')
    p.add_argument('--distance', type=float, default=0.4, help='Linear travel m (default: 0.4)')
    p.add_argument('--w', type=float, default=0.5, dest='yaw_rate', help='Yaw |wz| rad/s (default: 0.5)')
    p.add_argument('--angle', type=float, default=90.0, help='Yaw change deg (default: 90)')
    p.add_argument('--pause', type=float, default=1.5, help='Seconds between motions in --action all')
    p.add_argument(
        '--via',
        choices=('ros', 'rest', 'wireless'),
        default='ros',
        help='ros=/cmd_vel; rest=POST /cmd_vel sport Move; wireless=POST /wireless',
    )
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8081)
    p.add_argument('--hz', type=float, default=20.0)
    p.add_argument('--countdown', type=float, default=2.0)
    p.add_argument('--topic', default='/cmd_vel')
    return p.parse_args()


def _motion(name: str, speed: float, distance: float, yaw_rate: float, angle_deg: float) -> dict:
    v = abs(speed)
    w = abs(yaw_rate)
    lin_t = distance / v if v > 0 else 0.0
    yaw_t = math.radians(angle_deg) / w if w > 0 else 0.0
    table = {
        'forward': (v, 0.0, 0.0, lin_t, f'+{distance:.2f} m forward'),
        'backward': (-v, 0.0, 0.0, lin_t, f'{distance:.2f} m backward'),
        'left': (0.0, v, 0.0, lin_t, f'+{distance:.2f} m left (strafe)'),
        'right': (0.0, -v, 0.0, lin_t, f'{distance:.2f} m right (strafe)'),
        'turn_left': (0.0, 0.0, w, yaw_t, f'+{angle_deg:.0f}° CCW / left'),
        'turn_right': (0.0, 0.0, -w, yaw_t, f'{angle_deg:.0f}° CW / right'),
    }
    vx, vy, wz, duration, expect = table[name]
    lx, ly, rx = _twist_to_sticks(vx, vy, wz)
    return {
        'name': name,
        'vx': vx,
        'vy': vy,
        'wz': wz,
        'duration': duration,
        'expect': expect,
        'lx': lx,
        'ly': ly,
        'rx': rx,
    }


def _post_json(url: str, body: dict | None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json'} if body is not None else {},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else {}


def _stop(via: str, host: str, port: int, ros_pub=None, ros_node=None) -> None:
    if via == 'ros' and ros_pub is not None:
        from geometry_msgs.msg import Twist

        zero = Twist()
        for _ in range(5):
            ros_pub.publish(zero)
            if ros_node is not None:
                import rclpy

                rclpy.spin_once(ros_node, timeout_sec=0.0)
            time.sleep(0.05)
        return
    base = f'http://{host}:{port}'
    if via == 'rest':
        _post_json(f'{base}/cmd_vel/stop', None)
    else:
        _post_json(f'{base}/wireless', {'lx': 0.0, 'ly': 0.0, 'rx': 0.0, 'ry': 0.0, 'keys': 0})


def _run_ros_step(pub, node, step: dict, hz: float) -> None:
    import rclpy
    from geometry_msgs.msg import Twist

    msg = Twist()
    msg.linear.x = step['vx']
    msg.linear.y = step['vy']
    msg.angular.z = step['wz']
    period = 1.0 / max(hz, 1.0)
    deadline = time.monotonic() + step['duration']
    print(
        f"  ROS /cmd_vel vx={step['vx']:+.2f} vy={step['vy']:+.2f} wz={step['wz']:+.2f} "
        f"for {step['duration']:.2f}s",
        flush=True,
    )
    while time.monotonic() < deadline:
        pub.publish(msg)
        rclpy.spin_once(node, timeout_sec=0.0)
        time.sleep(period)
    _stop('ros', '', 0, ros_pub=pub, ros_node=node)


def _run_rest_step(host: str, port: int, step: dict) -> None:
    base = f'http://{host}:{port}'
    body = {'vx': step['vx'], 'vy': step['vy'], 'w': step['wz'], 'duration': step['duration']}
    print(f'  POST {base}/cmd_vel {body}', flush=True)
    print(' ', _post_json(f'{base}/cmd_vel', body))
    time.sleep(step['duration'] + 0.3)
    _post_json(f'{base}/cmd_vel/stop', None)


def _run_wireless_step(host: str, port: int, step: dict) -> None:
    base = f'http://{host}:{port}'
    body = {'lx': step['lx'], 'ly': step['ly'], 'rx': step['rx'], 'ry': 0.0, 'keys': 0}
    print(f'  POST {base}/wireless {body}  ({step["duration"]:.2f}s)', flush=True)
    print(' ', _post_json(f'{base}/wireless', body))
    time.sleep(step['duration'])
    _post_json(f'{base}/wireless', {'lx': 0.0, 'ly': 0.0, 'rx': 0.0, 'ry': 0.0, 'keys': 0})


def main() -> int:
    args = _parse_args()
    if args.speed <= 0 or args.distance <= 0 or args.yaw_rate <= 0 or args.angle <= 0:
        print('error: --v --distance --w --angle must be > 0', file=sys.stderr)
        return 2

    names = list(ACTIONS) if args.action == 'all' else [args.action]
    steps = [_motion(n, args.speed, args.distance, args.yaw_rate, args.angle) for n in names]

    print(f'Controller move test  via={args.via}  actions={", ".join(names)}')
    for s in steps:
        print(
            f"  {s['name']:11} {s['expect']:28}  "
            f"cmd vx={s['vx']:+.2f} vy={s['vy']:+.2f} wz={s['wz']:+.2f}  "
            f"stick lx={s['lx']:+.2f} ly={s['ly']:+.2f} rx={s['rx']:+.2f}"
        )

    ros_node = ros_pub = None
    try:
        if args.countdown > 0:
            print(f'Clear the dog — starting in {args.countdown:.0f}s (Ctrl-C abort)...', flush=True)
            time.sleep(args.countdown)

        if args.via == 'ros':
            import rclpy
            from geometry_msgs.msg import Twist
            from rclpy.node import Node
            from rclpy.qos import QoSProfile, ReliabilityPolicy

            rclpy.init()
            ros_node = Node('test_controller_move')
            ros_pub = ros_node.create_publisher(
                Twist,
                args.topic,
                QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE),
            )

        for i, step in enumerate(steps):
            print(f'\n[{i + 1}/{len(steps)}] {step["name"]}: {step["expect"]}', flush=True)
            if args.via == 'ros':
                _run_ros_step(ros_pub, ros_node, step, args.hz)
            elif args.via == 'rest':
                _run_rest_step(args.host, args.port, step)
            else:
                _run_wireless_step(args.host, args.port, step)
            if i + 1 < len(steps) and args.pause > 0:
                time.sleep(args.pause)
    except KeyboardInterrupt:
        print('\naborted — stop', flush=True)
        try:
            _stop(args.via, args.host, args.port, ros_pub=ros_pub, ros_node=ros_node)
        except Exception:
            pass
        return 130
    except Exception as ex:
        print(f'error: {ex}', file=sys.stderr)
        try:
            _stop(args.via, args.host, args.port, ros_pub=ros_pub, ros_node=ros_node)
        except Exception:
            pass
        return 1
    finally:
        if ros_node is not None:
            import rclpy

            ros_node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()

    print('\nDone. Check each axis sign against the labels above.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
