# `go2_nav/launch` Overview

This directory contains launch entry points for camera bringup, RTAB-Map SLAM/localization flows, visualization, and Nav2 navigation.

## Quick File Guide

- `realsense.launch.py`  
  Starts RealSense camera driver under `/input/camera` and publishes static TFs:
  - `base_link -> camera_link` (configurable pose)
  - `base_link -> utlidar_imu` (identity)

- `go2_rtabmap.mapping.launch.py`  
  RTAB-Map **fresh mapping**, RealSense **RGB-D only** (no Livox).

- `go2_rtabmap.livox.mapping.launch.py`  
  Same mapping flow plus Livox `PointCloud2` fused into `rtabmap` (requires RealSense + Livox running).

  Main behavior: defaults to **fresh mapping** (does not preload existing default DB unless explicitly provided via `database_path`).

- `go2_rtabmap.launch.py`  
  General RTAB-Map launch (supports both mapping and localization modes).  
  Similar node set to `go2_rtabmap.mapping.launch.py`, but default DB behavior is to reuse existing DB when present.

- `go2_rtabmap.location.launch.py`  
  RTAB-Map launch variant that also starts `location_publisher`.  
  Use when you need location publication integrated with the RTAB-Map stack.

- `go2_rtabmap_viz.launch.py`  
  Starts `rtabmap_viz` only (visualization/inspection UI for RTAB-Map graph/map/state).

- `go2_rviz.launch.py`  
  Starts RViz2 with `rviz/go2_navigation.rviz` config.

- `go2_nav2.launch.py`  
  Starts Nav2 (`navigation_launch.py` wrapper) and `base_link_project_tf`.  
  It does **not** start map server/AMCL; expects map + TF chain already available (e.g. from RTAB-Map).

## Main Differences

- Camera + TF source:
  - `realsense.launch.py` is now the canonical place for camera and static sensor TF publishing.
  - RTAB-Map launches no longer publish those static transforms.

- Mapping behavior:
  - `go2_rtabmap.mapping.launch.py`: fresh mapping, camera-only.
  - `go2_rtabmap.livox.mapping.launch.py`: fresh mapping with Livox + camera fusion.
  - `go2_rtabmap.launch.py`: generic flow; can continue from existing DB by default.

- Extra location output:
  - `go2_rtabmap.location.launch.py` adds `location_publisher`.

- Visualization only:
  - `go2_rtabmap_viz.launch.py` and `go2_rviz.launch.py` do not run SLAM/navigation compute pipelines.

- Navigation only:
  - `go2_nav2.launch.py` runs Nav2 stack and expects localization/map inputs already running.
  - It also launches `goal_server` by default (`enable_goal_server:=true`) to expose REST API for `/goal_pose`.

## Recommended Startup Sequences

- Fresh mapping (camera only):
  1. `ros2 launch go2_nav realsense.launch.py`
  2. `ros2 launch go2_nav go2_rtabmap.mapping.launch.py`

- Fresh mapping (camera + Livox):
  1. `ros2 launch go2_nav realsense.launch.py`
  2. `ros2 launch go2_nav livox_mid360.launch.py`
  3. `ros2 launch go2_nav go2_rtabmap.livox.mapping.launch.py`
  4. Optional: `ros2 launch go2_nav go2_rviz.launch.py`

- Localization with existing map DB:
  1. `ros2 launch go2_nav realsense.launch.py`
  2. `ros2 launch go2_nav go2_rtabmap.launch.py localization:=true`
  3. Optional: `ros2 launch go2_nav go2_nav2.launch.py`

- Navigation:
  1. Ensure TF + map/localization are already valid
  2. `ros2 launch go2_nav go2_nav2.launch.py`

## REST Goal API (`goal_server`)

When launching `go2_nav2.launch.py`, the REST API server is enabled by default and publishes goals to `/goal_pose`.

- Swagger UI: `http://<robot-ip>:8080/docs`
- Health check: `GET /health`
- Publish goal: `POST /goal`

Example request (from a real `/goal_pose` sample):

```bash
curl -X POST "http://<robot-ip>:8080/goal" \
  -H "Content-Type: application/json" \
  -d '{
    "x": 41.87440490722656,
    "y": 12.993324279785156,
    "yaw": 1.88,
    "frame_id": "map"
  }'
```

Expected response:

```json
{"ok": true, "message": "Goal published to /goal_pose"}
```

