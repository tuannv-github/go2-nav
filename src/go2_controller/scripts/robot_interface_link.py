#!/usr/bin/env python3
"""Declare this Go2 on the NeuroRAN robot interface and publish its location.

Connects to ``/ws/robots``, sends ``hello``, then POSTs the map pose as
``x, y, z`` metres and heading ``w`` radians to ``/api/robots/{robot_id}/location``
every ``period_sec`` (default 0.1). The interface pushes that fix back on the
socket; this client acks it.
"""

from __future__ import annotations

import json
import math
import threading
import time
from typing import Callable, Optional
from urllib.parse import urlparse, urlunparse

import requests
import websocket

DEFAULT_URL = 'http://10.1.101.220:6112'
DEFAULT_ROBOT_ID = 'go2'
DEFAULT_NAME = 'Go2'
DEFAULT_IMSI = ''
DEFAULT_PERIOD_SEC = 0.1
DEFAULT_ACCURACY_M = 1.0


def http_to_ws(url: str) -> str:
    """``http://host:6112`` -> ``ws://host:6112`` (https -> wss)."""
    parsed = urlparse(url.strip())
    scheme = 'wss' if parsed.scheme == 'https' else 'ws'
    return urlunparse((scheme, parsed.netloc, '', '', '', ''))


class RobotInterfaceLink:
    """One websocket to the robot interface, plus a 10 Hz location publisher."""

    def __init__(
        self,
        url: str = DEFAULT_URL,
        robot_id: str = DEFAULT_ROBOT_ID,
        name: str = DEFAULT_NAME,
        imsis: Optional[list[str]] = None,
        period_sec: float = DEFAULT_PERIOD_SEC,
        accuracy_m: float = DEFAULT_ACCURACY_M,
        pose_provider: Optional[Callable[[], Optional[dict]]] = None,
        on_command: Optional[Callable[[str, dict], tuple[str, str]]] = None,
        logger=None,
    ):
        self.url = url.rstrip('/')
        self.robot_id = robot_id
        self.name = name
        self.imsis = list(imsis or [DEFAULT_IMSI])
        self.period_sec = max(0.02, float(period_sec))
        self.accuracy_m = float(accuracy_m)
        self.pose_provider = pose_provider
        self.on_command = on_command
        self.logger = logger
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._ws_lock = threading.Lock()
        self._last_ok_log = 0.0
        self._last_warn_log = 0.0
        self._post_lock = threading.Lock()
        self._inflight = 0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name='robot-interface', daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._ws_lock:
            ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _log(self, level: str, message: str) -> None:
        if self.logger is None:
            print(f'robot-interface {level}: {message}', flush=True)
            return
        # rclpy pins severity to the call site, so info and warning cannot share one function.
        if level == 'warning':
            self._log_warning(message)
            return
        self._log_info(message)

    def _log_info(self, message: str) -> None:
        self.logger.info(message)

    def _log_warning(self, message: str) -> None:
        self.logger.warning(message)

    def _warn(self, message: str) -> None:
        now = time.monotonic()
        if now - self._last_warn_log < 5.0:
            return
        self._last_warn_log = now
        self._log('warning', message)

    def _run(self) -> None:
        ws_url = http_to_ws(self.url) + '/ws/robots'
        while not self._stop.is_set():
            try:
                self._session(ws_url)
            except Exception as exc:
                self._log('warning', f'reconnecting to {ws_url}: {exc}')
            self._ready.clear()
            self._stop.wait(1.0)

    def _session(self, ws_url: str) -> None:
        ws = websocket.create_connection(ws_url, timeout=5)
        ws.settimeout(1.0)
        with self._ws_lock:
            self._ws = ws
        hello = {
            'type': 'hello',
            'robot_id': self.robot_id,
            'name': self.name,
            'imsis': self.imsis,
        }
        ws.send(json.dumps(hello))
        self._log(
            'info',
            f'declared {self.robot_id} ({",".join(self.imsis)}) on {ws_url}',
        )
        reader = threading.Thread(
            target=self._read_loop, args=(ws,), name='robot-interface-rx', daemon=True
        )
        reader.start()
        try:
            while not self._stop.is_set() and reader.is_alive():
                started = time.monotonic()
                if self._ready.is_set():
                    self._schedule_location()
                remain = self.period_sec - (time.monotonic() - started)
                if remain > 0:
                    self._stop.wait(remain)
        finally:
            self._ready.clear()
            try:
                ws.close()
            except Exception:
                pass
            with self._ws_lock:
                if self._ws is ws:
                    self._ws = None
            reader.join(timeout=2.0)

    def _read_loop(self, ws) -> None:
        while not self._stop.is_set():
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                return
            if not raw:
                return
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = message.get('type')
            if kind == 'welcome':
                self._ready.set()
                self._log('info', f'welcome robot_id={message.get("robot_id")}')
                continue
            if kind == 'location':
                ws.send(json.dumps({
                    'type': 'location_ack',
                    'seq': message.get('seq'),
                    'robot_id': self.robot_id,
                }))
                continue
            if kind == 'command':
                status, detail = self._handle_command(message)
                ws.send(json.dumps({
                    'type': 'command_result',
                    'command_id': message.get('command_id'),
                    'action': message.get('action'),
                    'status': status,
                    'detail': detail,
                }))
                continue
            if kind == 'error':
                self._log('warning', f'interface error: {message.get("detail")}')
                return

    def _handle_command(self, message: dict) -> tuple[str, str]:
        action = str(message.get('action') or '')
        if self.on_command is None:
            return 'rejected', 'no command handler'
        try:
            status, detail = self.on_command(action, message)
        except Exception as exc:
            return 'rejected', str(exc)
        if status not in ('applied', 'rejected', 'sent'):
            return 'rejected', detail or 'bad status'
        return status, detail

    def _schedule_location(self) -> None:
        with self._post_lock:
            if self._inflight >= 2:
                return
            self._inflight += 1

        def _run():
            try:
                self._post_location()
            finally:
                with self._post_lock:
                    self._inflight -= 1

        threading.Thread(target=_run, name='robot-interface-tx', daemon=True).start()

    def _post_location(self) -> None:
        if self.pose_provider is None:
            return
        try:
            pose = self.pose_provider()
        except Exception as exc:
            self._log('warning', f'pose lookup failed: {exc}')
            return
        if not pose:
            return
        body = {
            'x': float(pose['x']),
            'y': float(pose['y']),
            'z': float(pose.get('z', 0.0)),
            'w': float(pose.get('w', pose.get('yaw', 0.0))),
            'accuracy_m': self.accuracy_m,
            'imsi': self.imsis[0],
            'source': 'go2',
        }
        try:
            response = requests.post(
                f'{self.url}/api/robots/{self.robot_id}/location',
                json=body,
                timeout=1.0,
            )
        except requests.RequestException as exc:
            self._warn(f'location post failed: {exc}')
            return
        if response.status_code != 200:
            self._warn(
                f'location post {response.status_code}: {response.text[:200]}',
            )
            return
        now = time.monotonic()
        if now - self._last_ok_log >= 5.0:
            self._last_ok_log = now
            self._log(
                'info',
                f'location x={body["x"]:.2f} y={body["y"]:.2f} '
                f'z={body["z"]:.2f} w={body["w"]:.3f}',
            )


def main() -> None:
    """ROS node: map→base_link at 10 Hz to the robot interface."""
    import rclpy
    from rclpy.duration import Duration
    from rclpy.node import Node
    from tf2_ros import Buffer, TransformException, TransformListener

    rclpy.init()
    node = Node('robot_interface_link')
    node.declare_parameter('url', DEFAULT_URL)
    node.declare_parameter('robot_id', DEFAULT_ROBOT_ID)
    node.declare_parameter('name', DEFAULT_NAME)
    node.declare_parameter('imsi', 'imsi-' + DEFAULT_IMSI)
    node.declare_parameter('period_sec', DEFAULT_PERIOD_SEC)
    node.declare_parameter('accuracy_m', DEFAULT_ACCURACY_M)
    node.declare_parameter('pose_frame', 'map')
    node.declare_parameter('base_frame', 'base_link')

    url = node.get_parameter('url').get_parameter_value().string_value
    robot_id = node.get_parameter('robot_id').get_parameter_value().string_value
    name = node.get_parameter('name').get_parameter_value().string_value
    imsi = node.get_parameter('imsi').get_parameter_value().string_value.removeprefix('imsi-')
    period = node.get_parameter('period_sec').get_parameter_value().double_value
    accuracy = node.get_parameter('accuracy_m').get_parameter_value().double_value
    pose_frame = node.get_parameter('pose_frame').get_parameter_value().string_value
    base_frame = node.get_parameter('base_frame').get_parameter_value().string_value

    buffer = Buffer()
    TransformListener(buffer, node)

    def pose():
        try:
            tf = buffer.lookup_transform(
                pose_frame, base_frame, rclpy.time.Time(), timeout=Duration(seconds=0.05)
            )
        except TransformException:
            return None
        t = tf.transform.translation
        q = tf.transform.rotation
        yaw = 2.0 * math.atan2(float(q.z), float(q.w))
        return {'x': float(t.x), 'y': float(t.y), 'z': float(t.z), 'w': yaw}

    link = RobotInterfaceLink(
        url=url,
        robot_id=robot_id,
        name=name,
        imsis=[imsi],
        period_sec=period,
        accuracy_m=accuracy,
        pose_provider=pose,
        logger=node.get_logger(),
    )
    link.start()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        link.stop()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
