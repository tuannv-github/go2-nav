#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

sudo apt-get update
sudo apt-get install \
  libpcl-dev=1.12.1+dfsg-3build1 \
  libopencv-dev libopencv-contrib-dev \
  ros-${ROS_DISTRO}-cv-bridge \
  ros-${ROS_DISTRO}-image-transport-plugins \
  ros-${ROS_DISTRO}-topic-tools

rosdep install --from-paths src --ignore-src -r -y
