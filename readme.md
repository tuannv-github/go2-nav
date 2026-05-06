# Architecture

```mermaid
flowchart LR
    D[realsense2_camera]
    D --> M[rtabmap_slam]
    D --> N[nav2_bringup]
    D --> V[realsense_video_publisher]
```
