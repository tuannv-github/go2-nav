#!/usr/bin/env python3
"""
Go2 controller bridge: single node publishing ``unitree_go/WirelessController`` (default ``/wirelesscontroller``).

- **MQTT** (JSON joystick payloads) has priority; each MQTT message is published immediately.
- **REST** (Starlette + OpenAPI): ``POST /wireless`` with the same JSON fields as MQTT; Swagger UI at ``/docs``.
- If no MQTT and no REST update for ``mqtt_timeout_sec``, **Nav2** commands from ``cmd_vel_topic`` are converted
  to ``WirelessController`` and published at ``publish_rate``.
- If there is **no new** MQTT, REST, or ``cmd_vel`` for ``input_idle_timeout_sec``,
  repeatedly publish an all-zero ``WirelessController`` (safe stop).

The robot consumes ``/wirelesscontroller`` over DDS (e.g. eth0 via cyclonedds.go2.xml); there is no
separate Twist mux or topic_tools relay.
"""

import json
import math
import threading

import paho.mqtt.client as mqtt
import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from unitree_go.msg import WirelessController

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


_REST_OPENAPI_SPEC = {
    'openapi': '3.0.3',
    'info': {
        'title': 'Go2 controller bridge',
        'version': '1.0.0',
        'description': (
            'Joystick-style WirelessController commands as JSON (same schema as MQTT). '
            'Forwarded to ROS 2 unitree_go/msg/WirelessController by the bridge node.'
        ),
    },
    'paths': {
        '/wireless': {
            'post': {
                'tags': ['WirelessController'],
                'summary': 'Send WirelessController joystick payload',
                'requestBody': {
                    'required': True,
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {
                                    'lx': {'type': 'number', 'description': 'Left stick X', 'default': 0.0},
                                    'ly': {'type': 'number', 'description': 'Left stick Y', 'default': 0.0},
                                    'rx': {'type': 'number', 'description': 'Right stick X', 'default': 0.0},
                                    'ry': {'type': 'number', 'description': 'Right stick Y', 'default': 0.0},
                                    'keys': {'type': 'integer', 'description': 'Button bitmask', 'default': 0},
                                },
                            },
                            'example': {'lx': 0.0, 'ly': 0.2, 'rx': 0.0, 'ry': 0.0, 'keys': 0},
                        }
                    },
                },
                'responses': {
                    '200': {
                        'description': 'Accepted',
                        'content': {'application/json': {'schema': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}}}},
                    },
                    '400': {'description': 'Bad request'},
                    '422': {'description': 'Body must be a JSON object'},
                },
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

        self._last_mqtt_time = None
        self._last_rest_time = None
        self._last_input_time = self.get_clock().now()
        self._mqtt_wc = WirelessController()
        self._nav_twist = Twist()

        self.publisher_ = self.create_publisher(WirelessController, self._out_topic, 10)
        self.create_subscription(Twist, self._cmd_vel_topic, self._on_cmd_vel, 10)

        period = 1.0 / max(rate_hz, 1.0)
        self.create_timer(period, self._tick_nav_fallback)

        rest_msg = ''
        if self._rest_enable and _REST_DEPS_AVAILABLE:
            self._start_rest_server()
            rest_msg = (
                f' REST: http://{self._rest_host}:{self._rest_port}/wireless '
                f'(Swagger: http://{self._rest_host}:{self._rest_port}/docs)'
            )
        elif self._rest_enable and not _REST_DEPS_AVAILABLE:
            self.get_logger().warn(
                'rest_enable=true but uvicorn/starlette not installed; REST API disabled.'
            )

        self.get_logger().info(
            f'Output WirelessController: {self._out_topic} | MQTT: {self.mqtt_broker}:{self.mqtt_port} '
            f'{self.mqtt_topic} | cmd_vel: {self._cmd_vel_topic} | mqtt_timeout={self._mqtt_timeout_sec}s | '
            f'input_idle_zero={self._input_idle_timeout}s{rest_msg}'
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

    def _rest_parse_and_apply(self, body) -> tuple[bool, str]:
        """Validate JSON body and publish; runs in worker thread (rclpy publish)."""
        if not isinstance(body, dict):
            return False, 'Body must be a JSON object'
        try:
            wc = _wireless_from_mapping(body)
        except (TypeError, ValueError) as e:
            return False, str(e)
        self._on_rest_wireless(wc)
        return True, ''

    def _start_rest_server(self) -> None:
        bridge = self

        async def openapi_json(_request):
            return JSONResponse(_REST_OPENAPI_SPEC)

        async def docs_page(_request):
            return HTMLResponse(_REST_DOCS_HTML)

        async def health(_request):
            return JSONResponse({'status': 'ok', 'node': 'go2_controller_bridge'})

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

        app = Starlette(
            routes=[
                Route('/openapi.json', openapi_json, methods=['GET']),
                Route('/docs', docs_page, methods=['GET']),
                Route('/health', health, methods=['GET']),
                Route('/wireless', wireless_post, methods=['POST']),
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

    def _on_rest_wireless(self, wc: WirelessController) -> None:
        self._touch_input_activity()
        self._last_rest_time = self.get_clock().now()
        if self._log_each_rest:
            self._log_io(
                input_kind='rest',
                input_topic=self._wireless_rest_topic_label(),
                input_msg_type='application/json',
                wc=wc,
            )
        self._publish_wireless(wc, source='rest')

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
            self._touch_input_activity()
            self._last_mqtt_time = self.get_clock().now()
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
        """Idle → zero WC; else when MQTT/REST stale, forward Nav cmd_vel as WirelessController."""
        now = self.get_clock().now()
        idle_sec = (now - self._last_input_time).nanoseconds * 1e-9
        if self._input_idle_timeout > 0.0 and idle_sec >= self._input_idle_timeout:
            self._publish_wireless(WirelessController(), source='input_idle_timeout')
            return

        if self._non_nav_input_fresh(now):
            return

        wc = self._twist_to_wireless(self._nav_twist)
        if (
            math.isfinite(wc.lx)
            and math.isfinite(wc.ly)
            and math.isfinite(wc.rx)
            and math.isfinite(wc.ry)
        ):
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
