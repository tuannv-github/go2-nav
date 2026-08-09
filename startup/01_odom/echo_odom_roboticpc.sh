#!/usr/bin/env bash
# Echo /odom on roboticpc over SSH.
# Remote login shell is zsh; quotes must survive zsh -c so bash gets one -c string.
set -eo pipefail
args=$(printf '%q ' "$@")
exec ssh -tt roboticpc "/usr/bin/bash --noprofile --norc -c 'source /opt/ros/humble/setup.bash && exec ros2 topic echo --qos-reliability reliable /odom nav_msgs/msg/Odometry ${args}'"
