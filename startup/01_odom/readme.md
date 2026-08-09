# Go2 odom startup

Bridges Unitree lidar odometry to the ROS default topic and TF:

- subscribe: `/utlidar/robot_odom` (eth0, dog)
- publish: `/odom` (`nav_msgs/Odometry`) on eth0 and on **all other NICs** (0.0.0.0)
- TF: `odom` → `base_link`
- IPC between the two processes: named pipe `/tmp/go2_odom.fifo`

First pose is the local origin (`zero_at_start:=true`). Does not change onboard `/utlidar/robot_odom`.

**Do not put eth0 Unitree traffic and the external bus in one CycloneDDS participant.**
That stops SPDP, so `/utlidar/robot_odom` never arrives. Startup runs two processes:

1. `utlidar_odom` — eth0 only (`cyclonedds.eth0.xml`)
2. `odom_ext_relay` — all interfaces (`cyclonedds.odom-ext.xml`, discovery tag `go2-odom-ext`)

A plain `ros2 topic echo /odom` with Humble-only env (no `CYCLONEDDS_URI`) often
sees the topic name but **no data**. WiFi multicast is unreliable — use a unicast Peer.

## Build

From repo root:

```bash
colcon build --symlink-install --packages-select odom
```

## Install (start at boot)

```bash
sudo ./startup/01_odom/install.sh
```

```bash
systemctl status go2-odom.service
journalctl -u go2-odom.service -f
```

Uninstall:

```bash
sudo ./startup/01_odom/install.sh uninstall
```

## Manual run

```bash
./startup/01_odom/run_odom.sh
```

Faithful relay (no origin zero):

```bash
./startup/01_odom/run_odom.sh zero_at_start:=false
```

## Subscribe on this machine (eth0)

```bash
~/go2-nav/startup/01_odom/echo_odom.sh --field pose.pose
```

```bash
source ~/go2-nav/scripts/setup.eth0.sh
ros2 topic echo /odom --field pose.pose
```

## Subscribe from another PC

Same `ROS_DOMAIN_ID=0` and `rmw_cyclonedds_cpp`. Copy
`cyclonedds/cyclonedds.odom-ext-client.xml` (any NIC / `0.0.0.0`), set
`<Peer address="..."/>` to a reachable robot IP (e.g. wlan `10.1.100.210`),
keep `<Tag>go2-odom-ext</Tag>`:

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=0
export CYCLONEDDS_URI=file:///path/to/cyclonedds.odom-ext-client.xml
ros2 topic echo /odom --field pose.pose
```

Check the external bus from the robot:

```bash
~/go2-nav/startup/01_odom/echo_odom_ext.sh --field pose.pose
```

Reset origin (next sample becomes zero; onboard `/utlidar/robot_odom` unchanged):

```bash
~/go2-nav/startup/01_odom/reset_odom.sh
```

On the external FastDDS bus (e.g. roboticpc):

```bash
ros2 service call /odom_ext_relay/reset std_srvs/srv/Empty
```

CLI monitor (does not publish `/odom`):

```bash
./scripts/utlidar_odom.py
```
