#!/usr/bin/env python3
"""
Go2 controller bridge: operator API is HTTP REST (``:8081``). The dog still consumes
DDS ``/wirelesscontroller`` and ``/api/sport/request``.

Priority REST → MQTT → Nav. Higher source applies immediately and **drops** lower
msgs (MQTT ignored; Nav ``/cmd_vel`` not published). Lower source may apply only
after ``mqtt_timeout_sec`` (default 1 s) with no msgs from all higher sources.
- If there is **no new** REST, MQTT, or ``cmd_vel`` for ``input_idle_timeout_sec``,
  publish an all-zero ``WirelessController`` **once** (safe stop), then pause periodic output
  until new input arrives.
"""

import json
import math
import threading
import time

import paho.mqtt.client as mqtt
import rclpy
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped, Twist
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.node import Node
from tf2_ros import Buffer, TransformException, TransformListener
from unitree_api.msg import Request
from unitree_go.msg import WirelessController

try:
    from nav2_msgs.action import NavigateToPose
    from nav2_msgs.srv import ClearEntireCostmap

    _NAV2_AVAILABLE = True
except ImportError:  # pragma: no cover - minimal controller-only installs
    NavigateToPose = None
    ClearEntireCostmap = None
    _NAV2_AVAILABLE = False

CMD_VEL_REPUBLISH_INTERVAL_S = 0.05
SPORT_API_ID_STOPMOVE = 1003
SPORT_API_ID_MOVE = 1008
SPORT_REQUEST_TOPIC = '/api/sport/request'
NAV2_ACTION_NAME = 'navigate_to_pose'
DEFAULT_POSE_FRAME = 'map'
DEFAULT_BASE_FRAME = 'base_link'
DEFAULT_INITIALPOSE_TOPIC = '/initialpose'
DEFAULT_CLEAR_LOCAL_COSTMAP_SERVICE = '/local_costmap/clear_entirely_local_costmap'
# vlaa app_go2 calib: stick/sport send = command * scale (same numbers both paths).
# Yaw: vlaa GO2_MAX_YAW=2.094 → scale = 1/max (rx = wz * scale), not a max param.
DEFAULT_CMD_VEL_SCALE_VX = 0.65
DEFAULT_CMD_VEL_SCALE_VY = 1.65
DEFAULT_CMD_VEL_SCALE_W = 1.0 / 2.094

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
            'Operator API is HTTP. POST /wireless → /wirelesscontroller; '
            'POST /cmd_vel → sport Move (vx/vy m/s, w/wz rad/s, api_id 1008). '
            f'Default calibration: vx×{DEFAULT_CMD_VEL_SCALE_VX}, '
            f'vy×{DEFAULT_CMD_VEL_SCALE_VY}, w×{DEFAULT_CMD_VEL_SCALE_W}. '
            'Change online via GET/POST /calib, POST /calib/vx|vy|w/{scale}. '
            'Priority REST > MQTT > Nav. Full docs: docs/go2_controller.md.'
        ),
    },
    'tags': [
        {'name': 'WirelessController'},
        {'name': 'cmd_vel'},
        {'name': 'calib'},
        {'name': 'meta'},
        {'name': 'nav2'},
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
        '/nav2/status': {
            'get': {
                'tags': ['nav2'],
                'summary': 'Get Nav2 NavigateToPose status',
                'responses': _OK_RESPONSE,
            }
        },
        '/nav2/goal': {
            'get': {
                'tags': ['nav2'],
                'summary': 'Get the current Nav2 goal and status',
                'responses': _OK_RESPONSE,
            },
            'post': {
                'tags': ['nav2'],
                'summary': 'Send a goal to Nav2 NavigateToPose (replaces any active goal)',
                'requestBody': {
                    'required': True,
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'required': ['x', 'y'],
                                'properties': {
                                    'x': {'type': 'number'},
                                    'y': {'type': 'number'},
                                    'yaw': {'type': 'number', 'default': 0.0},
                                    'frame_id': {'type': 'string', 'default': 'map'},
                                },
                            },
                            'example': {
                                'x': -0.05047607421875,
                                'y': 2.0018317699432373,
                                'yaw': -0.5609602627,
                                'frame_id': 'map',
                            },
                        }
                    },
                },
                'responses': _OK_RESPONSE,
            }
        },
        '/nav2/cancel': {
            'post': {
                'tags': ['nav2'],
                'summary': 'Cancel the active Nav2 goal',
                'responses': _OK_RESPONSE,
            }
        },
        '/nav2/pose': {
            'get': {
                'tags': ['nav2'],
                'summary': 'Get current robot pose (TF map→base_link)',
                'responses': _OK_RESPONSE,
            },
            'post': {
                'tags': ['nav2'],
                'summary': 'Set localization pose via /initialpose',
                'requestBody': {
                    'required': True,
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'required': ['x', 'y'],
                                'properties': {
                                    'x': {'type': 'number'},
                                    'y': {'type': 'number'},
                                    'yaw': {'type': 'number', 'default': 0.0},
                                    'frame_id': {'type': 'string', 'default': 'map'},
                                },
                            },
                            'example': {
                                'x': -0.05047607421875,
                                'y': 2.0018317699432373,
                                'yaw': -0.5609602627,
                                'frame_id': 'map',
                            },
                        }
                    },
                },
                'responses': _OK_RESPONSE,
            },
        },
        '/nav2/clear_local_costmap': {
            'post': {
                'tags': ['nav2'],
                'summary': 'Clear the entire local costmap',
                'responses': _OK_RESPONSE,
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
        self.declare_parameter('pose_frame', DEFAULT_POSE_FRAME)
        self.declare_parameter('base_frame', DEFAULT_BASE_FRAME)
        self.declare_parameter('initialpose_topic', DEFAULT_INITIALPOSE_TOPIC)
        self.declare_parameter(
            'clear_local_costmap_service', DEFAULT_CLEAR_LOCAL_COSTMAP_SERVICE
        )

        # ROS I/O
        self.declare_parameter('ros2_topic', '/wirelesscontroller')
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('mqtt_timeout_sec', 1.0)  # hold: no higher-priority msg for this long
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
        self._preempt_hold_sec = self.get_parameter('mqtt_timeout_sec').get_parameter_value().double_value
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
        self._pose_frame = self.get_parameter('pose_frame').get_parameter_value().string_value
        self._base_frame = self.get_parameter('base_frame').get_parameter_value().string_value
        self._initialpose_topic = self.get_parameter(
            'initialpose_topic'
        ).get_parameter_value().string_value
        self._clear_local_costmap_service = self.get_parameter(
            'clear_local_costmap_service'
        ).get_parameter_value().string_value
        self._calib_lock = threading.Lock()

        self._last_mqtt_time = None
        self._last_rest_time = None
        self._last_nav_time = None
        self._last_input_time = self.get_clock().now()
        self._periodic_stop_sent = False
        self._mqtt_wc = WirelessController()
        self._rest_wc = None
        self._nav_twist = Twist()
        self._move_lock = threading.Lock()
        self._move_stop = threading.Event()
        self._move_thread = None
        self._nav2_lock = threading.Lock()
        self._nav2_goal_handle = None
        self._nav2_goal_payload = None
        self._nav2_feedback = {}
        self._nav2_status = 'idle'
        self._nav2_result = None
        self._nav2_goal_token = 0
        self._nav2_action_client = (
            ActionClient(self, NavigateToPose, NAV2_ACTION_NAME)
            if _NAV2_AVAILABLE else None
        )
        self._clear_local_costmap_client = (
            self.create_client(ClearEntireCostmap, self._clear_local_costmap_service)
            if _NAV2_AVAILABLE else None
        )
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)

        self.publisher_ = self.create_publisher(WirelessController, self._out_topic, 10)
        self._sport_pub = self.create_publisher(Request, SPORT_REQUEST_TOPIC, 10)
        self._initialpose_pub = self.create_publisher(
            PoseWithCovarianceStamped, self._initialpose_topic, 10
        )
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
            f'{self.mqtt_topic} | cmd_vel: {self._cmd_vel_topic} | '
            f'priority rest>mqtt>nav hold={self._preempt_hold_sec}s | '
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

    def _preempt_sport_hold_locked(self) -> None:
        """Caller holds ``_move_lock``. StopMove only if a REST sport hold is running."""
        active = self._move_thread is not None and self._move_thread.is_alive()
        if not active:
            return
        self._cancel_timed_move()
        self._sport_stop_move(log=False, as_rest=False)

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

    def _sport_stop_move(self, log: bool = True, as_rest: bool = True) -> None:
        """Go2 sport StopMove (api_id 1003)."""
        self._touch_input_activity()
        if as_rest:
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
        blocked = self._blocked_by_higher('rest')
        if blocked:
            return False, blocked
        try:
            wc = _wireless_from_mapping(body)
        except (TypeError, ValueError) as e:
            return False, str(e)
        with self._move_lock:
            self._preempt_sport_hold_locked()
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
        blocked = self._blocked_by_higher('rest')
        if blocked:
            return 409, {'detail': blocked}
        ok, err, vx, vy, wz, duration = self._parse_cmd_vel(body)
        if not ok:
            code = 422 if err.startswith('Body must') else 400
            return code, {'detail': err}
        return 200, self._start_held_sport_move(vx, vy, wz, duration=duration)

    def _rest_cmd_vel_stop(self) -> tuple[int, dict]:
        blocked = self._blocked_by_higher('rest')
        if blocked:
            return 409, {'detail': blocked}
        with self._move_lock:
            self._cancel_timed_move()
            self._sport_stop_move(log=True)
        return 200, {'ok': True, 'message': 'stopped', 'backend': 'sport_move'}

    def _nav2_snapshot(self) -> dict:
        with self._nav2_lock:
            return {
                'ok': _NAV2_AVAILABLE,
                'action': NAV2_ACTION_NAME,
                'status': self._nav2_status,
                'goal': self._nav2_goal_payload,
                'feedback': dict(self._nav2_feedback),
                'result': self._nav2_result,
            }

    def _on_nav2_feedback(self, feedback_msg) -> None:
        feedback = feedback_msg.feedback
        current_pose = feedback.current_pose
        with self._nav2_lock:
            self._nav2_feedback = {
                'current_pose': {
                    'frame_id': current_pose.header.frame_id,
                    'x': current_pose.pose.position.x,
                    'y': current_pose.pose.position.y,
                },
                'distance_remaining': feedback.distance_remaining,
                'number_of_recoveries': feedback.number_of_recoveries,
            }

    def _on_nav2_goal_response(self, future, goal_token: int) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:
            with self._nav2_lock:
                if goal_token != self._nav2_goal_token:
                    return
                self._nav2_status = 'error'
                self._nav2_result = {'message': str(exc)}
            return
        with self._nav2_lock:
            if goal_token != self._nav2_goal_token:
                # A newer goal replaced this one; cancel the stale handle.
                if goal_handle is not None and goal_handle.accepted:
                    goal_handle.cancel_goal_async()
                return
            if not goal_handle.accepted:
                self._nav2_status = 'rejected'
                self._nav2_result = {'message': 'Nav2 rejected the goal'}
                return
            cancel_requested = self._nav2_status == 'canceling'
            self._nav2_goal_handle = goal_handle
            self._nav2_status = 'canceling' if cancel_requested else 'executing'
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda f, token=goal_token: self._on_nav2_result(f, token)
        )
        if cancel_requested:
            goal_handle.cancel_goal_async()

    def _on_nav2_result(self, future, goal_token: int) -> None:
        try:
            result = future.result()
            status = int(result.status)
            result_code = 0
            message = 'Nav2 action completed'
        except Exception as exc:
            status = -1
            result_code = -1
            message = str(exc)
        status_names = {
            4: 'succeeded',
            5: 'canceled',
            6: 'aborted',
        }
        with self._nav2_lock:
            if goal_token != self._nav2_goal_token:
                return
            self._nav2_status = status_names.get(status, 'finished')
            self._nav2_result = {
                'status_code': status,
                'error_code': result_code,
                'message': message,
            }
            self._nav2_goal_handle = None

    def _nav2_cancel_active_locked(self) -> None:
        """Caller holds ``_nav2_lock``. Cancel current Nav2 goal if any."""
        goal_handle = self._nav2_goal_handle
        if self._nav2_status in ('waiting', 'executing', 'canceling'):
            self._nav2_status = 'canceling'
        self._nav2_goal_handle = None
        if goal_handle is not None:
            try:
                goal_handle.cancel_goal_async()
            except Exception:
                pass

    def _nav2_send_goal(self, body) -> tuple[int, dict]:
        if not _NAV2_AVAILABLE or self._nav2_action_client is None:
            return 503, {'detail': 'nav2_msgs/NavigateToPose is not available'}
        if not isinstance(body, dict):
            return 422, {'detail': 'Body must be a JSON object'}
        try:
            x = float(body['x'])
            y = float(body['y'])
            yaw = float(body.get('yaw', 0.0))
            frame_id = str(body.get('frame_id', 'map'))
        except (KeyError, TypeError, ValueError) as exc:
            return 400, {'detail': f'Invalid goal: {exc}'}
        if not self._nav2_action_client.wait_for_server(timeout_sec=0.5):
            return 503, {'detail': f'Nav2 action server unavailable: {NAV2_ACTION_NAME}'}

        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.header.frame_id = frame_id
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
        payload = {'x': x, 'y': y, 'yaw': yaw, 'frame_id': frame_id}
        with self._nav2_lock:
            replaced = self._nav2_status in ('waiting', 'executing', 'canceling')
            self._nav2_cancel_active_locked()
            self._nav2_goal_token += 1
            goal_token = self._nav2_goal_token
            self._nav2_goal_payload = payload
            self._nav2_feedback = {}
            self._nav2_result = None
            self._nav2_status = 'waiting'
        send_future = self._nav2_action_client.send_goal_async(
            goal, feedback_callback=self._on_nav2_feedback
        )
        send_future.add_done_callback(
            lambda f, token=goal_token: self._on_nav2_goal_response(f, token)
        )
        return 200, {
            'ok': True,
            'status': 'waiting',
            'replaced': replaced,
            'goal': payload,
        }

    def _nav2_cancel(self) -> tuple[int, dict]:
        with self._nav2_lock:
            active = self._nav2_status in ('waiting', 'executing', 'canceling')
            if not active:
                return 404, {'detail': 'No active Nav2 goal'}
            self._nav2_cancel_active_locked()
            self._nav2_goal_token += 1
        return 200, {'ok': True, 'status': 'canceling'}

    @staticmethod
    def _yaw_from_quat(z: float, w: float) -> float:
        return 2.0 * math.atan2(float(z), float(w))

    @staticmethod
    def _quat_from_yaw(yaw: float) -> tuple[float, float, float, float]:
        half = 0.5 * float(yaw)
        return 0.0, 0.0, math.sin(half), math.cos(half)

    def _nav2_get_pose(self) -> tuple[int, dict]:
        try:
            tf = self._tf_buffer.lookup_transform(
                self._pose_frame,
                self._base_frame,
                rclpy.time.Time(),
                timeout=Duration(seconds=0.5),
            )
        except TransformException as exc:
            return 503, {
                'detail': (
                    f'TF unavailable ({self._pose_frame} → {self._base_frame}): {exc}'
                ),
            }
        t = tf.transform.translation
        q = tf.transform.rotation
        yaw = self._yaw_from_quat(q.z, q.w)
        return 200, {
            'ok': True,
            'frame_id': self._pose_frame,
            'base_frame': self._base_frame,
            'x': float(t.x),
            'y': float(t.y),
            'z': float(t.z),
            'yaw': float(yaw),
            'orientation': {
                'x': float(q.x),
                'y': float(q.y),
                'z': float(q.z),
                'w': float(q.w),
            },
        }

    def _nav2_set_pose(self, body) -> tuple[int, dict]:
        if not isinstance(body, dict):
            return 422, {'detail': 'Body must be a JSON object'}
        try:
            x = float(body['x'])
            y = float(body['y'])
            yaw = float(body.get('yaw', 0.0))
            frame_id = str(body.get('frame_id', self._pose_frame) or self._pose_frame)
        except (KeyError, TypeError, ValueError) as exc:
            return 400, {'detail': f'Invalid pose: {exc}'}

        msg = PoseWithCovarianceStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = frame_id
        msg.pose.pose.position.x = x
        msg.pose.pose.position.y = y
        msg.pose.pose.position.z = 0.0
        qx, qy, qz, qw = self._quat_from_yaw(yaw)
        msg.pose.pose.orientation.x = qx
        msg.pose.pose.orientation.y = qy
        msg.pose.pose.orientation.z = qz
        msg.pose.pose.orientation.w = qw
        # Modest XY/yaw covariance so RTAB-Map/AMCL accepts the estimate.
        msg.pose.covariance[0] = 0.25
        msg.pose.covariance[7] = 0.25
        msg.pose.covariance[35] = 0.06853891945200942  # (15 deg)^2

        self._initialpose_pub.publish(msg)
        if self._log_each_rest:
            self.get_logger().info(
                f'io input type=rest topic=POST /nav2/pose | '
                f'output type=geometry_msgs/PoseWithCovarianceStamped '
                f'topic={self._initialpose_topic} '
                f'x={x:.3f} y={y:.3f} yaw={yaw:.3f} frame_id={frame_id}'
            )
        return 200, {
            'ok': True,
            'topic': self._initialpose_topic,
            'pose': {'x': x, 'y': y, 'yaw': yaw, 'frame_id': frame_id},
        }

    def _nav2_clear_local_costmap(self) -> tuple[int, dict]:
        if not _NAV2_AVAILABLE or self._clear_local_costmap_client is None:
            return 503, {'detail': 'nav2_msgs/ClearEntireCostmap is not available'}
        if not self._clear_local_costmap_client.wait_for_service(timeout_sec=1.0):
            return 503, {
                'detail': (
                    f'Clear local costmap service unavailable: '
                    f'{self._clear_local_costmap_service}'
                ),
            }
        future = self._clear_local_costmap_client.call_async(ClearEntireCostmap.Request())
        deadline = time.time() + 2.0
        while rclpy.ok() and not future.done() and time.time() < deadline:
            time.sleep(0.02)
        if not future.done():
            return 504, {'detail': 'Timed out clearing local costmap'}
        try:
            future.result()
        except Exception as exc:
            return 500, {'detail': f'Clear local costmap failed: {exc}'}
        if self._log_each_rest:
            self.get_logger().info(
                f'io input type=rest topic=POST /nav2/clear_local_costmap | '
                f'cleared service={self._clear_local_costmap_service}'
            )
        return 200, {
            'ok': True,
            'service': self._clear_local_costmap_service,
            'message': 'local costmap cleared',
        }

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
            if err.startswith('blocked by'):
                return JSONResponse({'detail': err}, status_code=409)
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
            code, payload = await run_in_threadpool(bridge._rest_cmd_vel_stop)
            return JSONResponse(payload, status_code=code)

        async def nav2_status(_request):
            return JSONResponse(bridge._nav2_snapshot())

        async def nav2_goal_get(_request):
            return JSONResponse(bridge._nav2_snapshot())

        async def nav2_goal(request):
            try:
                body = await request.json()
            except Exception:
                return JSONResponse({'detail': 'Invalid JSON'}, status_code=400)
            code, payload = await run_in_threadpool(bridge._nav2_send_goal, body)
            return JSONResponse(payload, status_code=code)

        async def nav2_cancel(_request):
            code, payload = await run_in_threadpool(bridge._nav2_cancel)
            return JSONResponse(payload, status_code=code)

        async def nav2_pose_get(_request):
            code, payload = await run_in_threadpool(bridge._nav2_get_pose)
            return JSONResponse(payload, status_code=code)

        async def nav2_pose_post(request):
            try:
                body = await request.json()
            except Exception:
                return JSONResponse({'detail': 'Invalid JSON'}, status_code=400)
            code, payload = await run_in_threadpool(bridge._nav2_set_pose, body)
            return JSONResponse(payload, status_code=code)

        async def nav2_clear_local_costmap(_request):
            code, payload = await run_in_threadpool(bridge._nav2_clear_local_costmap)
            return JSONResponse(payload, status_code=code)

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
                Route('/nav2/status', nav2_status, methods=['GET']),
                Route('/nav2/goal', nav2_goal_get, methods=['GET']),
                Route('/nav2/goal', nav2_goal, methods=['POST']),
                Route('/nav2/cancel', nav2_cancel, methods=['POST']),
                Route('/nav2/pose', nav2_pose_get, methods=['GET']),
                Route('/nav2/pose', nav2_pose_post, methods=['POST']),
                Route(
                    '/nav2/clear_local_costmap',
                    nav2_clear_local_costmap,
                    methods=['POST'],
                ),
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
        self._rest_wc = wc
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
        hide_hold = source.endswith('_hold')
        if self._log_wc_publish and not hide_idle and not hide_hold:
            self.get_logger().info(
                f'WirelessController publish topic={self._out_topic} '
                f'type=unitree_go/msg/WirelessController source={source} '
                f'lx={wc.lx:.3f} ly={wc.ly:.3f} rx={wc.rx:.3f} ry={wc.ry:.3f} keys={wc.keys}'
            )

    def _touch_input_activity(self) -> None:
        self._last_input_time = self.get_clock().now()

    def _age_sec(self, stamp) -> float | None:
        if stamp is None:
            return None
        return (self.get_clock().now() - stamp).nanoseconds * 1e-9

    def _source_active(self, stamp) -> bool:
        age = self._age_sec(stamp)
        return age is not None and age < self._preempt_hold_sec

    def _blocked_by_higher(self, source: str) -> str | None:
        """If a higher-priority source sent a msg within hold window, return why."""
        if source == 'rest':
            return None
        if self._source_active(self._last_rest_time):
            return (
                f'blocked by rest; wait {self._preempt_hold_sec:.1f}s after last REST message'
            )
        if source == 'mqtt':
            return None
        if self._source_active(self._last_mqtt_time):
            return (
                f'blocked by mqtt; wait {self._preempt_hold_sec:.1f}s after last MQTT message'
            )
        return None

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

            blocked = self._blocked_by_higher('mqtt')
            if blocked:
                return
            self._mqtt_wc = ros2_msg
            with self._move_lock:
                self._preempt_sport_hold_locked()
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
        self._nav_twist = msg
        self._last_nav_time = self.get_clock().now()
        if self._blocked_by_higher('nav'):
            return
        self._touch_input_activity()
        if not _twist_is_zero(msg):
            self._periodic_stop_sent = False

    def _twist_to_wireless(self, t: Twist) -> WirelessController:
        # ly = vx * scale_vx, lx = vy * scale_vy, rx = wz * scale_w (w = 1/2.094).
        vx = float(t.linear.x)
        vy = float(-t.linear.y) if self._invert_lateral else float(t.linear.y)
        wz = float(-t.angular.z)
        m = WirelessController()
        m.ly = vx * self._cmd_vel_scale_vx
        m.lx = vy * self._cmd_vel_scale_vy
        m.rx = wz * self._cmd_vel_scale_w
        m.ry = 0.0
        m.keys = 0
        return m

    def _tick_nav_fallback(self):
        """Hold last REST/MQTT sticks while they own the bus; else Nav or one idle zero."""
        if self._source_active(self._last_rest_time):
            if self._rest_wc is not None:
                self._publish_wireless(self._rest_wc, source='rest_hold')
            return
        if self._source_active(self._last_mqtt_time):
            self._publish_wireless(self._mqtt_wc, source='mqtt_hold')
            return
        if self._blocked_by_higher('nav'):
            return

        nav_age = self._age_sec(self._last_nav_time)
        nav_fresh = nav_age is not None and (
            self._input_idle_timeout <= 0.0 or nav_age < self._input_idle_timeout
        )
        if nav_fresh:
            wc = self._twist_to_wireless(self._nav_twist)
            if not (
                math.isfinite(wc.lx)
                and math.isfinite(wc.ly)
                and math.isfinite(wc.rx)
                and math.isfinite(wc.ry)
            ):
                return
            if _wireless_is_zero(wc):
                if self._periodic_stop_sent:
                    return
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
            self._periodic_stop_sent = False
            if self._log_each_nav:
                self._log_io(
                    input_kind='ros',
                    input_topic=self._cmd_vel_topic,
                    input_msg_type='geometry_msgs/msg/Twist',
                    wc=wc,
                )
            self._publish_wireless(wc, source='nav/cmd_vel')
            return

        if self._periodic_stop_sent:
            return
        now = self.get_clock().now()
        idle_sec = (now - self._last_input_time).nanoseconds * 1e-9
        if self._input_idle_timeout > 0.0 and idle_sec >= self._input_idle_timeout:
            self._publish_wireless(WirelessController(), source='input_idle_timeout')
            self._periodic_stop_sent = True

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
