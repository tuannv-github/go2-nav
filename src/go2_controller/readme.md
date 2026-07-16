# go2_controller

ROS 2 package that merges **MQTT**, **HTTP REST** (OpenAPI/Swagger), and **Nav2 `cmd_vel`** into a single `unitree_go/msg/WirelessController` stream for the Go2, plus **sport Move** for REST speed commands.

## Behavior

1. **MQTT** — Each JSON message is parsed and published immediately as `WirelessController`.
2. **REST wireless** — `POST /wireless` with the same JSON shape; publishes immediately. Swagger UI: `/docs`.
3. **REST cmd_vel (sport Move)** — `POST /cmd_vel` sends Go2 sport `Move` (`api_id` 1008) with real SI speeds: `vx`/`vy` in **m/s**, `w`/`wz` in **rad/s**, via `/api/sport/request`. Calibration (defaults): **vx×0.88**, **vy×1.4**, **w×1.25**. Change online with `GET/POST /calib`, `POST /calib/vx|vy|w/{scale}`. Optional `duration`; omit to hold until `POST /cmd_vel/stop` (`StopMove` api_id 1003).
4. **ROS `cmd_vel`** — If neither MQTT nor REST has produced a “fresh” wireless update for `mqtt_timeout_sec`, the bridge converts `geometry_msgs/Twist` to `WirelessController` at `publish_rate`.
5. **Idle** — If there is no new MQTT, REST, or `cmd_vel` for `input_idle_timeout_sec`, an all-zero `WirelessController` is published (safe stop). Set `input_idle_timeout_sec` to `0` to disable this.

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
| `POST` | `/wireless` | WirelessController sticks JSON. |
| `POST` | `/cmd_vel` | Sport Move: `{vx,vy,w}` in m/s / rad/s (`wz` still accepted; optional `duration`). |
| `POST` | `/cmd_vel/stop` | Sport StopMove. |
| `GET` | `/calib` | Current scales (`vx`, `vy`, `w`). |
| `POST` | `/calib` | Set scales JSON: `{"vx":0.88,"vy":1.4,"w":1.25}` (any key optional). |
| `POST` | `/calib/vx/{scale}` | Set forward scale online. |
| `POST` | `/calib/vy/{scale}` | Set lateral scale online. |
| `POST` | `/calib/w/{scale}` | Set yaw scale online. |
| `GET` | `/health` | Liveness JSON. |
| `GET` | `/docs` | Swagger UI. |
| `GET` | `/openapi.json` | OpenAPI schema. |

Examples:

```bash
# Stick teleop (WirelessController)
curl -s -X POST http://127.0.0.1:8081/wireless \
  -H 'Content-Type: application/json' \
  -d '{"lx":0.0,"ly":0.2,"rx":0.0,"ry":0.0,"keys":0}'

# Speed-based sport Move: command 0.2 m/s × vx scale 0.88 → send 0.176 m/s for 5 s
curl -s -X POST http://127.0.0.1:8081/cmd_vel \
  -H 'Content-Type: application/json' \
  -d '{"vx":0.2,"vy":0.0,"w":0.0,"duration":5.0}'

curl -s -X POST http://127.0.0.1:8081/cmd_vel/stop

# Override calibration at launch
ros2 launch go2_controller go2_controller.launch.py \
  cmd_vel_scale_vx:=0.88 cmd_vel_scale_vy:=1.4 cmd_vel_scale_w:=1.25

# Or change scales online (no restart)
curl -s http://127.0.0.1:8081/calib
curl -s -X POST http://127.0.0.1:8081/calib/vx/0.88
curl -s -X POST http://127.0.0.1:8081/calib/vy/1.4
curl -s -X POST http://127.0.0.1:8081/calib/w/1.25
curl -s -X POST http://127.0.0.1:8081/calib \
  -H 'Content-Type: application/json' \
  -d '{"vx":0.88,"vy":1.4,"w":1.25}'
```

### MQTT / REST JSON (`WirelessController`)

```json
{ "lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0, "keys": 0 }
```

## Dependencies (ROS package)

`rclpy`, `unitree_go`, `unitree_api`, `geometry_msgs`, `python3-paho-mqtt`, `python3-starlette`, `python3-uvicorn`.

## Node script

Executable: `go2_controller_bridge.py`.
