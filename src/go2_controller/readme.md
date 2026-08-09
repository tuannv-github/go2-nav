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

Motion check (cancel Nav2 goal first):

```bash
./scripts/test_controller_move.sh
./scripts/test_controller_move.sh --action forward --distance 1.0 --v 0.2
./scripts/test_controller_move.sh --action left --distance 0.4 --v 0.2
./scripts/test_controller_move.sh --action right --distance 0.4 --v 0.2
./scripts/test_controller_move.sh --action turn_left --angle 90 --w 0.5
./scripts/test_controller_move.sh --action turn_right --angle 90 --w 0.5
```

Watch `/cmd_vel`:

```bash
./scripts/print_cmd_vel.sh
```

See [docs/go2_controller.md](../../docs/go2_controller.md#motion-test-script).
