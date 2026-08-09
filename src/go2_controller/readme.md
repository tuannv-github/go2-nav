# go2_controller

Operator API is **HTTP REST** (`http://<nx>:8081/docs`). The dog consumes DDS
`/wirelesscontroller` and sport `/api/sport/request`.

**Full documentation:** [docs/go2_controller.md](../../docs/go2_controller.md)

## Quick start

```bash
colcon build --symlink-install --packages-select go2_controller
cd /home/unitree/go2-nav/startup && ./run_go2_controller.sh
```

```bash
curl -s http://127.0.0.1:8081/health
curl -s -X POST http://127.0.0.1:8081/wireless \
  -H 'Content-Type: application/json' \
  -d '{"lx":0.0,"ly":0.2,"rx":0.0,"ry":0.0,"keys":0}'
curl -s -X POST http://127.0.0.1:8081/cmd_vel \
  -H 'Content-Type: application/json' \
  -d '{"vx":0.2,"vy":0.0,"w":0.0,"duration":5.0}'
```

Priority: REST → MQTT → Nav. Lower sources are dropped while a higher one is active.
