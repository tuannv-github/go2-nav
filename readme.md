# Architecture

NX Humble between the Go2 MCU (**eth0**) and operators (**wlan**). Do not put both NICs in one Cyclone participant — Unitree SPDP dies and `/utlidar/robot_odom` never arrives.

Full write-up: [docs/architecture.md](docs/architecture.md).

```mermaid
flowchart TB
  subgraph Op["Operator"]
    HTTP["HTTP :8081 /docs"]
    PC["roboticpc /odom FastDDS"]
  end

  subgraph NX["NX"]
    CTL["go2_controller_bridge"]
    ODOM["utlidar_odom → fifo → odom_ext_relay"]
    RS["RealSense"]
    LX["Livox MID-360"]
    RTAB["RTAB-Map"]
    NAV["Nav2"]
  end

  subgraph Dog["Go2 eth0 192.168.123.161"]
    MCU["sport + Unitree lidar"]
  end

  HTTP -->|"REST > MQTT > Nav"| CTL
  CTL -->|"/wirelesscontroller\n/api/sport/request"| MCU
  MCU -->|"/utlidar/robot_odom"| ODOM
  ODOM -->|"/odom TF"| RTAB
  ODOM --> PC
  RS --> RTAB
  LX --> RTAB
  RTAB --> NAV
  NAV -->|"/cmd_vel"| CTL
```

| Layer | Path |
|-------|------|
| Teleop | HTTP `POST /wireless` or `/cmd_vel` → DDS to dog |
| Odom | `/utlidar/robot_odom` → `/odom` + `odom`→`base_link` (split DDS + pipe) |
| Map | RealSense RGB-D + Livox cloud + `/odom` → RTAB-Map |
| Nav | Nav2 `/cmd_vel` → controller (lowest priority) |

## Docs

- [Architecture](docs/architecture.md)
- [Go2 controller](docs/go2_controller.md)
- [Odom startup](startup/01_odom/readme.md)
- [RTAB topics](docs/rtab.md)
