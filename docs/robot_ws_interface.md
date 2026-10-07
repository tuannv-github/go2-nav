# Robot websocket interface

The Go2 talks to the NeuroRAN robot interface on one websocket. It does not call that service's REST API. REST on the interface is for other servers (commands, queries, and a location submitted by a server).

Live service: `ws://10.1.101.220:6112/ws/robots`

Client: `go2_controller_bridge` (`RobotInterfaceLink` in `src/go2_controller/scripts/robot_interface_link.py`). The bridge starts the link when `robot_interface_enable` is true.

## Connection

```text
Go2  --websocket-->  ws://10.1.101.220:6112/ws/robots
```

1. Open the socket.
2. First message is `hello` (robot id, name, IMSIs).
3. Wait for `welcome`.
4. Send `pose` every 0.1 s.
5. On the same socket, answer `command` with `command_result`, answer a server-pushed `location` with `location_ack`, and answer an `estimates` mixture with `estimates_ack`.
6. If the socket drops, wait 1 s and connect again.

Robot id is `go2`. The name is `Go2`. The IMSI is read from the dongle (`GetDeviceInfo`), not from a fixed placeholder. On this robot that IMSI is `001010000000003`.

`robot_id` must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`. Each IMSI is 14 or 15 digits.

| Message | Direction |
| --- | --- |
| `hello` | Client → Server |
| `pose` | Client → Server |
| `command_result` | Client → Server |
| `location_ack` | Client → Server |
| `estimates_ack` | Client → Server |
| `terminal_output` | Client → Server |
| `terminal_exit` | Client → Server |
| `welcome` | Server → Client |
| `command` | Server → Client |
| `location` | Server → Client |
| `estimates` | Server → Client |
| `terminal_open` | Server → Client |
| `terminal_input` | Server → Client |
| `terminal_resize` | Server → Client |
| `terminal_close` | Server → Client |
| `error` | Server → Client |

## Client → Server

### hello

**Client → Server.** First message on a new socket.

```json
{
  "type": "hello",
  "robot_id": "go2",
  "name": "Go2",
  "imsis": ["001010000000003"]
}
```

### pose

**Client → Server.** Map pose, about 10 Hz, only after `welcome`. Taken from the ROS transform `map` → `base_link`.

| Field | Meaning |
| --- | --- |
| `x` | East, metres |
| `y` | North, metres |
| `z` | Up, metres |
| `w` | Heading, radians. 0 is east. The angle increases counterclockwise |
| `accuracy_m` | Fixed 1.0 m on this robot |
| `imsi` | Dongle IMSI this fix belongs to |
| `source` | `go2` |

```json
{
  "type": "pose",
  "x": 20.89,
  "y": -0.66,
  "z": -0.26,
  "w": 1.479,
  "accuracy_m": 1.0,
  "imsi": "001010000000003",
  "source": "go2"
}
```

If `map` → `base_link` is missing, that cycle is skipped.

### command_result

**Client → Server.** Reply to a `command`. `status` is `applied`, `rejected`, or `sent`.

```json
{
  "type": "command_result",
  "command_id": "abc123",
  "action": "stop",
  "status": "applied",
  "detail": "stopped"
}
```

This robot applies `stop` and `hold` (both stop motion). Any other action is `rejected`.

### terminal_output

**Client → Server.** Bytes read from the robot shell. `data` is text.

```json
{
  "type": "terminal_output",
  "data": "unitree@ubuntu:~/go2-nav$ "
}
```

### terminal_exit

**Client → Server.** The shell process ended. `code` is the exit status.

```json
{
  "type": "terminal_exit",
  "code": 0
}
```

### estimates_ack

**Client → Server.** One reply to an `estimates` mixture. `seq` is the top-level sequence of that message, not a sequence from inside `locations`.

```json
{
  "type": "estimates_ack",
  "seq": 10,
  "robot_id": "go2"
}
```

### location_ack

**Client → Server.** Reply when the interface pushes one older `location` fix. The robot's own `pose` messages do not use this ack, and an `estimates` mixture uses `estimates_ack` instead.

```json
{
  "type": "location_ack",
  "seq": 2,
  "robot_id": "go2"
}
```

## Server → Client

### welcome

**Server → Client.** The socket is up. Pose streaming starts after this.

```json
{
  "type": "welcome",
  "robot_id": "go2",
  "imsis": ["001010000000003"],
  "name": "Go2"
}
```

### command

**Server → Client.** Server-side control, delivered on this socket. The REST call that creates the command is made by another server, not by the robot.

```json
{
  "type": "command",
  "command_id": "abc123",
  "action": "hold"
}
```

### estimates

**Server → Client.** The ran-loc location mixture for this robot, one tick in one message. The robot stores this set and replaces the previous ran-loc set. It does not use these points as its own `pose`. Acknowledge once with `estimates_ack` and the top-level `seq`. Ignore the message when `robot_id` is not this robot.

`locations` is the full set, highest weight first. `x` and `y` are east and north in metres in the map frame. `z` and `w` are copied from the robot pose at that tick. `accuracy_m` is the uncertainty radius in metres. `weight` is the mixture weight, from 0 to 1, and the weights in one message sum to about 1. A heavier weight is the more likely location.

```json
{
  "type": "estimates",
  "seq": 10,
  "robot_id": "go2",
  "imsi": "001010000000003",
  "source": "ran-loc",
  "estimated_at": "2026-10-07T15:00:00+00:00",
  "locations": [
    {"seq": 10, "x": 38.6, "y": -0.5, "z": -0.25, "w": -0.002, "accuracy_m": 1.12, "weight": 0.41},
    {"seq": 11, "x": 30.1, "y": 1.4, "z": -0.25, "w": -0.002, "accuracy_m": 2.40, "weight": 0.38}
  ]
}
```

### location

**Server → Client.** One fix from an older server post, pushed back to the robot. Acknowledge it with `location_ack`. A ran-loc mixture arrives as `estimates`, not as this message.

```json
{
  "type": "location",
  "seq": 2,
  "robot_id": "go2",
  "imsi": "001010000000003",
  "x": 0.0,
  "y": 0.0,
  "z": 0.0,
  "w": 0.0,
  "accuracy_m": 1.0,
  "source": "external-estimator"
}
```

### terminal_open

**Server → Client.** Start one interactive `/bin/bash -i` on the robot. A second open replaces the current shell.

```json
{
  "type": "terminal_open",
  "cols": 80,
  "rows": 24
}
```

### terminal_input

**Server → Client.** Keystrokes for the shell, including newlines.

```json
{
  "type": "terminal_input",
  "data": "ls\n"
}
```

### terminal_resize

**Server → Client.** Change the shell window size.

```json
{
  "type": "terminal_resize",
  "cols": 120,
  "rows": 40
}
```

### terminal_close

**Server → Client.** Stop the shell.

```json
{
  "type": "terminal_close"
}
```

### error

**Server → Client.** The interface rejected the session (bad hello, IMSI already held by a connected robot, or a bad message). The client closes and reconnects.

```json
{
  "type": "error",
  "detail": "IMSI 001010000000003 is already on robot-go2-01"
}
```

## Server-side terminal socket

A server attaches a terminal with its own websocket. The interface forwards that session onto the robot socket. The first viewer sends `terminal_open`. The last viewer to disconnect sends `terminal_close`.

`ws://10.1.101.220:6112/ws/terminal/go2`

| Message | Direction |
| --- | --- |
| `terminal_input` | Server viewer → interface → robot |
| `terminal_resize` | Server viewer → interface → robot |
| `terminal_close` | Server viewer → interface → robot |
| `terminal_output` | Robot → interface → server viewer |
| `terminal_exit` | Robot → interface → server viewer |

## What the robot does not do

The robot does not call `POST /api/robots/go2/location` or any other REST path on `10.1.101.220:6112`. Those routes are for servers that command the robot or submit a location of their own.
