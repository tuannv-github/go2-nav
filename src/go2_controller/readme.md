# go2_controller

ROS 2 package that merges **MQTT**, **HTTP REST** (OpenAPI/Swagger), and **Nav2 `cmd_vel`** into a single `unitree_go/msg/WirelessController` stream for the Go2 (default topic: `/wirelesscontroller` over DDS).

## Behavior

1. **MQTT** — Each JSON message is parsed and published immediately as `WirelessController`.
2. **REST** — `POST /wireless` with the same JSON shape; publishes immediately. Swagger UI: `/docs`.
3. **`cmd_vel`** — If neither MQTT nor REST has produced a “fresh” wireless update for `mqtt_timeout_sec`, the bridge converts `geometry_msgs/Twist` to `WirelessController` at `publish_rate`.
4. **Idle** — If there is no new MQTT, REST, or `cmd_vel` for `input_idle_timeout_sec`, an all-zero `WirelessController` is published (safe stop). Set `input_idle_timeout_sec` to `0` to disable this.

MQTT and REST both count toward the wireless freshness window (`mqtt_timeout_sec`); whichever was updated most recently gates whether Nav2 `cmd_vel` is used.

## Run

After building and sourcing your workspace:

```bash
ros2 launch go2_controller go2_controller.launch.py
ros2 launch go2_controller go2_controller.launch.py mqtt_broker:=192.168.1.100 rest_port:=8081
```

## REST API

Default bind: `0.0.0.0:8081` (see `rest_host`, `rest_port`).

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/wireless` | Body: JSON joystick fields (see below). Returns `{"ok": true}`. |
| `GET` | `/health` | Liveness JSON. |
| `GET` | `/docs` | Swagger UI. |
| `GET` | `/openapi.json` | OpenAPI schema. |

Example:

```bash
curl -s -X POST http://127.0.0.1:8081/wireless \
  -H 'Content-Type: application/json' \
  -d '{"lx":0.0,"ly":0.2,"rx":0.0,"ry":0.0,"keys":0}'
```

### MQTT / REST JSON (`WirelessController`)

Object form (recommended):

```json
{ "lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0, "keys": 0 }
```

MQTT also accepts a 5-element array: `[lx, ly, rx, ry, keys]`.

The HTTP layer uses **Starlette** (not FastAPI) plus a static OpenAPI document, so it does not pull in Pydantic and avoids clashes with a user `pip` install of Pydantic v2 versus an older distro FastAPI stack.

If `rest_enable` is true but **uvicorn / starlette** are not installed, REST is disabled and a warning is logged.

## Dependencies (ROS package)

Declared in `package.xml`: `rclpy`, `unitree_go`, `geometry_msgs`, `python3-paho-mqtt`, `python3-starlette`, `python3-uvicorn`. (Uvicorn pulls Starlette on `pip` installs as well.)

## Launch parameters (high level)

MQTT: `mqtt_broker`, `mqtt_port`, `mqtt_topic`, `mqtt_client_id`, `mqtt_retry_interval`, `mqtt_connect_timeout`.

REST: `rest_enable`, `rest_host`, `rest_port`, `log_each_rest_request`.

ROS / logic: `ros2_topic`, `cmd_vel_topic`, `mqtt_timeout_sec`, `publish_rate`, `invert_cmd_vel_lateral`, `input_idle_timeout_sec`, logging flags (`log_each_mqtt_message`, `log_each_rest_request`, `log_each_nav_publish`, `log_each_wireless_publish`, `log_idle_zero_publish`).

## Node script

Executable: `go2_controller_bridge.py` (see inline module docstring for full detail).
