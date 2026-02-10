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
import requests
import threading
import paho.mqtt.client as mqtt

# Import device detection functions from list_joystick_devices
# Always use shared detection - required dependency
script_dir = os.path.dirname(os.path.abspath(__file__))
list_devices_path = os.path.join(script_dir, 'list_joystick_devices.py')
if not os.path.exists(list_devices_path):
    raise FileNotFoundError(f"Required file not found: {list_devices_path}")

# Add the directory to path to import the module
sys.path.insert(0, script_dir)
from list_joystick_devices import find_joystick_device_path


# Device configurations mapping patterns in device names to specific settings
DEVICE_CONFIGS = {
    "EasySMX": {
        "lx": (ecodes.EV_ABS, ecodes.ABS_X),
        "ly": (ecodes.EV_ABS, ecodes.ABS_Y),
        "rx": (ecodes.EV_ABS, ecodes.ABS_RX),
        "ry": (ecodes.EV_ABS, ecodes.ABS_RY),
        "l2": (ecodes.EV_KEY, ecodes.BTN_TL2),
        "btn_a": (ecodes.EV_KEY, ecodes.BTN_SOUTH),
        "btn_y": (ecodes.EV_KEY, ecodes.BTN_NORTH),
        "axis_min": -32768,
        "axis_max": 32767,
    },
    "Logitech": {
        "lx": (ecodes.EV_ABS, ecodes.ABS_X),
        "ly": (ecodes.EV_ABS, ecodes.ABS_Y),
        "rx": (ecodes.EV_ABS, ecodes.ABS_Z),
        "ry": (ecodes.EV_ABS, ecodes.ABS_RZ),
        "l2": (ecodes.EV_KEY, 294),
        "btn_a": (ecodes.EV_KEY, 289),
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
        "btn_y": (ecodes.EV_KEY, ecodes.BTN_Y),
        "axis_min": 0,
        "axis_max": 255,
    }
}


class JoystickReader:
    """Class to read joystick events and send state to queue"""
    
    def __init__(self, device_path, device_name, state_queue, running, button_mapping, log_file,
                 max_x_speed=1.0, max_y_speed=1.0, max_yaw_speed=1.0):
        self.device_path = device_path
        self.device_name = device_name
        self.state_queue = state_queue
        self.running = running
        self.button_mapping = button_mapping
        self.log_file = log_file
        self.max_x_speed = max_x_speed
        self.max_y_speed = max_y_speed
        self.max_yaw_speed = max_yaw_speed
        
        # Internal state
        self.axes_raw = {}
        self.axes_raw_values = {}
        self.buttons_raw = {}
        
        # Configure mapping and normalization based on device name
        config = DEVICE_CONFIGS["DEFAULT"]  # Start with default

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
       
        # Configure mapping and normalization based on device name
        self.config = DEVICE_CONFIGS["DEFAULT"]  # Start with default
        
        for pattern, device_config in DEVICE_CONFIGS.items():
            if pattern != "DEFAULT" and pattern in self.device_name:
                self.config = device_config
                self.logger.info(f"JoystickReader: Applied {pattern} configuration")
                break
        
        self.axis_min = self.config["axis_min"]
        self.axis_max = self.config["axis_max"]
        
        # Rate limiting for anomaly detection
        self.last_anomaly_trigger_time = 0
        self.anomaly_lock = threading.Lock()
        
        # Current normalized state of axes and special buttons
        self.controller_state = {
            'lx': 0.0, 'ly': 0.0, 'rx': 0.0, 'ry': 0.0, 'btn_a': 0, 'btn_b': 0,
            'btn_x': 0, 'btn_y': 0, 'l1': 0, 'r1': 0, 'l2': 0
        }
        
        # Build event_map from config roles
        self.event_map = {}
        # Support a wide range of roles
        roles = ['lx', 'ly', 'rx', 'ry', 'btn_a', 'btn_b', 'btn_x', 'btn_y', 'l1', 'r1', 'l2']
        for role in roles:
            etype, ecode = self.config.get(role, (None, None))
            if etype is not None and ecode is not None:
                self.event_map[(etype, ecode)] = role
        
        # Build button part of event_map from button_mapping
        for btn_name, bit_pos in self.button_mapping.items():
            if hasattr(ecodes, btn_name):
                code = getattr(ecodes, btn_name)
                self.event_map[(ecodes.EV_KEY, code)] = ('key', bit_pos)

    def send_anomaly_command(self, action):
        """Send POST request to anomaly demo API
        action: 'detected', 'ignore', or 'accept'
        """
        # Rate limiting mainly to prevent accidental double-presses
        # For 'detected', we might want slightly longer debounce
        now = time.time()
        
        with self.anomaly_lock:
            # Simple debounce of 1.0s for all actions to prevent double-sends
            if now - self.last_anomaly_trigger_time < 0.5:
                # self.logger.debug(f"Action {action} skipped (debounce)")
                return
            self.last_anomaly_trigger_time = now

        url = f'http://10.1.101.216:8081/api/demo/anomaly/{action}'
        headers = {'accept': 'application/json'}
        
        def send_request():
            try:
                self.logger.info(f"************* Sending anomaly command: {action} ({url})")
                response = requests.post(url, headers=headers, data='', timeout=5)
                self.logger.info(f"************* Anomaly {action} response: {response.status_code} - {response.text}")
            except Exception as e:
                self.logger.error(f"************* Error calling anomaly {action} API: {e}")
        
        threading.Thread(target=send_request, daemon=True).start()

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
        
        # Special Unitree-style key logic:
        # Use the mapped A button state
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
        try:
            self.state_queue.put_nowait(state)
            self.logger.debug(f"JoystickReader: Put state in queue: {state}")
        except Exception as e:
            # Queue is full, try to get one and put new one
            try:
                self.state_queue.get_nowait()
                self.state_queue.put_nowait(state)
                self.logger.debug(f"JoystickReader: Queue was full, dropped old state, put new: {state}")
            except Exception as e2:
                self.logger.warning(f"JoystickReader: Failed to put state in queue: {e2}")
    
    def process_event(self, event):
        """Process joystick event and update state using role-based event_map"""
        # Log all events as requested
        self.logger.info(f"JoystickReader: Received event: type={event.type}, code={event.code}, value={event.value}")
        
        mapping = self.event_map.get((event.type, event.code))
        
        if mapping:
            if event.type == ecodes.EV_ABS:
                self.logger.debug(f"Axis event: role={mapping}, code={event.code}, value={event.value}")
                
                # Update normalized value in controller_state
                normalized_value = self.normalize_axis(event.value)
                self.controller_state[mapping] = normalized_value
                
                self.update_wireless_controller_state()
                return True
                
            elif mapping.startswith('btn_') or mapping in ['l1', 'r1', 'l2', 'select', 'start', 'mode', 'l3', 'r3']:
                self.controller_state[mapping] = event.value
                self.update_wireless_controller_state()
                
                # Trigger anomaly detection actions
                if event.value == 1:  # Button press only
                    if mapping == 'btn_y':
                        self.send_anomaly_command('detected')
                    elif mapping == 'btn_x':
                        self.send_anomaly_command('ignore')
                    elif mapping == 'btn_b':
                        self.send_anomaly_command('accept')
                    
                return True
                
            elif isinstance(mapping, tuple) and mapping[0] == 'key':
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
                self.update_wireless_controller_state()
                return True
        
        elif event.type == ecodes.EV_SYN:
            return False
            
        return False
    
    def run(self):
        """Main loop to read joystick events"""
        self.logger.info("JoystickReader: Started, waiting for events...")
        
        device = None
        try:
            # Open device
            device = InputDevice(self.device_path)
            self.logger.info(f"JoystickReader: Opened joystick device: {device.name}")
            self.logger.info(f"JoystickReader: Device capabilities: {list(device.capabilities().keys())}")
            
            # Try to grab device exclusively to prevent other processes from reading it
            # Note: Some devices may not support grabbing, or it might prevent events
            try:
                device.grab()
                self.logger.info("JoystickReader: Grabbed device exclusively")
            except Exception as grab_error:
                self.logger.warning(f"JoystickReader: Could not grab device (may already be in use): {grab_error}")
                self.logger.info("JoystickReader: Continuing without grab...")
            
            # Send initial state (all zeros) to queue
            initial_state = {'lx': 0.0, 'ly': 0.0, 'rx': 0.0, 'ry': 0.0, 'keys': 0}
            try:
                self.state_queue.put_nowait(initial_state)
                self.logger.debug("JoystickReader: Sent initial state to queue")
            except:
                pass
            
            # Log that we're entering the read loop
            self.logger.info("JoystickReader: Entering read loop, waiting for events...")
            
            # Use select-based reading to avoid blocking issues
            
            iteration = 0
            while self.running.value:
                try:
                    # Check if device is still valid
                    if not device.fd:
                        self.logger.error("JoystickReader: Device file descriptor is invalid")
                        break
                    
                    # Use select to check if events are available (non-blocking check)
                    r, w, x = select.select([device.fd], [], [], 0.1)
                    if r:
                        # Events available, read them
                        for event in device.read():
                            if not self.running.value:
                                self.logger.info("JoystickReader: Stopping (running=False)")
                                break
                            self.process_event(event)
                    else:
                        # No events, log periodically to show we're alive
                        iteration += 1
                        if iteration % 50 == 0:  # Every 5 seconds (50 * 0.1s)
                            self.logger.debug(f"JoystickReader: Still waiting for events (iteration {iteration})")
                except OSError as e:
                    # Device might have been disconnected
                    self.logger.error(f"JoystickReader: Device error: {e}", exc_info=True)
                    break
                except Exception as e:
                    self.logger.error(f"JoystickReader: Error in read loop: {e}", exc_info=True)
                    time.sleep(0.1)
        except Exception as e:
            self.logger.error(f"JoystickReader: Fatal error: {e}", exc_info=True)
        finally:
            if device:
                try:
                    device.ungrab()
                    self.logger.debug("JoystickReader: Ungrabbed device")
                except:
                    pass
                try:
                    device.close()
                except:
                    pass
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
                 max_x_speed=1.0, max_y_speed=1.0, max_yaw_speed=1.0):
        self.device_path = device_path
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.mqtt_topic = mqtt_topic
        self.mqtt_username = mqtt_username
        self.mqtt_password = mqtt_password
        self.max_x_speed = max_x_speed
        self.max_y_speed = max_y_speed
        self.max_yaw_speed = max_yaw_speed
        
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
            max_yaw_speed=self.max_yaw_speed
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
                       help='Joystick device path (e.g., /dev/input/js0). Auto-detect if not specified')
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
    parser.add_argument('--log-file', '-l', type=str, default=None,
                       help='Log file path (default: joystick_mqtt.py.log)')
    parser.add_argument('--max-x-speed', type=float, default=0.5,
                       help='Max X speed in m/s (default: 0.5)')
    parser.add_argument('--max-y-speed', type=float, default=0.5,
                       help='Max Y speed in m/s (default: 0.5)')
    parser.add_argument('--max-yaw-speed', type=float, default=0.5,
                       help='Max Yaw speed in rad/s (default: 0.5)')
    
    args = parser.parse_args()
    
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
        else:
            # Log the detected device name
            try:
                device = InputDevice(device_path)
                logging.info(f"Auto-detected joystick device: {device.name} at {device_path}")
            except Exception as e:
                logging.warning(f"Found device path {device_path} but couldn't open it: {e}")
    
    logging.info(f"Using joystick device: {device_path}")
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
            max_yaw_speed=args.max_yaw_speed
        )
        joystick_mqtt.run(publish_interval=args.interval)
    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
