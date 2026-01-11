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
from list_joystick_devices import find_joystick_device_path


class JoystickReader:
    """Class to read joystick events and send state to queue"""
    
    def __init__(self, device_path, state_queue, running, button_mapping, log_file):
        self.device_path = device_path
        self.state_queue = state_queue
        self.running = running
        self.button_mapping = button_mapping
        self.log_file = log_file
        
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
    
    @staticmethod
    def normalize_axis(value, min_val=-32768, max_val=32767):
        """Normalize axis value to range [-1.0, 1.0]"""
        if value == 0:
            return 0.0
        normalized = (value - min_val) / (max_val - min_val) * 2.0 - 1.0
        # Apply deadzone
        if abs(normalized) < 0.1:
            return 0.0
        return round(normalized, 3)
    
    def update_wireless_controller_state(self):
        """Update WirelessController format from raw axes and buttons"""
        # Map axes to lx, ly, rx, ry
        # Xbox 360: ABS_X = left stick X, ABS_Y = left stick Y
        #           ABS_RX = right stick X, ABS_RY = right stick Y
        # Always update, even if value is 0.0 (to ensure 0.0 is published)
        state = {
            'lx': round(self.axes_raw.get('ABS_X', 0.0), 3),
            'ly': round(-self.axes_raw.get('ABS_Y', 0.0), 3),  # Invert Y axis
            'rx': round(self.axes_raw.get('ABS_RX', 0.0), 3),
            'ry': round(-self.axes_raw.get('ABS_RY', 0.0), 3),  # Invert Y axis
        }
        
        # Encode buttons as uint16 bitfield
        keys = 0
        for button_name, bit_position in self.button_mapping.items():
            if self.buttons_raw.get(button_name, 0):
                keys |= (1 << bit_position)
        
        # Also check for generic button codes
        for button_name, pressed in self.buttons_raw.items():
            if button_name not in self.button_mapping:
                # Try to extract button number from name like BTN_0, BTN_1, etc.
                try:
                    button_name_str = str(button_name)
                    if button_name_str.startswith('BTN_'):
                        btn_num = int(button_name_str.split('_')[1])
                        if btn_num < 16:  # Only use lower 16 bits
                            if pressed:
                                keys |= (1 << btn_num)
                except (ValueError, IndexError, AttributeError):
                    pass
        
            # Special handling:
            # 1. A button only (no other buttons, no ABS_Z=255) -> keys = 4
            # 2. ABS_Z = 255 AND BTN_A -> keys = 288
            # 3. ABS_Z = 255 (without BTN_A) -> keys = 32
            
            abs_z_raw = self.axes_raw_values.get('ABS_Z', 0)
            # Check for both BTN_SOUTH and BTN_A (different controllers may use different names)
            a_button_pressed = self.buttons_raw.get('BTN_SOUTH', 0) or self.buttons_raw.get('BTN_A', 0)
            
            # Check if only A button is pressed (no other buttons)
            other_buttons_pressed = False
            for button_name, pressed in self.buttons_raw.items():
                if pressed and button_name not in ['BTN_SOUTH', 'BTN_A']:
                    other_buttons_pressed = True
                    break
            
            if abs_z_raw >= 255 and a_button_pressed:
                # When ABS_Z=255 AND A button pressed, set key to 288
                keys = 288
                self.logger.debug(f"ABS_Z={abs_z_raw}, BTN_A pressed, setting keys=288")
            elif abs_z_raw >= 255:
                # When ABS_Z=255 (without A button), set key to 32
                keys = 32
                self.logger.debug(f"ABS_Z={abs_z_raw}, BTN_A not pressed, setting keys=32")
            elif a_button_pressed and not other_buttons_pressed and abs_z_raw < 255:
                # A button only (no other buttons, no ABS_Z=255) -> keys = 4
                keys = 4
                self.logger.debug(f"BTN_A only pressed (no other buttons, ABS_Z={abs_z_raw}), setting keys=4")
            # Otherwise, use normal button mapping (keys already calculated above)
        
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
        """Process joystick event and update state"""
        if event.type == ecodes.EV_ABS:
            # Analog stick/trigger event
            if event.code in ecodes.ABS:
                axis_name = ecodes.ABS[event.code]
                # Handle tuple (some codes map to multiple names)
                if isinstance(axis_name, tuple):
                    axis_name = axis_name[0]
                axis_name = str(axis_name)
            else:
                axis_name = f"ABS_{event.code}"
            normalized_value = self.normalize_axis(event.value)
            self.axes_raw[axis_name] = normalized_value
            self.axes_raw_values[axis_name] = event.value  # Store raw value
            self.update_wireless_controller_state()
            self.logger.debug(f"Event: {axis_name} = {event.value} (normalized: {normalized_value})")
            return True
        elif event.type == ecodes.EV_KEY:
            # Button event
            if event.code in ecodes.BTN:
                button_name = ecodes.BTN[event.code]
                # Handle tuple (some codes map to multiple names)
                if isinstance(button_name, tuple):
                    button_name = button_name[0]
                button_name = str(button_name)
            else:
                button_name = f"BTN_{event.code}"
            self.buttons_raw[button_name] = event.value
            self.update_wireless_controller_state()
            button_state = "pressed" if event.value else "released"
            self.logger.debug(f"Event: {button_name} {button_state}")
            return True
        elif event.type == ecodes.EV_SYN:
            # Synchronization event (ignore but don't print)
            return False
        else:
            # Other event types
            event_type_name = ecodes.EV[event.type] if event.type in ecodes.EV else f"EV_{event.type}"
            self.logger.debug(f"Event: {event_type_name} code={event.code} value={event.value}")
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
                            # Log that we received an event
                            self.logger.debug(f"JoystickReader: Received event: type={event.type}, code={event.code}, value={event.value}")
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
        if reason_code == 0:
            logger = logging.getLogger(__name__)
            logger.info("MQTTPublisher: Connected to MQTT broker")
        else:
            logger = logging.getLogger(__name__)
            logger.error(f"MQTTPublisher: Failed to connect to MQTT broker, reason code {reason_code}")
    
    @staticmethod
    def on_disconnect(client, userdata, reason_code, properties=None):
        logger = logging.getLogger(__name__)
        logger.info(f"MQTTPublisher: Disconnected from MQTT broker, reason code: {reason_code}")
    
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
    
    def __init__(self, device_path, mqtt_broker, mqtt_port, mqtt_topic, mqtt_username=None, mqtt_password=None, log_file=None):
        self.device_path = device_path
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.mqtt_topic = mqtt_topic
        self.mqtt_username = mqtt_username
        self.mqtt_password = mqtt_password
        
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
            self.logger.info(f"Found joystick device: {test_device.name}")
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
            state_queue=self.state_queue,
            running=self.running,
            button_mapping=self.button_mapping,
            log_file=self.log_file
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
            log_file=args.log_file
        )
        joystick_mqtt.run(publish_interval=args.interval)
    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
