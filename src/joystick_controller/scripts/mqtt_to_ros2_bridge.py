#!/usr/bin/env python3
"""
MQTT to ROS2 bridge for wireless controller messages.

Subscribes to MQTT topic /wirelesscontroller and publishes to ROS2 topic /wirelesscontroller
"""

import json
import sys
import time
import rclpy
from rclpy.node import Node
from unitree_go.msg import WirelessController
import paho.mqtt.client as mqtt


class MQTTToROS2Bridge(Node):
    """Bridge node that subscribes to MQTT and publishes to ROS2."""

    def __init__(self):
        super().__init__('mqtt_to_ros2_bridge')
        
        # Declare parameters
        self.declare_parameter('mqtt_broker', 'localhost')
        self.declare_parameter('mqtt_port', 1883)
        self.declare_parameter('mqtt_topic', '/wirelesscontroller')
        self.declare_parameter('mqtt_client_id', 'joystick_controller_bridge')
        self.declare_parameter('ros2_topic', '/wirelesscontroller')
        self.declare_parameter('mqtt_retry_interval', 5.0)  # seconds between retries
        self.declare_parameter('mqtt_connect_timeout', 10.0)  # connection timeout in seconds
        
        # Get parameters
        self.mqtt_broker = self.get_parameter('mqtt_broker').get_parameter_value().string_value
        self.mqtt_port = self.get_parameter('mqtt_port').get_parameter_value().integer_value
        self.mqtt_topic = self.get_parameter('mqtt_topic').get_parameter_value().string_value
        mqtt_client_id = self.get_parameter('mqtt_client_id').get_parameter_value().string_value
        ros2_topic = self.get_parameter('ros2_topic').get_parameter_value().string_value
        self.mqtt_retry_interval = self.get_parameter('mqtt_retry_interval').get_parameter_value().double_value
        self.mqtt_connect_timeout = self.get_parameter('mqtt_connect_timeout').get_parameter_value().double_value
        
        self.get_logger().info(f'MQTT Broker: {self.mqtt_broker}:{self.mqtt_port}')
        self.get_logger().info(f'MQTT Topic: {self.mqtt_topic}')
        self.get_logger().info(f'ROS2 Topic: {ros2_topic}')
        
        # Create ROS2 publisher
        self.publisher_ = self.create_publisher(WirelessController, ros2_topic, 10)
        
        # Setup MQTT client with new callback API version
        try:
            # Use VERSION2 if available, fallback to VERSION1
            callback_version = getattr(mqtt.CallbackAPIVersion, 'VERSION2', mqtt.CallbackAPIVersion.VERSION1)
            self.mqtt_client = mqtt.Client(
                callback_api_version=callback_version,
                client_id=mqtt_client_id
            )
        except AttributeError:
            # Fallback for older paho-mqtt versions
            self.mqtt_client = mqtt.Client(client_id=mqtt_client_id)
        
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        self.mqtt_connected = False
        self.mqtt_connecting = False  # Flag to prevent multiple simultaneous connection attempts
        
        # Start connection attempt (non-blocking)
        self.mqtt_client.loop_start()
        self.connect_mqtt_with_retry()
    
    def connect_mqtt_with_retry(self):
        """Attempt to connect to MQTT broker with retry logic."""
        # Cancel existing timer if it exists
        if hasattr(self, '_mqtt_retry_timer'):
            try:
                self._mqtt_retry_timer.cancel()
            except:
                pass
        # Create new retry timer
        self._mqtt_retry_timer = self.create_timer(self.mqtt_retry_interval, self._attempt_mqtt_connection)
        # Try immediate connection
        self._attempt_mqtt_connection()
    
    def _attempt_mqtt_connection(self):
        """Internal method to attempt MQTT connection."""
        if self.mqtt_connected:
            # Cancel retry timer if connected
            if hasattr(self, '_mqtt_retry_timer'):
                self._mqtt_retry_timer.cancel()
            return
        
        # Prevent multiple simultaneous connection attempts
        if self.mqtt_connecting:
            return
        
        self.mqtt_connecting = True
        try:
            # Disconnect any existing connection attempt first
            try:
                self.mqtt_client.disconnect()
            except:
                pass
            
            # Attempt connection (blocking call, but should fail quickly if connection refused)
            # If it doesn't raise an exception, the connection attempt is in progress
            # and on_connect callback will be called with the result
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, int(self.mqtt_connect_timeout))
            # If we get here, connection attempt was initiated (may still fail)
            # The on_connect callback will handle the result
        except (ConnectionRefusedError, OSError) as e:
            # Connection refused at TCP level - immediate failure
            self.mqtt_connecting = False
            self.get_logger().warn(f'Connection refused to {self.mqtt_broker}:{self.mqtt_port}. Retrying in {self.mqtt_retry_interval}s...')
        except Exception as e:
            # Other connection errors
            self.mqtt_connecting = False
            self.get_logger().warn(f'Failed to connect to MQTT broker: {e}. Retrying in {self.mqtt_retry_interval}s...')
    
    def on_mqtt_connect(self, client, userdata, flags, rc, *args):
        """Callback when MQTT client connects."""
        self.mqtt_connecting = False
        if rc == 0:
            self.mqtt_connected = True
            # Cancel retry timer
            if hasattr(self, '_mqtt_retry_timer'):
                self._mqtt_retry_timer.cancel()
            client.subscribe(self.mqtt_topic)
            self.get_logger().info(f'✓ Connected to MQTT broker and subscribed to {self.mqtt_topic}')
        else:
            self.mqtt_connected = False
            error_messages = {
                1: "incorrect protocol version",
                2: "invalid client identifier",
                3: "server unavailable",
                4: "bad username or password",
                5: "not authorised"
            }
            error_msg = error_messages.get(rc, f"unknown error code {rc}")
            self.get_logger().error(f'Failed to connect to MQTT broker: {error_msg} (code {rc})')
    
    def on_mqtt_message(self, client, userdata, msg):
        """Callback when MQTT message is received."""
        try:
            # Parse JSON message
            payload = msg.payload.decode('utf-8')
            data = json.loads(payload)
            
            # Create ROS2 message
            ros2_msg = WirelessController()
            
            # Extract values from JSON (handle different possible formats)
            if isinstance(data, dict):
                ros2_msg.lx = float(data.get('lx', 0.0))
                ros2_msg.ly = float(data.get('ly', 0.0))
                ros2_msg.rx = float(data.get('rx', 0.0))
                ros2_msg.ry = float(data.get('ry', 0.0))
                ros2_msg.keys = int(data.get('keys', 0))
            elif isinstance(data, list) and len(data) >= 5:
                # Handle list format: [lx, ly, rx, ry, keys]
                ros2_msg.lx = float(data[0])
                ros2_msg.ly = float(data[1])
                ros2_msg.rx = float(data[2])
                ros2_msg.ry = float(data[3])
                ros2_msg.keys = int(data[4])
            else:
                self.get_logger().warn(f'Unexpected message format: {payload}')
                return
            
            # Publish to ROS2
            self.publisher_.publish(ros2_msg)
            self.get_logger().debug(
                f'Published: lx={ros2_msg.lx}, ly={ros2_msg.ly}, '
                f'rx={ros2_msg.rx}, ry={ros2_msg.ry}, keys={ros2_msg.keys}'
            )
            
        except json.JSONDecodeError as e:
            self.get_logger().error(f'Failed to parse JSON message: {e}')
        except (KeyError, ValueError, TypeError) as e:
            self.get_logger().error(f'Failed to extract data from message: {e}')
        except Exception as e:
            self.get_logger().error(f'Unexpected error: {e}')
    
    def on_mqtt_disconnect(self, client, userdata, rc, *args):
        """Callback when MQTT client disconnects."""
        self.mqtt_connected = False
        self.mqtt_connecting = False
        if rc != 0:
            self.get_logger().warn('Unexpected MQTT disconnection. Will attempt to reconnect...')
            # Restart retry timer
            self.connect_mqtt_with_retry()
        else:
            self.get_logger().info('MQTT client disconnected')
    
    def destroy_node(self):
        """Cleanup on node destruction."""
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        super().destroy_node()


def main(args=None):
    """Main function."""
    rclpy.init(args=args)
    
    node = MQTTToROS2Bridge()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
