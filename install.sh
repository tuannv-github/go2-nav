#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

sudo apt-get update
sudo apt-get install libpcl-dev=1.12.1+dfsg-3build1
sudo apt-get install libopencv-dev libopencv-contrib-dev
sudo apt-get install ros-$ROS_DISTRO-cv-bridge
sudo apt install ros-humble-image-transport-plugins
sudo apt install ros-humble-topic-tools

rosdep install --from-paths src --ignore-src -r -y
