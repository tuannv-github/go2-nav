#!/bin/bash
# Remote control (MQTT + video) + VLAA LLM over WiFi.
# Lightweight stack: no Nav2 / RTAB-Map / Livox — only teleop, stream, voice, WiFi monitor.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
VLAA_APP_ROBOTS="${VLAA_APP_ROBOTS:-$HOME/vlaa/app_robots}"
WIFI_IFACE="${WIFI_IFACE:-wlan0}"
# shellcheck source=tmux.common.sh
source "$SCRIPT_DIR/tmux.common.sh"

SESSION=remote_llm
tmux_stack_begin "$SCRIPT_DIR" "$SESSION" remote_llm "$@"
tmux_stack_max_perf "$SCRIPT_DIR"

tmux_stack_ensure_session "$SESSION" control "$TMUX_STACK_PROJECT_DIR"
tmux_stack_ensure_four_panes "$SESSION" control "$TMUX_STACK_PROJECT_DIR"

SETUP="cd $TMUX_STACK_PROJECT_DIR && source ./setup.sh"
RS_SETUP="export CYCLONEDDS_URI=file://$TMUX_STACK_PROJECT_DIR/cyclonedds.realsense.xml"

tmux_stack_run_pane "$SESSION" control 0 "$SETUP && $RS_SETUP && ros2 launch go2_nav realsense.launch.py"
tmux_stack_run_pane "$SESSION" control 1 "$SETUP && ros2 launch realsense_video_publisher video_publisher.launch.py"
tmux_stack_run_pane "$SESSION" control 2 "cd $SCRIPT_DIR && ./run_go2_controller.sh"
tmux_stack_run_pane "$SESSION" control 3 "nload $WIFI_IFACE"

tmux_stack_reset_window "$SESSION" llm "$VLAA_APP_ROBOTS" \
    "VLAA_APP_ROBOTS=\"$VLAA_APP_ROBOTS\" bash \"$SCRIPT_DIR/run_vlaa.sh\""

tmux_stack_reset_window "$SESSION" wifi "$SCRIPT_DIR" \
    "bash \"$SCRIPT_DIR/wifi-heartbeat.sh\""

tmux select-window -t "$SESSION:control"
tmux select-pane -t "$SESSION:control.2"
echo "Session '$SESSION' started (control / llm / wifi)."
echo "  control.0 — RealSense"
echo "  control.1 — video stream"
echo "  control.2 — go2_controller (MQTT teleop)"
echo "  control.3 — nload $WIFI_IFACE"
tmux_stack_attach "$SESSION"
