#!/usr/bin/env python3
"""Declare this Go2 on the NeuroRAN robot interface and publish its location.

Connects to ``/ws/robots``, sends ``hello``, then sends the map pose as
``x, y, z`` metres and heading ``w`` radians in a ``pose`` message every
``period_sec`` (default 0.1). A server ``estimates`` message is stored as the
ran-loc mixture and acked; it is not the robot pose. REST on the interface is
for server-side control.
"""

from __future__ import annotations

import json
import math
import os
import pty
import select
import signal
import struct
import subprocess
import threading
import time
import fcntl
import termios
from typing import Callable, Optional
from urllib.parse import urlparse, urlunparse

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


class TerminalSession:
    """One interactive shell on this robot, forwarded on the robot websocket."""

    def __init__(self, send: Callable[[dict], None]):
        self._send = send
        self._lock = threading.Lock()
        self._master: Optional[int] = None
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def open(self, cols: int = 80, rows: int = 24) -> None:
        self.close()
        cols = max(1, min(int(cols), 500))
        rows = max(1, min(int(rows), 200))
        master, slave = pty.openpty()
        _set_winsize(master, cols, rows)
        try:
            proc = subprocess.Popen(
                ['/bin/bash', '-i'],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                preexec_fn=os.setsid,
                close_fds=True,
                env={**os.environ, 'TERM': 'xterm-256color'},
            )
        except Exception:
            os.close(master)
            os.close(slave)
            raise
        os.close(slave)
        self._stop.clear()
        with self._lock:
            self._master = master
            self._proc = proc
        self._thread = threading.Thread(target=self._read, name='robot-terminal', daemon=True)
        self._thread.start()

    def write(self, data: str) -> None:
        raw = data.encode('utf-8', 'replace')[:8192]
        with self._lock:
            fd = self._master
        if fd is None or not raw:
            return
        try:
            os.write(fd, raw)
        except OSError:
            self.close()

    def resize(self, cols: int, rows: int) -> None:
        with self._lock:
            fd = self._master
        if fd is None:
            return
        _set_winsize(fd, max(1, min(int(cols), 500)), max(1, min(int(rows), 200)))

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            proc = self._proc
            fd = self._master
            self._proc = None
            self._master = None
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGHUP)
            except OSError:
                proc.terminate()
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

    def _read(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                fd = self._master
                proc = self._proc
            if fd is None or proc is None:
                break
            if proc.poll() is not None:
                break
            readable, _, _ = select.select([fd], [], [], 0.2)
            if fd not in readable:
                continue
            try:
                raw = os.read(fd, 4096)
            except OSError:
                break
            if not raw:
                break
            self._send({
                'type': 'terminal_output',
                'data': raw.decode('utf-8', 'replace'),
            })
        natural = not self._stop.is_set()
        code = -1
        with self._lock:
            proc = self._proc
        if proc is not None and proc.poll() is not None:
            code = int(proc.returncode)
        self.close()
        if natural:
            self._send({'type': 'terminal_exit', 'code': code})


def _parse_estimate_locations(raw) -> list[dict]:
    """Keep one ran-loc tick. Highest weight first. Not the robot pose."""
    if not isinstance(raw, list):
        return []
    locations = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            locations.append({
                'seq': item.get('seq'),
                'x': float(item['x']),
                'y': float(item['y']),
                'z': float(item.get('z', 0.0)),
                'w': float(item.get('w', 0.0)),
                'accuracy_m': float(item.get('accuracy_m', 0.0)),
                'weight': float(item.get('weight', 0.0)),
            })
        except (TypeError, ValueError, KeyError):
            continue
    locations.sort(key=lambda fix: fix['weight'], reverse=True)
    return locations


def _set_winsize(fd: int, cols: int, rows: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))


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
        on_estimates: Optional[Callable[[dict], None]] = None,
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
        self.on_estimates = on_estimates
        self.logger = logger
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._ws_lock = threading.Lock()
        self._last_ok_log = 0.0
        self._last_warn_log = 0.0
        self._estimates_lock = threading.Lock()
        self._ran_loc: Optional[dict] = None
        self._last_estimates_log = 0.0
        self._terminal = TerminalSession(self._send_from_terminal)

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
                    self._send_pose()
                remain = self.period_sec - (time.monotonic() - started)
                if remain > 0:
                    self._stop.wait(remain)
        finally:
            self._terminal.close()
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
                self._send(ws, {
                    'type': 'location_ack',
                    'seq': message.get('seq'),
                    'robot_id': self.robot_id,
                })
                continue
            if kind == 'estimates':
                self._store_estimates(ws, message)
                continue
            if kind == 'command':
                status, detail = self._handle_command(message)
                self._send(ws, {
                    'type': 'command_result',
                    'command_id': message.get('command_id'),
                    'action': message.get('action'),
                    'status': status,
                    'detail': detail,
                })
                continue
            if kind == 'terminal_open':
                self._terminal_open(message)
                continue
            if kind == 'terminal_input':
                self._terminal.write(str(message.get('data') or ''))
                continue
            if kind == 'terminal_resize':
                self._terminal.resize(
                    int(message.get('cols') or 80),
                    int(message.get('rows') or 24),
                )
                continue
            if kind == 'terminal_close':
                self._terminal.close()
                continue
            if kind == 'error':
                self._log('warning', f'interface error: {message.get("detail")}')
                return

    def ran_loc_estimates(self) -> Optional[dict]:
        """Latest ran-loc mixture, or None. This is not the robot pose."""
        with self._estimates_lock:
            if self._ran_loc is None:
                return None
            return {
                'seq': self._ran_loc['seq'],
                'robot_id': self._ran_loc['robot_id'],
                'imsi': self._ran_loc['imsi'],
                'source': self._ran_loc['source'],
                'estimated_at': self._ran_loc['estimated_at'],
                'locations': [dict(item) for item in self._ran_loc['locations']],
            }

    def _store_estimates(self, ws, message: dict) -> None:
        if message.get('robot_id') != self.robot_id:
            return
        locations = _parse_estimate_locations(message.get('locations'))
        stored = {
            'seq': message.get('seq'),
            'robot_id': self.robot_id,
            'imsi': message.get('imsi'),
            'source': message.get('source') or 'ran-loc',
            'estimated_at': message.get('estimated_at'),
            'locations': locations,
        }
        with self._estimates_lock:
            self._ran_loc = stored
        if self.on_estimates is not None:
            try:
                self.on_estimates({
                    'seq': stored['seq'],
                    'robot_id': stored['robot_id'],
                    'imsi': stored['imsi'],
                    'source': stored['source'],
                    'estimated_at': stored['estimated_at'],
                    'locations': [dict(item) for item in stored['locations']],
                })
            except Exception as exc:
                self._warn(f'ran-loc publish failed: {exc}')
        self._send(ws, {
            'type': 'estimates_ack',
            'seq': message.get('seq'),
            'robot_id': self.robot_id,
        })
        now = time.monotonic()
        if now - self._last_estimates_log >= 5.0:
            self._last_estimates_log = now
            top = locations[0]['weight'] if locations else 0.0
            self._log(
                'info',
                f'ran-loc seq={message.get("seq")} n={len(locations)} top_weight={top:.2f}',
            )

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

    def _send_from_terminal(self, payload: dict) -> None:
        with self._ws_lock:
            ws = self._ws
        if ws is None:
            return
        try:
            self._send(ws, payload)
        except Exception as exc:
            self._warn(f'terminal send failed: {exc}')

    def _terminal_open(self, message: dict) -> None:
        try:
            self._terminal.open(
                int(message.get('cols') or 80),
                int(message.get('rows') or 24),
            )
        except Exception as exc:
            self._send_from_terminal({'type': 'terminal_exit', 'code': -1, 'detail': str(exc)})

    def _send(self, ws, payload: dict) -> None:
        raw = json.dumps(payload)
        with self._ws_lock:
            ws.send(raw)

    def _send_pose(self) -> None:
        if self.pose_provider is None:
            return
        with self._ws_lock:
            ws = self._ws
        if ws is None:
            return
        try:
            pose = self.pose_provider()
        except Exception as exc:
            self._log('warning', f'pose lookup failed: {exc}')
            return
        if not pose:
            return
        message = {
            'type': 'pose',
            'x': float(pose['x']),
            'y': float(pose['y']),
            'z': float(pose.get('z', 0.0)),
            'w': float(pose.get('w', pose.get('yaw', 0.0))),
            'accuracy_m': self.accuracy_m,
            'imsi': self.imsis[0],
            'source': 'go2',
        }
        try:
            self._send(ws, message)
        except Exception as exc:
            self._warn(f'pose send failed: {exc}')
            return
        now = time.monotonic()
        if now - self._last_ok_log >= 5.0:
            self._last_ok_log = now
            self._log(
                'info',
                f'pose x={message["x"]:.2f} y={message["y"]:.2f} '
                f'z={message["z"]:.2f} w={message["w"]:.3f}',
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
