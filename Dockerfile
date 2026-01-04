FROM ubuntu:22.04

# Set working directory
WORKDIR /workspace

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Install ROS Humble and dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg2 \
    lsb-release \
    software-properties-common \
    && curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc | gpg --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg \
    && sh -c 'echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" > /etc/apt/sources.list.d/ros2-latest.list' \
    && apt-get update && apt-get install -y \
    ros-humble-desktop \
    python3-colcon-common-extensions \
    python3-pip \
    zsh \
    git \
    && rm -rf /var/lib/apt/lists/*
    
# Copy and run Oh My Zsh installation script
COPY install-oh-my-zsh.sh /tmp/install-oh-my-zsh.sh
RUN chmod +x /tmp/install-oh-my-zsh.sh && \
sed -i 's/sudo apt update/apt-get update/g' /tmp/install-oh-my-zsh.sh && \
sed -i 's/sudo apt install/apt-get install/g' /tmp/install-oh-my-zsh.sh && \
/tmp/install-oh-my-zsh.sh

# Source ROS setup
RUN echo "source /opt/ros/humble/setup.zsh" >> ~/.zshrc

# Install RTAB-Map and Nav2
RUN apt-get update && apt-get install -y \
ros-humble-rtabmap-ros \
ros-humble-navigation2 \
ros-humble-nav2-bringup \
ros-humble-nav2-common \
&& rm -rf /var/lib/apt/lists/*

# Install ROSIDL DDS IDL
RUN apt-get update && apt-get install -y \
ros-humble-rosidl-generator-dds-idl \
&& rm -rf /var/lib/apt/lists/*

# Build workspace
RUN /bin/zsh -c "source /opt/ros/humble/setup.zsh && cd /workspace && colcon build"
