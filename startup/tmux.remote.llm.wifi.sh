#!/bin/bash
# Remote control (MQTT + video) + VLAA LLM over WiFi.
# Lightweight stack: no Nav2 / RTAB-Map / Livox — only teleop, stream, voice, WiFi monitor.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
VLAA_APP_ROBOTS="${VLAA_APP_ROBOTS:-$HOME/vlaa/app_robots}"
WIFI_IFACE="${WIFI_IFACE:-wlan0}"
ROUTE_WIFI="$SCRIPT_DIR/route.wifi.sh"
# shellcheck source=tmux.common.sh
source "$SCRIPT_DIR/tmux.common.sh"

SESSION=remote_llm
tmux_stack_begin "$SCRIPT_DIR" "$SESSION" remote_llm "$@"
tmux_stack_finish_kill_only
tmux_stack_max_perf "$SCRIPT_DIR"

apply_wifi_routes() {
    echo "Applying WiFi routes ($ROUTE_WIFI)..."
    bash "$ROUTE_WIFI" || echo "Warning: route.wifi.sh failed (WiFi may not be up yet; see wifi window)"
}

apply_wifi_routes

tmux_stack_ensure_session "$SESSION" control "$TMUX_STACK_PROJECT_DIR"
tmux_stack_ensure_four_panes "$SESSION" control "$TMUX_STACK_PROJECT_DIR"

SETUP="cd $TMUX_STACK_PROJECT_DIR && source ./scripts/setup.sh"
RS_SETUP="export CYCLONEDDS_URI=file://$TMUX_STACK_PROJECT_DIR/cyclonedds/cyclonedds.realsense.xml"

tmux_stack_run_pane "$SESSION" control 0 "cd $SCRIPT_DIR && ./launch_realsense.sh"
tmux_stack_run_pane "$SESSION" control 1 "cd $SCRIPT_DIR && ./launch_video_publisher.sh"
tmux_stack_run_pane "$SESSION" control 2 "cd $SCRIPT_DIR && ./run_go2_controller.sh"
tmux_stack_run_pane "$SESSION" control 3 "nload $WIFI_IFACE"

tmux_stack_reset_window "$SESSION" llm "$VLAA_APP_ROBOTS" \
    "ROUTE_SCRIPT=\"$ROUTE_WIFI\" VLAA_APP_ROBOTS=\"$VLAA_APP_ROBOTS\" bash \"$SCRIPT_DIR/run_vlaa.sh\""

tmux select-window -t "$SESSION:control"
tmux select-pane -t "$SESSION:control.2"
echo "Session '$SESSION' started (control / llm)."
echo "  control.0 — RealSense"
echo "  control.1 — video stream"
echo "  control.2 — go2_controller (MQTT teleop)"
echo "  control.3 — nload $WIFI_IFACE"
tmux_stack_attach "$SESSION"
