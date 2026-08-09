#!/usr/bin/env python3
"""
Go2 controller bridge: single node publishing ``unitree_go/WirelessController`` (default ``/wirelesscontroller``).

- **MQTT** (JSON joystick payloads) has priority; each MQTT message is published immediately.
- **REST** (Starlette + OpenAPI): ``POST /wireless`` with the same JSON fields as MQTT; Swagger UI at ``/docs``.
- **REST cmd_vel**: ``POST /cmd_vel`` uses Go2 sport ``Move`` (api_id 1008) with real SI speeds
  ``vx, vy`` in m/s and ``wz`` in rad/s via ``/api/sport/request`` — not WirelessController sticks.
  Optional ``duration``; omit to hold until ``POST /cmd_vel/stop``.
- If no MQTT and no REST update for ``mqtt_timeout_sec``, **Nav2** commands from ``cmd_vel_topic`` are converted
  to ``WirelessController`` and published at ``publish_rate``.
- If there is **no new** MQTT, REST, or ``cmd_vel`` for ``input_idle_timeout_sec``,
  publish an all-zero ``WirelessController`` **once** (safe stop), then pause periodic output
  until new input arrives.

The robot consumes ``/wirelesscontroller`` over DDS (e.g. eth0 via cyclonedds/cyclonedds.go2.xml); there is no
separate Twist mux or topic_tools relay.
"""

import json
import math
import threading
import time

import paho.mqtt.client as mqtt
import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from unitree_api.msg import Request
from unitree_go.msg import WirelessController

CMD_VEL_REPUBLISH_INTERVAL_S = 0.05
SPORT_API_ID_STOPMOVE = 1003
SPORT_API_ID_MOVE = 1008
SPORT_REQUEST_TOPIC = '/api/sport/request'
# Applied to REST /cmd_vel before sport Move: send = command * scale.
DEFAULT_CMD_VEL_SCALE_VX = 0.88
DEFAULT_CMD_VEL_SCALE_VY = 1.4
DEFAULT_CMD_VEL_SCALE_W = 1.25

try:
    import uvicorn
    from starlette.applications import Starlette
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import HTMLResponse, JSONResponse
    from starlette.routing import Route

    _REST_DEPS_AVAILABLE = True
except ImportError:  # pragma: no cover - optional stack on minimal images
    _REST_DEPS_AVAILABLE = False
    uvicorn = None  # type: ignore
    Starlette = None  # type: ignore
    run_in_threadpool = None  # type: ignore
    HTMLResponse = None  # type: ignore
    JSONResponse = None  # type: ignore
    Route = None  # type: ignore


_WIRELESS_BODY_SCHEMA = {
    'type': 'object',
    'properties': {
        'lx': {'type': 'number', 'description': 'Left stick X (strafe)', 'default': 0.0},
        'ly': {'type': 'number', 'description': 'Left stick Y (forward/back)', 'default': 0.0},
        'rx': {'type': 'number', 'description': 'Right stick X (yaw)', 'default': 0.0},
        'ry': {'type': 'number', 'description': 'Right stick Y', 'default': 0.0},
        'keys': {'type': 'integer', 'description': 'Button bitmask', 'default': 0},
    },
}

_CMD_VEL_BODY_SCHEMA = {
    'type': 'object',
    'description': (
        'Go2 sport Move speeds (SI): vx/vy in m/s, w/wz in rad/s. '
        'Published to /api/sport/request (api_id 1008). '
        f'Calibration scales (defaults): vx×{DEFAULT_CMD_VEL_SCALE_VX}, '
        f'vy×{DEFAULT_CMD_VEL_SCALE_VY}, w×{DEFAULT_CMD_VEL_SCALE_W} '
        '(params cmd_vel_scale_vx / cmd_vel_scale_vy / cmd_vel_scale_w). '
        'Optional duration; omit to hold until /cmd_vel/stop.'
    ),
    'properties': {
        'vx': {'type': 'number', 'default': 0.0, 'description': 'Forward velocity (m/s)'},
        'vy': {'type': 'number', 'default': 0.0, 'description': 'Leftward velocity (m/s)'},
        'vz': {'type': 'number', 'default': 0.0, 'description': 'Unused (kept for Twist shape)'},
        'wx': {'type': 'number', 'default': 0.0, 'description': 'Unused (kept for Twist shape)'},
        'wy': {'type': 'number', 'default': 0.0, 'description': 'Unused (kept for Twist shape)'},
        'wz': {'type': 'number', 'default': 0.0, 'description': 'Yaw rate (rad/s)'},
        'w': {'type': 'number', 'default': 0.0, 'description': 'Alias for wz (yaw rate rad/s)'},
        'duration': {
            'type': 'number',
            'description': 'Optional hold time (seconds). Omit to hold until /cmd_vel/stop.',
            'exclusiveMinimum': 0,
        },
    },
}

_OK_RESPONSE = {
    '200': {
        'description': 'Accepted',
        'content': {
            'application/json': {
                'schema': {'type': 'object', 'additionalProperties': True},
            }
        },
    },
    '400': {'description': 'Bad request'},
    '422': {'description': 'Body must be a JSON object'},
}

_REST_OPENAPI_SPEC = {
    'openapi': '3.0.3',
    'info': {
        'title': 'Go2 controller bridge',
        'version': '1.5.0',
        'description': (
            'WirelessController via MQTT/POST /wireless, and speed-based Go2 sport Move '
            'via POST /cmd_vel (vx/vy m/s, w/wz rad/s → /api/sport/request api_id 1008). '
            f'Default calibration: vx×{DEFAULT_CMD_VEL_SCALE_VX}, '
            f'vy×{DEFAULT_CMD_VEL_SCALE_VY}, w×{DEFAULT_CMD_VEL_SCALE_W}. '
            'Change online via GET/POST /calib, POST /calib/vx|vy|w/{scale}.'
        ),
    },
    'tags': [
        {'name': 'WirelessController'},
        {'name': 'cmd_vel'},
        {'name': 'calib'},
        {'name': 'meta'},
    ],
    'paths': {
        '/wireless': {
            'post': {
                'tags': ['WirelessController'],
                'summary': 'Send WirelessController joystick payload',
                'requestBody': {
                    'required': True,
                    'content': {
                        'application/json': {
                            'schema': _WIRELESS_BODY_SCHEMA,
                            'example': {'lx': 0.0, 'ly': 0.2, 'rx': 0.0, 'ry': 0.0, 'keys': 0},
                        }
                    },
                },
                'responses': _OK_RESPONSE,
            }
        },
        '/cmd_vel': {
            'post': {
                'tags': ['cmd_vel'],
                'summary': 'Sport Move: vx/vy (m/s), wz (rad/s)',
                'requestBody': {
                    'required': True,
                    'content': {
                        'application/json': {
                            'schema': _CMD_VEL_BODY_SCHEMA,
                            'example': {
                                'vx': 0.2,
                                'vy': 0.0,
                                'vz': 0.0,
                                'wx': 0.0,
                                'wy': 0.0,
                                'wz': 0.0,
                                'duration': 5.0,
                            },
                        }
                    },
                },
                'responses': _OK_RESPONSE,
            }
        },
        '/cmd_vel/stop': {
            'post': {
                'tags': ['cmd_vel'],
                'summary': 'Sport StopMove (api_id 1003)',
                'responses': _OK_RESPONSE,
            }
        },
        '/calib': {
            'get': {
                'tags': ['calib'],
                'summary': 'Get cmd_vel calibration scales (vx, vy, w)',
                'responses': _OK_RESPONSE,
            },
            'post': {
                'tags': ['calib'],
                'summary': 'Set cmd_vel calibration scales online',
                'requestBody': {
                    'required': True,
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    'vx': {'type': 'number', 'description': 'Forward scale'},
                                    'vy': {'type': 'number', 'description': 'Lateral scale'},
                                    'w': {'type': 'number', 'description': 'Yaw scale'},
                                },
                            },
                            'example': {
                                'vx': DEFAULT_CMD_VEL_SCALE_VX,
                                'vy': DEFAULT_CMD_VEL_SCALE_VY,
                                'w': DEFAULT_CMD_VEL_SCALE_W,
                            },
                        }
                    },
                },
                'responses': _OK_RESPONSE,
            },
        },
        '/calib/vx/{scale}': {
            'post': {
                'tags': ['calib'],
                'summary': 'Set forward (vx) scale online',
                'parameters': [
                    {
                        'name': 'scale',
                        'in': 'path',
                        'required': True,
                        'schema': {'type': 'number'},
                        'example': DEFAULT_CMD_VEL_SCALE_VX,
                    }
                ],
                'responses': _OK_RESPONSE,
            }
        },
        '/calib/vy/{scale}': {
            'post': {
                'tags': ['calib'],
                'summary': 'Set lateral (vy) scale online',
                'parameters': [
                    {
                        'name': 'scale',
                        'in': 'path',
                        'required': True,
                        'schema': {'type': 'number'},
                        'example': DEFAULT_CMD_VEL_SCALE_VY,
                    }
                ],
                'responses': _OK_RESPONSE,
            }
        },
        '/calib/w/{scale}': {
            'post': {
                'tags': ['calib'],
                'summary': 'Set yaw (w) scale online',
                'parameters': [
                    {
                        'name': 'scale',
                        'in': 'path',
                        'required': True,
                        'schema': {'type': 'number'},
                        'example': DEFAULT_CMD_VEL_SCALE_W,
                    }
                ],
                'responses': _OK_RESPONSE,
            }
        },
        '/health': {
            'get': {
                'tags': ['meta'],
                'summary': 'Liveness',
                'responses': {
                    '200': {
                        'description': 'OK',
                        'content': {
                            'application/json': {'schema': {'type': 'object', 'additionalProperties': True}}
                        },
                    },
                },
            }
        },
    },
}

_REST_DOCS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Go2 controller bridge — Swagger</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" crossorigin/>
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js" crossorigin></script>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js" crossorigin></script>
<script>
  window.onload = function () {
    window.ui = SwaggerUIBundle({
      url: '/openapi.json',
      dom_id: '#swagger-ui',
      presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
      layout: 'BaseLayout',
    });
  };
</script>
</body>
</html>
"""


def _wireless_from_mapping(data: dict) -> WirelessController:
    m = WirelessController()
    m.lx = float(data.get('lx', 0.0))
    m.ly = float(data.get('ly', 0.0))
    m.rx = float(data.get('rx', 0.0))
    m.ry = float(data.get('ry', 0.0))
    m.keys = int(data.get('keys', 0))
    return m


def _wireless_from_sequence(seq: list) -> WirelessController:
    m = WirelessController()
    m.lx = float(seq[0])
    m.ly = float(seq[1])
    m.rx = float(seq[2])
    m.ry = float(seq[3])
    m.keys = int(seq[4])
    return m


def _wireless_is_zero(wc: WirelessController) -> bool:
    return (
        wc.lx == 0.0
        and wc.ly == 0.0
        and wc.rx == 0.0
        and wc.ry == 0.0
        and wc.keys == 0
    )


def _twist_is_zero(t: Twist) -> bool:
    return (
        t.linear.x == 0.0
        and t.linear.y == 0.0
        and t.linear.z == 0.0
        and t.angular.x == 0.0
        and t.angular.y == 0.0
        and t.angular.z == 0.0
    )



class Go2ControllerBridge(Node):
    def __init__(self):
        super().__init__('go2_controller_bridge')

        # MQTT
        self.declare_parameter('mqtt_broker', '10.1.106.210')
        self.declare_parameter('mqtt_port', 1883)
        self.declare_parameter('mqtt_topic', '/wirelesscontroller')
        self.declare_parameter('mqtt_client_id', 'go2_controller_bridge')
        self.declare_parameter('mqtt_retry_interval', 5.0)
        self.declare_parameter('mqtt_connect_timeout', 10.0)

        # REST (Starlette + OpenAPI / Swagger UI)
        self.declare_parameter('rest_enable', True)
        self.declare_parameter('rest_host', '0.0.0.0')
        self.declare_parameter('rest_port', 8081)
        self.declare_parameter('log_each_rest_request', True)
        self.declare_parameter('cmd_vel_scale_vx', DEFAULT_CMD_VEL_SCALE_VX)
        self.declare_parameter('cmd_vel_scale_vy', DEFAULT_CMD_VEL_SCALE_VY)
        self.declare_parameter('cmd_vel_scale_w', DEFAULT_CMD_VEL_SCALE_W)

        # ROS I/O
        self.declare_parameter('ros2_topic', '/wirelesscontroller')
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('mqtt_timeout_sec', 1.0)
        self.declare_parameter('publish_rate', 50.0)
        self.declare_parameter('invert_cmd_vel_lateral', True)
        self.declare_parameter('log_each_mqtt_message', True)
        self.declare_parameter('log_each_nav_publish', False)
        self.declare_parameter('log_each_wireless_publish', True)
        self.declare_parameter('input_idle_timeout_sec', 1.0)
        self.declare_parameter('log_idle_zero_publish', False)

        self.mqtt_broker = self.get_parameter('mqtt_broker').get_parameter_value().string_value
        self.mqtt_port = self.get_parameter('mqtt_port').get_parameter_value().integer_value
        self.mqtt_topic = self.get_parameter('mqtt_topic').get_parameter_value().string_value
        mqtt_client_id = self.get_parameter('mqtt_client_id').get_parameter_value().string_value
        self._out_topic = self.get_parameter('ros2_topic').get_parameter_value().string_value
        self._cmd_vel_topic = self.get_parameter('cmd_vel_topic').get_parameter_value().string_value
        self.mqtt_retry_interval = self.get_parameter('mqtt_retry_interval').get_parameter_value().double_value
        self.mqtt_connect_timeout = self.get_parameter('mqtt_connect_timeout').get_parameter_value().double_value
        self._mqtt_timeout_sec = self.get_parameter('mqtt_timeout_sec').get_parameter_value().double_value
        rate_hz = self.get_parameter('publish_rate').get_parameter_value().double_value
        self._invert_lateral = self.get_parameter('invert_cmd_vel_lateral').get_parameter_value().bool_value
        self._log_each_mqtt = self.get_parameter('log_each_mqtt_message').get_parameter_value().bool_value
        self._log_each_nav = self.get_parameter('log_each_nav_publish').get_parameter_value().bool_value
        self._log_wc_publish = self.get_parameter('log_each_wireless_publish').get_parameter_value().bool_value
        self._input_idle_timeout = self.get_parameter('input_idle_timeout_sec').get_parameter_value().double_value
        self._log_idle_zero = self.get_parameter('log_idle_zero_publish').get_parameter_value().bool_value

        self._rest_enable = self.get_parameter('rest_enable').get_parameter_value().bool_value
        self._rest_host = self.get_parameter('rest_host').get_parameter_value().string_value
        self._rest_port = self.get_parameter('rest_port').get_parameter_value().integer_value
        self._log_each_rest = self.get_parameter('log_each_rest_request').get_parameter_value().bool_value
        self._cmd_vel_scale_vx = self.get_parameter(
            'cmd_vel_scale_vx'
        ).get_parameter_value().double_value
        self._cmd_vel_scale_vy = self.get_parameter(
            'cmd_vel_scale_vy'
        ).get_parameter_value().double_value
        self._cmd_vel_scale_w = self.get_parameter(
            'cmd_vel_scale_w'
        ).get_parameter_value().double_value
        self._calib_lock = threading.Lock()

        self._last_mqtt_time = None
        self._last_rest_time = None
        self._last_input_time = self.get_clock().now()
        self._periodic_stop_sent = False
        self._mqtt_wc = WirelessController()
        self._nav_twist = Twist()
        self._move_lock = threading.Lock()
        self._move_stop = threading.Event()
        self._move_thread = None

        self.publisher_ = self.create_publisher(WirelessController, self._out_topic, 10)
        self._sport_pub = self.create_publisher(Request, SPORT_REQUEST_TOPIC, 10)
        self._sport_req_seq = 0
        self.create_subscription(Twist, self._cmd_vel_topic, self._on_cmd_vel, 10)

        period = 1.0 / max(rate_hz, 1.0)
        self.create_timer(period, self._tick_nav_fallback)

        rest_msg = ''
        if self._rest_enable and _REST_DEPS_AVAILABLE:
            self._start_rest_server()
            rest_msg = (
                f' REST: http://{self._rest_host}:{self._rest_port}/wireless '
                f'| /cmd_vel→sport Move '
                f'(Swagger: http://{self._rest_host}:{self._rest_port}/docs)'
            )
        elif self._rest_enable and not _REST_DEPS_AVAILABLE:
            self.get_logger().warn(
                'rest_enable=true but uvicorn/starlette not installed; REST API disabled.'
            )

        self.get_logger().info(
            f'Output WirelessController: {self._out_topic} | MQTT: {self.mqtt_broker}:{self.mqtt_port} '
            f'{self.mqtt_topic} | cmd_vel: {self._cmd_vel_topic} | mqtt_timeout={self._mqtt_timeout_sec}s | '
            f'input_idle_zero={self._input_idle_timeout}s | '
            f'cmd_vel_scale vx×{self._cmd_vel_scale_vx} '
            f'vy×{self._cmd_vel_scale_vy} w×{self._cmd_vel_scale_w}'
            f'{rest_msg}'
        )

        try:
            callback_version = getattr(mqtt.CallbackAPIVersion, 'VERSION2', mqtt.CallbackAPIVersion.VERSION1)
            self.mqtt_client = mqtt.Client(
                callback_api_version=callback_version,
                client_id=mqtt_client_id,
            )
        except AttributeError:
            self.mqtt_client = mqtt.Client(client_id=mqtt_client_id)

        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        self.mqtt_connected = False
        self.mqtt_connecting = False

        self.mqtt_client.loop_start()
        self.connect_mqtt_with_retry()

    @staticmethod
    def _mqtt_topic_str(topic) -> str:
        if topic is None:
            return ''
        if isinstance(topic, bytes):
            return topic.decode('utf-8', errors='replace')
        return str(topic)

    def _wireless_rest_topic_label(self) -> str:
        return f'POST http://{self._rest_host}:{self._rest_port}/wireless'

    def _cancel_timed_move(self) -> None:
        """Stop any in-flight timed sport cmd_vel hold."""
        self._move_stop.set()
        thread = self._move_thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._move_thread = None

    def _next_sport_req_id(self) -> int:
        self._sport_req_seq = (self._sport_req_seq + 1) % (2**62)
        return int(time.time() * 1000) % (10**9) * 1000 + self._sport_req_seq

    def _publish_sport_request(self, api_id: int, parameter: str, noreply: bool = True) -> None:
        req = Request()
        req.header.identity.id = self._next_sport_req_id()
        req.header.identity.api_id = int(api_id)
        req.header.lease.id = 0
        req.header.policy.priority = 0
        req.header.policy.noreply = bool(noreply)
        req.parameter = parameter
        req.binary = []
        self._sport_pub.publish(req)

    def _sport_move(self, vx: float, vy: float, vyaw: float, log: bool = False) -> None:
        """Go2 sport Move (api_id 1008): x/y m/s, z yaw rad/s."""
        self._touch_input_activity()
        self._last_rest_time = self.get_clock().now()
        self._periodic_stop_sent = False
        parameter = json.dumps({'x': float(vx), 'y': float(vy), 'z': float(vyaw)})
        self._publish_sport_request(SPORT_API_ID_MOVE, parameter, noreply=True)
        if log and self._log_each_rest:
            self.get_logger().info(
                f'io input type=rest topic=POST /cmd_vel msg_type=sport/Move | '
                f'output type=unitree_api/msg/Request topic={SPORT_REQUEST_TOPIC} '
                f'api_id={SPORT_API_ID_MOVE} vx={vx:.3f} vy={vy:.3f} wz={vyaw:.3f}'
            )

    def _sport_stop_move(self, log: bool = True) -> None:
        """Go2 sport StopMove (api_id 1003)."""
        self._touch_input_activity()
        self._last_rest_time = self.get_clock().now()
        self._periodic_stop_sent = True
        self._publish_sport_request(SPORT_API_ID_STOPMOVE, '{}', noreply=False)
        if log and self._log_each_rest:
            self.get_logger().info(
                f'io input type=rest topic=POST /cmd_vel/stop msg_type=sport/StopMove | '
                f'output type=unitree_api/msg/Request topic={SPORT_REQUEST_TOPIC} '
                f'api_id={SPORT_API_ID_STOPMOVE}'
            )

    def _rest_parse_and_apply(self, body) -> tuple[bool, str]:
        """Validate JSON body and publish; runs in worker thread (rclpy publish)."""
        if not isinstance(body, dict):
            return False, 'Body must be a JSON object'
        try:
            wc = _wireless_from_mapping(body)
        except (TypeError, ValueError) as e:
            return False, str(e)
        with self._move_lock:
            self._cancel_timed_move()
            self._sport_stop_move(log=False)
            self._on_rest_wireless(wc, source='rest', log=True)
        return True, ''

    def _calibrate_cmd_vel(self, vx: float, vy: float, wz: float) -> tuple[float, float, float]:
        """Apply per-axis calibration scales before sport Move."""
        with self._calib_lock:
            scale_vx = self._cmd_vel_scale_vx
            scale_vy = self._cmd_vel_scale_vy
            scale_w = self._cmd_vel_scale_w
        return (
            float(vx) * scale_vx,
            float(vy) * scale_vy,
            float(wz) * scale_w,
        )

    def _calib_snapshot(self) -> dict:
        with self._calib_lock:
            vx = self._cmd_vel_scale_vx
            vy = self._cmd_vel_scale_vy
            w = self._cmd_vel_scale_w
        return {'ok': True, 'vx': vx, 'vy': vy, 'w': w}

    @staticmethod
    def _parse_scale_value(raw) -> tuple[bool, str, float | None]:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return False, 'scale must be a number', None
        if value != value or value in (float('inf'), float('-inf')):  # NaN / Inf
            return False, 'scale must be finite', None
        return True, '', value

    def _set_calib(
        self,
        vx: float | None = None,
        vy: float | None = None,
        w: float | None = None,
    ) -> tuple[int, dict]:
        if vx is None and vy is None and w is None:
            return 400, {'detail': 'Provide vx and/or vy and/or w'}
        with self._calib_lock:
            if vx is not None:
                self._cmd_vel_scale_vx = float(vx)
            if vy is not None:
                self._cmd_vel_scale_vy = float(vy)
            if w is not None:
                self._cmd_vel_scale_w = float(w)
            cur_vx = self._cmd_vel_scale_vx
            cur_vy = self._cmd_vel_scale_vy
            cur_w = self._cmd_vel_scale_w
        self.get_logger().info(f'calib updated: vx×{cur_vx} vy×{cur_vy} w×{cur_w}')
        return 200, {'ok': True, 'vx': cur_vx, 'vy': cur_vy, 'w': cur_w}

    def _rest_calib_set_body(self, body) -> tuple[int, dict]:
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return 422, {'detail': 'Body must be a JSON object'}
        parsed: dict[str, float | None] = {'vx': None, 'vy': None, 'w': None}
        for key in ('vx', 'vy', 'w'):
            if key not in body or body[key] is None:
                continue
            ok, err, value = self._parse_scale_value(body[key])
            if not ok:
                return 400, {'detail': f'{key}: {err}'}
            parsed[key] = value
        return self._set_calib(vx=parsed['vx'], vy=parsed['vy'], w=parsed['w'])

    def _start_held_sport_move(
        self,
        vx: float,
        vy: float,
        wz: float,
        duration: float | None = None,
    ) -> dict:
        """Republish sport Move until duration elapses (or forever), then StopMove."""
        send_vx, send_vy, send_wz = self._calibrate_cmd_vel(vx, vy, wz)
        with self._calib_lock:
            scale_vx = self._cmd_vel_scale_vx
            scale_vy = self._cmd_vel_scale_vy
            scale_w = self._cmd_vel_scale_w
        calibration = {
            'vx': scale_vx,
            'vy': scale_vy,
            'w': scale_w,
            'sent': {'vx': send_vx, 'vy': send_vy, 'w': send_wz},
        }

        with self._move_lock:
            self._cancel_timed_move()
            if vx == 0.0 and vy == 0.0 and wz == 0.0:
                self._sport_stop_move(log=True)
                return {
                    'ok': True,
                    'held': False,
                    'backend': 'sport_move',
                    'duration': 0.0,
                    'calibration': calibration,
                    'cmd_vel': {
                        'vx': vx,
                        'vy': vy,
                        'w': wz,
                        'vz': 0.0,
                        'wx': 0.0,
                        'wy': 0.0,
                        'wz': wz,
                        'duration': 0.0,
                    },
                }

            self._move_stop.clear()
            self._sport_move(send_vx, send_vy, send_wz, log=True)

            def _hold():
                end = None if duration is None else time.monotonic() + float(duration)
                while not self._move_stop.is_set():
                    if end is not None and time.monotonic() >= end:
                        break
                    self._sport_move(send_vx, send_vy, send_wz, log=False)
                    if end is None:
                        time.sleep(CMD_VEL_REPUBLISH_INTERVAL_S)
                    else:
                        remaining = end - time.monotonic()
                        if remaining <= 0:
                            break
                        time.sleep(min(CMD_VEL_REPUBLISH_INTERVAL_S, remaining))
                if not self._move_stop.is_set():
                    self._sport_stop_move(log=True)

            self._move_thread = threading.Thread(
                target=_hold, name='go2-sport-cmd-vel', daemon=True
            )
            self._move_thread.start()

        return {
            'ok': True,
            'held': True,
            'backend': 'sport_move',
            'duration': duration,
            'calibration': calibration,
            'cmd_vel': {
                'vx': vx,
                'vy': vy,
                'w': wz,
                'vz': 0.0,
                'wx': 0.0,
                'wy': 0.0,
                'wz': wz,
                'duration': duration,
            },
        }

    def _parse_cmd_vel(self, body) -> tuple[bool, str, float, float, float, float | None]:
        """Parse flat vx/vy/w (+ optional duration). Returns (ok, err, vx, vy, wz, duration).

        ``w`` is an alias for ``wz``; if both are present, ``w`` wins.
        """
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return False, 'Body must be a JSON object', 0.0, 0.0, 0.0, None
        try:
            vx = float(body.get('vx', 0.0))
            vy = float(body.get('vy', 0.0))
            if 'w' in body and body['w'] is not None:
                wz = float(body['w'])
            else:
                wz = float(body.get('wz', 0.0))
            duration = None
            if 'duration' in body and body['duration'] is not None:
                duration = float(body['duration'])
                if duration <= 0:
                    return False, 'duration must be > 0', 0.0, 0.0, 0.0, None
        except (TypeError, ValueError) as e:
            return False, str(e), 0.0, 0.0, 0.0, None
        return True, '', vx, vy, wz, duration

    def _rest_cmd_vel(self, body) -> tuple[int, dict]:
        ok, err, vx, vy, wz, duration = self._parse_cmd_vel(body)
        if not ok:
            code = 422 if err.startswith('Body must') else 400
            return code, {'detail': err}
        return 200, self._start_held_sport_move(vx, vy, wz, duration=duration)

    def _rest_cmd_vel_stop(self) -> dict:
        with self._move_lock:
            self._cancel_timed_move()
            self._sport_stop_move(log=True)
        return {'ok': True, 'message': 'stopped', 'backend': 'sport_move'}

    def _start_rest_server(self) -> None:
        bridge = self

        async def openapi_json(_request):
            return JSONResponse(_REST_OPENAPI_SPEC)

        async def docs_page(_request):
            return HTMLResponse(_REST_DOCS_HTML)

        async def health(_request):
            snap = bridge._calib_snapshot()
            return JSONResponse({
                'status': 'ok',
                'node': 'go2_controller_bridge',
                'vx': snap['vx'],
                'vy': snap['vy'],
                'w': snap['w'],
            })

        async def calib_get(_request):
            return JSONResponse(bridge._calib_snapshot())

        async def calib_post(request):
            try:
                body = await request.json()
            except Exception:
                return JSONResponse({'detail': 'Invalid JSON'}, status_code=400)
            code, payload = await run_in_threadpool(bridge._rest_calib_set_body, body)
            return JSONResponse(payload, status_code=code)

        async def calib_vx_post(request):
            ok, err, value = bridge._parse_scale_value(request.path_params.get('scale'))
            if not ok:
                return JSONResponse({'detail': err}, status_code=400)
            code, payload = await run_in_threadpool(
                bridge._set_calib, value, None, None
            )
            return JSONResponse(payload, status_code=code)

        async def calib_vy_post(request):
            ok, err, value = bridge._parse_scale_value(request.path_params.get('scale'))
            if not ok:
                return JSONResponse({'detail': err}, status_code=400)
            code, payload = await run_in_threadpool(
                bridge._set_calib, None, value, None
            )
            return JSONResponse(payload, status_code=code)

        async def calib_w_post(request):
            ok, err, value = bridge._parse_scale_value(request.path_params.get('scale'))
            if not ok:
                return JSONResponse({'detail': err}, status_code=400)
            code, payload = await run_in_threadpool(
                bridge._set_calib, None, None, value
            )
            return JSONResponse(payload, status_code=code)

        async def wireless_post(request):
            try:
                body = await request.json()
            except Exception:
                return JSONResponse({'detail': 'Invalid JSON'}, status_code=400)
            ok, err = await run_in_threadpool(bridge._rest_parse_and_apply, body)
            if ok:
                return JSONResponse({'ok': True})
            code = 422 if err.startswith('Body must') else 400
            return JSONResponse({'detail': err}, status_code=code)

        async def cmd_vel_post(request):
            try:
                body = await request.json()
            except Exception:
                return JSONResponse({'detail': 'Invalid JSON'}, status_code=400)
            code, payload = await run_in_threadpool(bridge._rest_cmd_vel, body)
            return JSONResponse(payload, status_code=code)

        async def cmd_vel_stop_post(_request):
            payload = await run_in_threadpool(bridge._rest_cmd_vel_stop)
            return JSONResponse(payload)

        app = Starlette(
            routes=[
                Route('/openapi.json', openapi_json, methods=['GET']),
                Route('/docs', docs_page, methods=['GET']),
                Route('/health', health, methods=['GET']),
                Route('/calib', calib_get, methods=['GET']),
                Route('/calib', calib_post, methods=['POST']),
                Route('/calib/vx/{scale}', calib_vx_post, methods=['POST']),
                Route('/calib/vy/{scale}', calib_vy_post, methods=['POST']),
                Route('/calib/w/{scale}', calib_w_post, methods=['POST']),
                Route('/wireless', wireless_post, methods=['POST']),
                Route('/cmd_vel', cmd_vel_post, methods=['POST']),
                Route('/cmd_vel/stop', cmd_vel_stop_post, methods=['POST']),
            ],
        )

        def _run():
            config = uvicorn.Config(
                app,
                host=bridge._rest_host,
                port=int(bridge._rest_port),
                log_level='warning',
            )
            uvicorn.Server(config).run()

        self._rest_thread = threading.Thread(target=_run, name='go2-rest-api', daemon=True)
        self._rest_thread.start()

    def _on_rest_wireless(
        self,
        wc: WirelessController,
        source: str = 'rest',
        log: bool = True,
    ) -> None:
        self._touch_input_activity()
        self._last_rest_time = self.get_clock().now()
        if _wireless_is_zero(wc):
            self._periodic_stop_sent = True
        else:
            self._periodic_stop_sent = False
        if log and self._log_each_rest:
            self._log_io(
                input_kind='rest',
                input_topic=self._wireless_rest_topic_label(),
                input_msg_type='application/json',
                wc=wc,
            )
        self._publish_wireless(wc, source=source)

    def _log_io(
        self,
        *,
        input_kind: str,
        input_topic: str,
        input_msg_type: str,
        wc: WirelessController,
    ) -> None:
        """Structured log: input (transport, topic, ROS/MQTT message type) → WirelessController."""
        self.get_logger().info(
            f'io input type={input_kind} topic={input_topic} msg_type={input_msg_type} | '
            f'output type=unitree_go/msg/WirelessController topic={self._out_topic} '
            f'lx={wc.lx:.3f} ly={wc.ly:.3f} rx={wc.rx:.3f} ry={wc.ry:.3f} keys={wc.keys}'
        )

    def _publish_wireless(self, wc: WirelessController, source: str) -> None:
        """Publish WirelessController and optionally log published message."""
        self.publisher_.publish(wc)
        hide_idle = source == 'input_idle_timeout' and not self._log_idle_zero
        if self._log_wc_publish and not hide_idle:
            self.get_logger().info(
                f'WirelessController publish topic={self._out_topic} '
                f'type=unitree_go/msg/WirelessController source={source} '
                f'lx={wc.lx:.3f} ly={wc.ly:.3f} rx={wc.rx:.3f} ry={wc.ry:.3f} keys={wc.keys}'
            )

    def _touch_input_activity(self) -> None:
        self._last_input_time = self.get_clock().now()

    def _non_nav_input_fresh(self, now) -> bool:
        """True if a recent MQTT or REST wireless-style update should block cmd_vel fallback."""
        if self._last_mqtt_time is not None:
            dt_mqtt = (now - self._last_mqtt_time).nanoseconds * 1e-9
            if dt_mqtt < self._mqtt_timeout_sec:
                return True
        if self._last_rest_time is not None:
            dt_rest = (now - self._last_rest_time).nanoseconds * 1e-9
            if dt_rest < self._mqtt_timeout_sec:
                return True
        return False

    def connect_mqtt_with_retry(self):
        if hasattr(self, '_mqtt_retry_timer'):
            try:
                self._mqtt_retry_timer.cancel()
            except Exception:
                pass
        self._mqtt_retry_timer = self.create_timer(self.mqtt_retry_interval, self._attempt_mqtt_connection)
        self._attempt_mqtt_connection()

    def _attempt_mqtt_connection(self):
        if self.mqtt_connected:
            if hasattr(self, '_mqtt_retry_timer'):
                self._mqtt_retry_timer.cancel()
            return
        if self.mqtt_connecting:
            return
        self.mqtt_connecting = True
        try:
            try:
                self.mqtt_client.disconnect()
            except Exception:
                pass
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, int(self.mqtt_connect_timeout))
        except (ConnectionRefusedError, OSError):
            self.mqtt_connecting = False
            self.get_logger().warn(
                f'MQTT connection refused {self.mqtt_broker}:{self.mqtt_port}; retry in {self.mqtt_retry_interval}s'
            )
        except Exception as e:
            self.mqtt_connecting = False
            self.get_logger().warn(f'MQTT connect error: {e}; retry in {self.mqtt_retry_interval}s')

    def on_mqtt_connect(self, client, userdata, flags, rc, *args):
        self.mqtt_connecting = False
        if rc == 0:
            self.mqtt_connected = True
            if hasattr(self, '_mqtt_retry_timer'):
                self._mqtt_retry_timer.cancel()
            client.subscribe(self.mqtt_topic)
            self.get_logger().info(f'MQTT connected; subscribed to {self.mqtt_topic}')
        else:
            self.mqtt_connected = False
            self.get_logger().error(f'MQTT connect failed rc={rc}')

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode('utf-8')
            data = json.loads(payload)
            if isinstance(data, dict):
                ros2_msg = _wireless_from_mapping(data)
            elif isinstance(data, list) and len(data) >= 5:
                ros2_msg = _wireless_from_sequence(data)
            else:
                self.get_logger().warn(f'Unexpected MQTT payload: {payload}')
                return

            self._mqtt_wc = ros2_msg
            with self._move_lock:
                self._cancel_timed_move()
                self._sport_stop_move(log=False)
            self._touch_input_activity()
            self._last_mqtt_time = self.get_clock().now()
            if _wireless_is_zero(ros2_msg):
                self._periodic_stop_sent = True
            else:
                self._periodic_stop_sent = False
            if self._log_each_mqtt:
                mt = self._mqtt_topic_str(getattr(msg, 'topic', self.mqtt_topic))
                self._log_io(
                    input_kind='mqtt',
                    input_topic=mt or self.mqtt_topic,
                    input_msg_type='application/json',
                    wc=ros2_msg,
                )
            self._publish_wireless(ros2_msg, source='mqtt')
        except json.JSONDecodeError as e:
            self.get_logger().error(f'MQTT JSON error: {e}')
        except (KeyError, ValueError, TypeError) as e:
            self.get_logger().error(f'MQTT parse error: {e}')
        except Exception as e:
            self.get_logger().error(f'MQTT handler error: {e}')

    def on_mqtt_disconnect(self, client, userdata, rc, *args):
        self.mqtt_connected = False
        self.mqtt_connecting = False
        if rc != 0:
            self.get_logger().warn('MQTT disconnected; reconnecting...')
            self.connect_mqtt_with_retry()

    def _on_cmd_vel(self, msg: Twist):
        self._touch_input_activity()
        self._nav_twist = msg
        if not _twist_is_zero(msg):
            self._periodic_stop_sent = False

    def _twist_to_wireless(self, t: Twist) -> WirelessController:
        m = WirelessController()
        m.ly = float(t.linear.x)
        m.lx = float(-t.linear.y) if self._invert_lateral else float(t.linear.y)
        # Go2 control convention is opposite sign from ROS angular.z for yaw.
        m.rx = float(-t.angular.z)
        m.ry = 0.0
        m.keys = 0
        return m

    def _tick_nav_fallback(self):
        """Idle → one zero then pause; else forward Nav cmd_vel (zero cmd_vel also once then pause)."""
        if self._periodic_stop_sent:
            return

        now = self.get_clock().now()
        idle_sec = (now - self._last_input_time).nanoseconds * 1e-9
        if self._input_idle_timeout > 0.0 and idle_sec >= self._input_idle_timeout:
            self._publish_wireless(WirelessController(), source='input_idle_timeout')
            self._periodic_stop_sent = True
            return

        if self._non_nav_input_fresh(now):
            return

        wc = self._twist_to_wireless(self._nav_twist)
        if not (
            math.isfinite(wc.lx)
            and math.isfinite(wc.ly)
            and math.isfinite(wc.rx)
            and math.isfinite(wc.ry)
        ):
            return

        if _wireless_is_zero(wc):
            if self._log_each_nav:
                self._log_io(
                    input_kind='ros',
                    input_topic=self._cmd_vel_topic,
                    input_msg_type='geometry_msgs/msg/Twist',
                    wc=wc,
                )
            self._publish_wireless(wc, source='nav/cmd_vel')
            self._periodic_stop_sent = True
            return

        if self._log_each_nav:
            self._log_io(
                input_kind='ros',
                input_topic=self._cmd_vel_topic,
                input_msg_type='geometry_msgs/msg/Twist',
                wc=wc,
            )
        self._publish_wireless(wc, source='nav/cmd_vel')

    def destroy_node(self):
        try:
            with self._move_lock:
                self._cancel_timed_move()
                self._sport_stop_move(log=False)
        except Exception:
            pass
        try:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        except Exception:
            pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = Go2ControllerBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
