#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SESSION="go2nav"

# Kill the session if it already exists
tmux has-session -t $SESSION 2>/dev/null
if [ $? -eq 0 ]; then
    echo "Killing existing tmux session '$SESSION'"
    tmux kill-session -t $SESSION
    sleep 1
fi

# Create a new session with the first window
echo "Creating new tmux session '$SESSION'"
tmux new-session -d -s $SESSION -n main

# Create the 2x2 layout by splitting strategically
# First split vertically (left/right), then split each side horizontally (top/bottom)
# Split the initial pane vertically to create left and right columns
tmux split-window -v -p 50 -t $SESSION:0.0
# Split the left pane horizontally to create top-left and bottom-left
tmux split-window -h -p 50 -t $SESSION:0.0
# Split the right pane horizontally to create top-right and bottom-right
tmux split-window -h -p 50 -t $SESSION:0.1

# Send commands to panes by navigating to them
# Start with top-left pane (should be current)
echo "Setting up joystick_controller pane (top-left)"
tmux send-keys -t $SESSION:0.0 "cd $SCRIPT_DIR/joystick_controller/ && ./run_mqtt_to_ros2.sh" C-m

# Move to top-right pane
tmux select-pane -R -t $SESSION:0
echo "Setting up realsense_video_publisher pane (top-right)"
tmux send-keys -t $SESSION:0.1 "cd $SCRIPT_DIR && source ./setup.sh && ros2 launch realsense_video_publisher video_publisher.launch.py" C-m

# Move to bottom-left pane
tmux select-pane -D -t $SESSION:0
echo "Setting up go2_nav realsense pane (bottom-left)"
tmux send-keys -t $SESSION:0.2 "cd $SCRIPT_DIR && source ./setup.sh && ros2 launch go2_nav realsense.launch.py" C-m

# Move to bottom-right pane
tmux select-pane -R -t $SESSION:0
echo "Setting up go2_nav rtabmap pane (bottom-right)"
tmux send-keys -t $SESSION:0.3 "cd $SCRIPT_DIR && source ./setup.sh && ros2 launch go2_nav go2_rtabmap.launch.py | tee go2_rtabmap.launch.py.log" C-m

# Set tiled layout for even 2x2 distribution
tmux select-layout -t $SESSION:0 tiled

# Select the first pane and attach
tmux select-pane -t $SESSION:0.0
echo "Attaching to tmux session '$SESSION'"
tmux attach -t $SESSION
