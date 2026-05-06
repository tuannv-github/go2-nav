#!/usr/bin/env python3
"""
Joystick to MQTT Publisher
Reads joystick input and publishes to MQTT topic
"""

import json
import time
import argparse
import multiprocessing
import logging
import select
import os
import sys
from datetime import datetime
from evdev import InputDevice, categorize, ecodes
import paho.mqtt.client as mqtt

# Import device detection functions from list_joystick_devices
# Always use shared detection - required dependency
script_dir = os.path.dirname(os.path.abspath(__file__))
list_devices_path = os.path.join(script_dir, 'list_joystick_devices.py')
if not os.path.exists(list_devices_path):
    raise FileNotFoundError(f"Required file not found: {list_devices_path}")

# Add the directory to path to import the module
sys.path.insert(0, script_dir)
from list_joystick_devices import find_joystick_device_path, verify_joystick_device_path


def _role_bindings(raw):
    """Single (etype, ecode) or list of alternates → iterable for event_map."""
    if raw is None:
        return
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, tuple) and len(item) == 2:
                yield item
        return
    if isinstance(raw, tuple) and len(raw) == 2:
        yield raw


# Logitech Dual Action KEY codes; some EasySMX / USB gamepads report the same.
_LD2_KEY = {"a": 289, "l2": 294}


# EasySMX layout (signed 16-bit sticks on ABS_X/Y + ABS_RX/RY). Often enumerates as
# "Microsoft X-Box 360 pad". L2 may be BTN_TL2, Dual-Action code 294, or ABS_Z (analog LT);
# those must all drive `l2` so L2+A can produce keys==288 like Logitech.
_EASYSMX_CONFIG = {
    "lx": (ecodes.EV_ABS, ecodes.ABS_X),
    "ly": (ecodes.EV_ABS, ecodes.ABS_Y),
    "rx": (ecodes.EV_ABS, ecodes.ABS_RX),
    "ry": (ecodes.EV_ABS, ecodes.ABS_RY),
    "l1": (ecodes.EV_KEY, ecodes.BTN_TL),
    "r1": (ecodes.EV_KEY, ecodes.BTN_TR),
    "l2": [
        (ecodes.EV_KEY, ecodes.BTN_TL2),
        (ecodes.EV_KEY, _LD2_KEY["l2"]),
        (ecodes.EV_ABS, ecodes.ABS_Z),
    ],
    "btn_a": [
        (ecodes.EV_KEY, ecodes.BTN_SOUTH),
        (ecodes.EV_KEY, _LD2_KEY["a"]),
    ],
    "btn_b": (ecodes.EV_KEY, ecodes.BTN_EAST),
    "btn_x": (ecodes.EV_KEY, ecodes.BTN_NORTH),
    "btn_y": (ecodes.EV_KEY, ecodes.BTN_WEST),
    "axis_min": -32768,
    "axis_max": 32767,
}

# Device configurations: patterns matched as substrings of evdev device name (except DEFAULT).
DEVICE_CONFIGS = {
    "EasySMX": _EASYSMX_CONFIG,
    "X-Box 360": _EASYSMX_CONFIG,
    "Logitech": {
        "lx": (ecodes.EV_ABS, ecodes.ABS_X),
        "ly": (ecodes.EV_ABS, ecodes.ABS_Y),
        "rx": (ecodes.EV_ABS, ecodes.ABS_Z),
        "ry": (ecodes.EV_ABS, ecodes.ABS_RZ),
        "l2": [
            (ecodes.EV_KEY, 294),
            (ecodes.EV_KEY, ecodes.BTN_TL2),
        ],
        "btn_a": [
            (ecodes.EV_KEY, 289),
            (ecodes.EV_KEY, ecodes.BTN_SOUTH),
        ],
        "btn_b": (ecodes.EV_KEY, 290),
        "btn_x": (ecodes.EV_KEY, 288),
        "btn_y": (ecodes.EV_KEY, 291),
        "l1": (ecodes.EV_KEY, 292),
        "r1": (ecodes.EV_KEY, 293),
        "axis_min": 0,
        "axis_max": 255,
    },
    "DEFAULT": {
        "lx": (ecodes.EV_ABS, ecodes.ABS_X),
        "ly": (ecodes.EV_ABS, ecodes.ABS_Y),
        "rx": (ecodes.EV_ABS, ecodes.ABS_Z),
        "ry": (ecodes.EV_ABS, ecodes.ABS_RZ),
        "l2": (ecodes.EV_KEY, ecodes.BTN_TL2),
        "btn_a": (ecodes.EV_KEY, ecodes.BTN_A),
        "axis_min": 0,
        "axis_max": 255,
    }
}

# CLI --device-config values -> canonical DEVICE_CONFIGS key (None = infer from device name)
DEVICE_CONFIG_CLI = {
    "auto": None,
    "easysmx": "EasySMX",
    "xbox360": "X-Box 360",
    "logitech": "Logitech",
    "default": "DEFAULT",
}


class JoystickReader:
    """Class to read joystick events and send state to queue"""
    
    def __init__(self, device_path, device_name, state_queue, running, button_mapping, log_file,
                 max_x_speed=1.0, max_y_speed=1.0, max_yaw_speed=1.0,
                 device_config_key=None, reconnect_auto_detect=True, reconnect_delay=1.0,
                 control_heartbeat_interval=0.5, transmit_armed_default=False):
        self.state_queue = state_queue
        self.running = running
        self.button_mapping = button_mapping
        self.log_file = log_file
        self.control_heartbeat_interval = control_heartbeat_interval
        self._last_state_queued_monotonic = 0.0
        self._transmit_armed_default = transmit_armed_default
        self._transmit_enabled = transmit_armed_default
        self.max_x_speed = max_x_speed
        self.max_y_speed = max_y_speed
        self.max_yaw_speed = max_yaw_speed
        self.device_config_key = device_config_key
        self.reconnect_auto_detect = reconnect_auto_detect
        self.reconnect_delay = reconnect_delay
        self._fixed_device_path = device_path

        # Internal state
        self.axes_raw = {}
        self.axes_raw_values = {}
        self.buttons_raw = {}
        
        # Setup logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

        self._configure_for_device(device_path, device_name)

    def _configure_for_device(self, device_path, device_name):
        """Apply device path/name and rebuild axis map and evdev bindings."""
        self.device_path = device_path
        self.device_name = device_name

        if self.device_config_key is not None and self.device_config_key in DEVICE_CONFIGS:
            self.config = DEVICE_CONFIGS[self.device_config_key]
            self.logger.info(
                "JoystickReader: Using forced %s axis/button mapping", self.device_config_key
            )
        else:
            self.config = DEVICE_CONFIGS["DEFAULT"]
            matched = False
            for pattern, device_config in DEVICE_CONFIGS.items():
                if pattern != "DEFAULT" and pattern in self.device_name:
                    self.config = device_config
                    self.logger.info(
                        "JoystickReader: Applied %s mapping (matched device name)", pattern
                    )
                    matched = True
                    break
            if not matched:
                self.logger.info("JoystickReader: Using DEFAULT mapping for %s", self.device_name)

        self.axis_min = self.config["axis_min"]
        self.axis_max = self.config["axis_max"]

        self.controller_state = {
            'lx': 0.0, 'ly': 0.0, 'rx': 0.0, 'ry': 0.0, 'btn_a': 0, 'btn_b': 0,
            'btn_x': 0, 'btn_y': 0, 'l1': 0, 'r1': 0, 'l2': 0, 'start': 0,
        }
        self.buttons_raw.clear()

        self.event_map = {}
        roles = ['lx', 'ly', 'rx', 'ry', 'btn_a', 'btn_b', 'btn_x', 'btn_y', 'l1', 'r1', 'l2']
        for role in roles:
            for etype, ecode in _role_bindings(self.config.get(role)):
                self.event_map[(etype, ecode)] = role

        for btn_name, bit_pos in self.button_mapping.items():
            if hasattr(ecodes, btn_name):
                code = getattr(ecodes, btn_name)
                key_t = (ecodes.EV_KEY, code)
                if key_t not in self.event_map:
                    self.event_map[key_t] = ('key', bit_pos)

        # START: arm/disarm MQTT transmit on press edge (overrides BTN_* bitfield tuple)
        self.event_map[(ecodes.EV_KEY, ecodes.BTN_START)] = 'start'

    def _resolve_device_path(self):
        """Return (path, evdev_name) for opening, or (None, None) if not available."""
        if self.reconnect_auto_detect:
            path = find_joystick_device_path()
        else:
            path = self._fixed_device_path
            if path and not os.path.exists(path):
                path = None
        if not path:
            return None, None
        ok, detail = verify_joystick_device_path(path)
        if not ok:
            self.logger.warning("JoystickReader: %s", detail)
            return None, None
        return path, detail

    def _reset_and_publish_neutral(self):
        """Zero sticks/buttons and queue neutral payload after disconnect."""
        self.controller_state.update({
            'lx': 0.0, 'ly': 0.0, 'rx': 0.0, 'ry': 0.0,
            'btn_a': 0, 'btn_b': 0, 'btn_x': 0, 'btn_y': 0, 'l1': 0, 'r1': 0, 'l2': 0,
            'start': 0,
        })
        self.buttons_raw.clear()
        try:
            self.update_wireless_controller_state()
        except Exception as e:
            self.logger.warning("JoystickReader: Could not publish neutral state: %s", e)

    def _publish_if_transmit_enabled(self):
        """Queue MQTT state only while transmit is armed (START toggles)."""
        if self._transmit_enabled:
            self.update_wireless_controller_state()

    def _on_start_button_event(self, value):
        """Edge on press: toggle transmit on/off; stop sends one neutral snapshot."""
        prev = self.controller_state.get('start', 0)
        self.controller_state['start'] = value
        if prev == 0 and value == 1:
            self._transmit_enabled = not self._transmit_enabled
            if self._transmit_enabled:
                self.logger.warning("Wanring -------- start sending")
                self.logger.info("JoystickReader: MQTT transmit enabled (START)")
                self.update_wireless_controller_state()
            else:
                self.logger.warning("Wanring -------- stop sending")
                self.logger.info("JoystickReader: MQTT transmit disabled (START); neutral")
                self._reset_and_publish_neutral()
            return True
        if self._transmit_enabled:
            self.update_wireless_controller_state()
        return True

    def normalize_axis(self, value):
        """Normalize axis value to range [-1.0, 1.0] using configured ranges"""
        if value == 0 and self.axis_min < 0:
            return 0.0
        
        # Use instance-specific min/max
        normalized = (value - self.axis_min) / (self.axis_max - self.axis_min) * 2.0 - 1.0
        
        # Apply deadzone
        if abs(normalized) < 0.1:
            return 0.0
        return round(normalized, 3)
    
    def update_wireless_controller_state(self):
        """Update WirelessController format from internal controller_state and buttons"""
        # ly is forward/backward, lx is left/right (lateral), rx is yaw
        # We scale these by the configured max speeds
        state = {
            'lx': round(self.controller_state.get('lx', 0.0) * self.max_y_speed, 3), # Lateral
            'ly': round(-self.controller_state.get('ly', 0.0) * self.max_x_speed, 3), # Forward/Backward
            'rx': round(self.controller_state.get('rx', 0.0) * self.max_yaw_speed, 3), # Yaw
            'ry': round(-self.controller_state.get('ry', 0.0), 3),  # Invert Y axis
            'device_name': self.device_name,
            'device_path': self.device_path,
        }
        
        # Encode buttons as uint16 bitfield
        keys = 0
        
        # 1. Map roles to bit positions
        role_to_bit = {
            'btn_a': 0, 'btn_b': 1, 'btn_x': 2, 'btn_y': 3,
            'l1': 4, 'r1': 5, 'select': 6, 'start': 7, 'mode': 8,
            'l3': 9, 'r3': 10
        }
        
        for role, bit_pos in role_to_bit.items():
            if self.controller_state.get(role, 0):
                keys |= (1 << bit_pos)
        
        # 2. Fall back to generic buttons_raw for buttons not covered by roles
        for button_name, pressed in self.buttons_raw.items():
            # Check if this button's code is already handled by a role
            if hasattr(ecodes, button_name):
                code = getattr(ecodes, button_name)
                if (ecodes.EV_KEY, code) in self.event_map:
                    continue # Already handled by roles loop above
                
            bit_position = self.button_mapping.get(button_name)
            if bit_position is not None and pressed:
                keys |= (1 << bit_position)
        
        # Unitree / Easy-style combo: L2+A → 288, L2 alone → 32, A alone (no other btns) → 4
        a_button_pressed = self.controller_state['btn_a']
        l2_pressed = self.controller_state['l2']
        
        # Check if other mapped buttons are pressed (for "A button only" logic)
        other_buttons_pressed = False
        for button_name, pressed in self.buttons_raw.items():
            # Check if this button is NOT the one mapped to btn_a or l2 role
            etype, ecode = self.event_map.get((ecodes.EV_KEY, getattr(ecodes, button_name, None)), (None, None))
            mapped_role = self.event_map.get((ecodes.EV_KEY, getattr(ecodes, button_name, None)))
            if pressed and mapped_role not in ['btn_a', 'l2']:
                other_buttons_pressed = True
                break
        
        if l2_pressed and a_button_pressed:
            keys = 288
            self.logger.debug(f"L2 pressed, BTN_A pressed, setting keys=288")
        elif l2_pressed:
            keys = 32
            self.logger.debug(f"L2 pressed, setting keys=32")
        elif a_button_pressed and not other_buttons_pressed:
            keys = 4
            self.logger.debug(f"BTN_A only pressed, setting keys=4")
        
        state['keys'] = keys & 0xFFFF  # Ensure uint16
        
        # Put state in queue (non-blocking, drop if queue is full to keep latest)
        queued = False
        try:
            self.state_queue.put_nowait(state)
            self.logger.debug(f"JoystickReader: Put state in queue: {state}")
            queued = True
        except Exception as e:
            # Queue is full, try to get one and put new one
            try:
                self.state_queue.get_nowait()
                self.state_queue.put_nowait(state)
                self.logger.debug(f"JoystickReader: Queue was full, dropped old state, put new: {state}")
                queued = True
            except Exception as e2:
                self.logger.warning(f"JoystickReader: Failed to put state in queue: {e2}")
        if queued:
            self._last_state_queued_monotonic = time.monotonic()
    
    def process_event(self, event):
        """Process joystick event and update state using role-based event_map"""
        # Log all events as requested
        self.logger.info(f"JoystickReader: Received event: type={event.type}, code={event.code}, value={event.value}")
        
        mapping = self.event_map.get((event.type, event.code))
        
        if mapping:
            if event.type == ecodes.EV_ABS:
                self.logger.debug(f"Axis event: role={mapping}, code={event.code}, value={event.value}")

                if mapping == 'l2':
                    # Analog left trigger (typical Xbox / EasySMX on ABS_Z, 0–255)
                    v = max(0, int(event.value))
                    self.controller_state['l2'] = 1 if v > 48 else 0
                else:
                    normalized_value = self.normalize_axis(event.value)
                    self.controller_state[mapping] = normalized_value

                self._publish_if_transmit_enabled()
                return True

            if isinstance(mapping, tuple) and mapping[0] == 'key':
                bit_pos = mapping[1]
                # Find the button name from ecodes if possible
                button_name = None
                for name, pos in self.button_mapping.items():
                    if pos == bit_pos:
                        button_name = name
                        break
                
                if not button_name:
                    button_name = f"BTN_{event.code}"
                    
                self.buttons_raw[button_name] = event.value
                self._publish_if_transmit_enabled()
                return True
                
            if isinstance(mapping, str) and mapping == 'start':
                return self._on_start_button_event(event.value)

            if isinstance(mapping, str) and (
                mapping.startswith('btn_') or mapping in ['l1', 'r1', 'l2', 'select', 'mode', 'l3', 'r3']
            ):
                self.controller_state[mapping] = event.value
                self._publish_if_transmit_enabled()
                return True
        
        elif event.type == ecodes.EV_SYN:
            return False
            
        return False
    
    def run(self):
        """Reconnect loop: find device (scan or fixed path), read until disconnect, repeat."""
        mode = "auto-detect" if self.reconnect_auto_detect else f"fixed {self._fixed_device_path}"
        self.logger.info(
            "JoystickReader: Started (%s; %.1fs between reconnect tries)",
            mode,
            self.reconnect_delay,
        )

        while self.running.value:
            path, name = self._resolve_device_path()
            if not path:
                self.logger.warning(
                    "JoystickReader: No gamepad (%s); retry in %.1fs",
                    mode,
                    self.reconnect_delay,
                )
                time.sleep(self.reconnect_delay)
                continue

            self._configure_for_device(path, name)
            self.logger.info(
                "JoystickReader: Using %s at %s",
                self.device_name,
                self.device_path,
            )
            self._transmit_enabled = self._transmit_armed_default
            self.logger.info(
                "JoystickReader: MQTT transmit %s at session start (press START to toggle)",
                "enabled" if self._transmit_enabled else "disabled until START",
            )

            device = None
            session_ok = False
            try:
                device = InputDevice(path)
                self.logger.info(
                    "JoystickReader: Capabilities: %s",
                    list(device.capabilities().keys()),
                )
                try:
                    device.grab()
                    self.logger.info("JoystickReader: Grabbed device exclusively")
                except Exception as grab_error:
                    self.logger.warning(
                        "JoystickReader: Could not grab device: %s", grab_error
                    )
                    self.logger.info("JoystickReader: Continuing without grab...")

                iteration = 0
                while self.running.value:
                    try:
                        if not device.fd:
                            self.logger.warning("JoystickReader: Invalid fd; reconnecting")
                            break
                        r, _, _ = select.select([device.fd], [], [], 0.1)
                        if r:
                            for event in device.read():
                                if not self.running.value:
                                    break
                                self.process_event(event)
                        else:
                            now = time.monotonic()
                            if (
                                self.control_heartbeat_interval > 0
                                and now - self._last_state_queued_monotonic
                                >= self.control_heartbeat_interval
                            ):
                                self._publish_if_transmit_enabled()
                            iteration += 1
                            if iteration % 50 == 0:
                                self.logger.debug(
                                    "JoystickReader: Idle waiting for events (%s)",
                                    iteration,
                                )
                    except OSError as e:
                        self.logger.warning(
                            "JoystickReader: Device lost (%s); reconnecting...", e
                        )
                        break
                    except Exception as e:
                        self.logger.error(
                            "JoystickReader: Read loop error: %s", e, exc_info=True
                        )
                        time.sleep(0.1)
                session_ok = True
            except Exception as e:
                self.logger.warning(
                    "JoystickReader: Open %s failed (%s); retry in %.1fs",
                    path,
                    e,
                    self.reconnect_delay,
                )
                time.sleep(self.reconnect_delay)
                continue
            finally:
                if device is not None:
                    try:
                        device.ungrab()
                    except Exception:
                        pass
                    try:
                        device.close()
                    except Exception:
                        pass

            if not self.running.value:
                break

            if session_ok:
                self.logger.info(
                    "JoystickReader: Session ended; neutral output, pause %.1fs",
                    self.reconnect_delay,
                )
                self._reset_and_publish_neutral()
                time.sleep(self.reconnect_delay)

        self.logger.info("JoystickReader: Exited")


class MQTTPublisher:
    """Class to read state from queue and publish to MQTT"""
    
    def __init__(self, mqtt_broker, mqtt_port, mqtt_topic, mqtt_username, mqtt_password,
                 state_queue, running, publish_interval, log_file):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.mqtt_topic = mqtt_topic
        self.mqtt_username = mqtt_username
        self.mqtt_password = mqtt_password
        self.state_queue = state_queue
        self.running = running
        self.publish_interval = publish_interval
        self.log_file = log_file
        
        # Setup logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    @staticmethod
    def on_connect(client, userdata, flags, reason_code, properties=None):
        logger = logging.getLogger(__name__)
        if reason_code == 0:
            logger.info("MQTTPublisher: Connected to MQTT broker")
        else:
            logger.error(f"MQTTPublisher: Failed to connect to MQTT broker, reason code {reason_code}")
    
    @staticmethod
    def on_disconnect(client, userdata, flags, reason_code, properties=None):
        logger = logging.getLogger(__name__)
        logger.info(f"MQTTPublisher: Disconnected from MQTT broker, flags: {flags}, reason code: {reason_code}")
    
    def publish_state(self, state):
        """Publish state to MQTT"""
        try:
            payload = json.dumps(state)
            result = self.mqtt_client.publish(self.mqtt_topic, payload, qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.logger.info(f"MQTTPublisher: Published to {self.mqtt_topic}: {payload}")
                self.logger.debug(f"MQTTPublisher: Published state: {json.dumps(state, indent=2)}")
                return True
            else:
                self.logger.error(f"MQTTPublisher: Failed to publish: {result.rc}")
                return False
        except Exception as e:
            self.logger.error(f"MQTTPublisher: Error publishing to MQTT: {e}", exc_info=True)
            return False
    
    def run(self):
        """Main loop to read from queue and publish to MQTT"""
        self.logger.info("MQTTPublisher: Started, waiting for state updates...")
        
        try:
            # Create MQTT client
            self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            if self.mqtt_username and self.mqtt_password:
                self.mqtt_client.username_pw_set(self.mqtt_username, self.mqtt_password)
            
            self.mqtt_client.on_connect = self.on_connect
            self.mqtt_client.on_disconnect = self.on_disconnect
            
            # Connect to MQTT
            try:
                self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
                self.mqtt_client.loop_start()
                time.sleep(1)  # Wait for connection
                self.logger.info(f"MQTTPublisher: Connected to MQTT broker at {self.mqtt_broker}:{self.mqtt_port}")
            except Exception as e:
                self.logger.error(f"MQTTPublisher: Error connecting to MQTT broker: {e}")
                return
            
            iteration = 0
            while self.running.value:
                try:
                    # Try to get state from queue (blocking with timeout)
                    try:
                        state = self.state_queue.get(timeout=self.publish_interval)
                        self.logger.debug(f"MQTTPublisher: Got state from queue, publishing...")
                        # Drain queue to get latest state (drop older ones)
                        latest_state = state
                        while True:
                            try:
                                latest_state = self.state_queue.get_nowait()
                            except:
                                break
                        # Publish only the latest state
                        self.publish_state(latest_state)
                    except Exception as queue_empty:
                        # No new data, log periodically
                        if iteration % 10 == 0:  # Log every 10 iterations (every 1 second)
                            self.logger.debug(f"MQTTPublisher: No new data (iteration {iteration})")
                    
                    iteration += 1
                except Exception as e:
                    self.logger.error(f"MQTTPublisher: Error in publish loop: {e}", exc_info=True)
                    time.sleep(self.publish_interval)
        except Exception as e:
            self.logger.error(f"MQTTPublisher: Fatal error: {e}", exc_info=True)
        finally:
            if hasattr(self, 'mqtt_client'):
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            self.logger.info("MQTTPublisher: Exited")


class JoystickMQTT:
    """Main coordinator class to manage joystick reader and MQTT publisher processes"""
    
    def __init__(self, device_path, mqtt_broker, mqtt_port, mqtt_topic, 
                 mqtt_username=None, mqtt_password=None, log_file=None,
                 max_x_speed=1.0, max_y_speed=1.0, max_yaw_speed=1.0,
                 device_config_key=None, reconnect_auto_detect=True, reconnect_delay=1.0,
                 control_heartbeat_interval=0.5, transmit_armed_default=False):
        self.device_path = device_path
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.mqtt_topic = mqtt_topic
        self.mqtt_username = mqtt_username
        self.mqtt_password = mqtt_password
        self.max_x_speed = max_x_speed
        self.max_y_speed = max_y_speed
        self.max_yaw_speed = max_yaw_speed
        self.device_config_key = device_config_key
        self.reconnect_auto_detect = reconnect_auto_detect
        self.reconnect_delay = reconnect_delay
        self.control_heartbeat_interval = control_heartbeat_interval
        self.transmit_armed_default = transmit_armed_default
        
        # Setup logging
        if log_file is None:
            log_file = "joystick_mqtt.py.log"
        self.log_file = log_file
        
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Logging to file: {log_file}")
        
        self.logger.info(
            "Reconnect: %s (interval %.1fs)",
            "scan for gamepad" if self.reconnect_auto_detect else f"reuse path {self.device_path}",
            self.reconnect_delay,
        )

        # Verify device exists
        try:
            test_device = InputDevice(device_path)
            self.device_name = test_device.name
            self.logger.info(f"Found joystick device: {self.device_name}")
            test_device.close()
        except Exception as e:
            self.logger.error(f"Error opening joystick device {device_path}: {e}")
            raise
        
        # Create queue for inter-process communication
        self.state_queue = multiprocessing.Queue(maxsize=10)  # Limit queue size
        
        # Process control
        self.running = multiprocessing.Value('b', False)  # Shared boolean
        self.read_process = None
        self.publish_process = None
        
        # Button mapping for Xbox 360 controller to keys bitfield
        self.button_mapping = {
            'BTN_SOUTH': 0,      # A button
            'BTN_EAST': 1,       # B button
            'BTN_NORTH': 2,      # X button
            'BTN_WEST': 3,       # Y button
            'BTN_TL': 4,         # Left Bumper
            'BTN_TR': 5,         # Right Bumper
            'BTN_SELECT': 6,     # Back button
            'BTN_START': 7,      # Start button
            'BTN_MODE': 8,       # Xbox button
            'BTN_THUMBL': 9,     # Left stick press
            'BTN_THUMBR': 10,    # Right stick press
        }
    
    def run(self, publish_interval=0.1):
        """Main loop to start processes for reading joystick and publishing to MQTT"""
        self.logger.info("Starting joystick to MQTT publisher...")
        self.logger.info(f"Device: {self.device_path}")
        self.logger.info(f"MQTT Topic: {self.mqtt_topic}")
        self.logger.info("Press Ctrl+C to stop")
        
        self.running.value = True
        
        # Create reader and publisher instances
        reader = JoystickReader(
            device_path=self.device_path,
            device_name=self.device_name,
            state_queue=self.state_queue,
            running=self.running,
            button_mapping=self.button_mapping,
            log_file=self.log_file,
            max_x_speed=self.max_x_speed,
            max_y_speed=self.max_y_speed,
            max_yaw_speed=self.max_yaw_speed,
            device_config_key=self.device_config_key,
            reconnect_auto_detect=self.reconnect_auto_detect,
            reconnect_delay=self.reconnect_delay,
            control_heartbeat_interval=self.control_heartbeat_interval,
            transmit_armed_default=self.transmit_armed_default,
        )
        
        publisher = MQTTPublisher(
            mqtt_broker=self.mqtt_broker,
            mqtt_port=self.mqtt_port,
            mqtt_topic=self.mqtt_topic,
            mqtt_username=self.mqtt_username,
            mqtt_password=self.mqtt_password,
            state_queue=self.state_queue,
            running=self.running,
            publish_interval=publish_interval,
            log_file=self.log_file
        )
        
        # Start reading process
        self.read_process = multiprocessing.Process(
            target=reader.run,
            daemon=True
        )
        self.read_process.start()
        self.logger.info("Started read process")
        
        # Start publishing process
        self.publish_process = multiprocessing.Process(
            target=publisher.run,
            daemon=True
        )
        self.publish_process.start()
        self.logger.info("Started publish process")
        time.sleep(0.1)  # Give processes a moment to start and log
        
        try:
            # Wait for processes (they run as daemons, so main thread can be interrupted)
            while self.running.value:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.logger.info("\nStopping...")
            self.running.value = False
        finally:
            self.running.value = False
            # Wait for processes to finish
            if self.read_process:
                self.read_process.join(timeout=2.0)
            if self.publish_process:
                self.publish_process.join(timeout=2.0)
            self.logger.info("All processes stopped")


def main():
    parser = argparse.ArgumentParser(description='Read joystick input and publish to MQTT')
    parser.add_argument('--device', '-d', type=str, default=None,
                       help='Joystick evdev path (e.g., /dev/input/event22). Auto-detect if not specified; '
                            'legacy /dev/input/js* nodes are not supported.')
    parser.add_argument('--broker', '-b', type=str, default='localhost',
                       help='MQTT broker address (default: localhost)')
    parser.add_argument('--port', '-p', type=int, default=1883,
                       help='MQTT broker port (default: 1883)')
    parser.add_argument('--topic', '-t', type=str, default='joystick/state',
                       help='MQTT topic to publish to (default: joystick/state)')
    parser.add_argument('--username', '-u', type=str, default=None,
                       help='MQTT username (optional)')
    parser.add_argument('--password', '-P', type=str, default=None,
                       help='MQTT password (optional)')
    parser.add_argument('--interval', '-i', type=float, default=0.1,
                       help='Publish interval in seconds (default: 0.1)')
    parser.add_argument(
        '--control-heartbeat',
        type=float,
        default=0.5,
        metavar='SEC',
        help='Re-send current control state at least this often when there are no joystick '
             'events (default: 0.5). Set to 0 to disable.',
    )
    parser.add_argument(
        '--transmit-on-start',
        action='store_true',
        help='Begin with MQTT transmit enabled (default: off until START is pressed once)',
    )
    parser.add_argument('--log-file', '-l', type=str, default=None,
                       help='Log file path (default: joystick_mqtt.py.log)')
    parser.add_argument('--max-x-speed', type=float, default=0.5,
                       help='Max X speed in m/s (default: 0.5)')
    parser.add_argument('--max-y-speed', type=float, default=0.5,
                       help='Max Y speed in m/s (default: 0.5)')
    parser.add_argument(
        '--device-config',
        type=str,
        default='auto',
        choices=sorted(DEVICE_CONFIG_CLI.keys()),
        help='Axis/button preset: auto (match evdev name), easysmx / xbox360 (EasySMX layout), '
             'logitech, default',
    )
    parser.add_argument('--print-device-name', action='store_true',
                       help='Print the evdev device name for --device or auto-detect, then exit')
    parser.add_argument('--max-yaw-speed', type=float, default=0.5,
                       help='Max Yaw speed in rad/s (default: 0.5)')
    parser.add_argument(
        '--reconnect-delay',
        type=float,
        default=1.0,
        help='Seconds to wait between gamepad disconnect and reopen/re-scan (default: 1.0)',
    )

    args = parser.parse_args()
    
    if args.print_device_name:
        logging.basicConfig(level=logging.WARNING, format='%(message)s')
        device_path = args.device
        if device_path is None:
            device_path = find_joystick_device_path()
            if device_path is None:
                logging.error("No joystick device found; specify --device PATH")
                return 1
        ok, detail = verify_joystick_device_path(device_path)
        if not ok:
            logging.error(detail)
            return 1
        print(detail)
        return 0
    
    # Setup basic logging early so we can see device detection messages
    log_file = args.log_file if args.log_file else "joystick_mqtt.py.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    # Find joystick device if not specified
    device_path = args.device
    if device_path is None:
        logging.info("Auto-detecting joystick device...")
        device_path = find_joystick_device_path()
        if device_path is None:
            logging.error("Error: No joystick device found. Please specify --device")
            return 1
        logging.info("Auto-detected gamepad path: %s", device_path)
    
    logging.info(f"Using joystick device: {device_path}")
    ok, detail = verify_joystick_device_path(device_path)
    if not ok:
        logging.error(detail)
        return 1
    logging.info("Joystick device check OK: %s", detail)
    device_config_key = DEVICE_CONFIG_CLI[args.device_config]
    if device_config_key is not None:
        logging.info("Joystick mapping preset: %s (forced)", device_config_key)
    reconnect_auto_detect = args.device is None
    if not reconnect_auto_detect:
        logging.info(
            "Reconnect will retry path %s (use auto-detect at launch omitting --device to re-scan)",
            device_path,
        )
    try:
        joystick_mqtt = JoystickMQTT(
            device_path=device_path,
            mqtt_broker=args.broker,
            mqtt_port=args.port,
            mqtt_topic=args.topic,
            mqtt_username=args.username,
            mqtt_password=args.password,
            log_file=args.log_file,
            max_x_speed=args.max_x_speed,
            max_y_speed=args.max_y_speed,
            max_yaw_speed=args.max_yaw_speed,
            device_config_key=device_config_key,
            reconnect_auto_detect=reconnect_auto_detect,
            reconnect_delay=args.reconnect_delay,
            control_heartbeat_interval=args.control_heartbeat,
            transmit_armed_default=args.transmit_on_start,
        )
        joystick_mqtt.run(publish_interval=args.interval)
    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
