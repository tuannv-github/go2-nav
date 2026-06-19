#!/bin/bash

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
# shellcheck source=tmux.common.sh
source "$SCRIPT_DIR/tmux.common.sh"

SESSION=go2nav
tmux_stack_begin "$SCRIPT_DIR" "$SESSION" nav_realsense "$@"
tmux_stack_max_perf "$SCRIPT_DIR"

tmux_stack_ensure_session "$SESSION" main "$TMUX_STACK_PROJECT_DIR"
tmux_stack_ensure_four_panes "$SESSION" main "$TMUX_STACK_PROJECT_DIR"

SETUP="cd $TMUX_STACK_PROJECT_DIR && source ./setup.sh"
RS_SETUP="export CYCLONEDDS_URI=file://$TMUX_STACK_PROJECT_DIR/cyclonedds.realsense.xml"

tmux_stack_run_pane "$SESSION" main 0 "cd $SCRIPT_DIR && ./run_go2_controller.sh"
tmux_stack_run_pane "$SESSION" main 1 "$SETUP && ros2 launch realsense_video_publisher video_publisher.launch.py"
tmux_stack_run_pane "$SESSION" main 2 "$SETUP && $RS_SETUP && ros2 launch go2_nav realsense.launch.py"
tmux_stack_run_pane "$SESSION" main 3 "$SETUP && ros2 launch go2_nav go2_rtabmap.location.launch.py"

tmux_stack_reset_window "$SESSION" nav "$TMUX_STACK_PROJECT_DIR" \
    "$SETUP && ros2 launch go2_nav go2_nav2.launch.py"

tmux select-pane -t "$SESSION:main.0"
tmux_stack_attach "$SESSION"
