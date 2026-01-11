#!/usr/bin/env python3
"""
List available joystick/gamepad devices on the system.
"""

import sys
import os
import glob

# Try to import evdev, with helpful error message if not available
try:
    from evdev import InputDevice, ecodes
except ImportError:
    print("Error: 'evdev' module not found.", file=sys.stderr)
    print("\nThis script requires the 'evdev' Python package.", file=sys.stderr)
    
    # Check if we're in the joystick_controller directory and venv exists
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(script_dir, 'venv', 'bin', 'python3')
    
    if os.path.exists(venv_python):
        print(f"\n✓ Found virtual environment at: {os.path.dirname(venv_python)}", file=sys.stderr)
        print("\nTo use the virtual environment:", file=sys.stderr)
        print(f"  {venv_python} {__file__}", file=sys.stderr)
        print("\nOr activate the venv first:", file=sys.stderr)
        print("  source venv/bin/activate", file=sys.stderr)
        print("  python3 list_joystick_devices.py", file=sys.stderr)
    else:
        print("\nIf you're using a virtual environment:", file=sys.stderr)
        print("  ./venv/bin/python3 list_joystick_devices.py", file=sys.stderr)
        print("\nOr activate the venv first:", file=sys.stderr)
        print("  source venv/bin/activate", file=sys.stderr)
        print("  python3 list_joystick_devices.py", file=sys.stderr)
    
    print("\nIf you need to install evdev system-wide:", file=sys.stderr)
    print("  sudo pip3 install evdev", file=sys.stderr)
    print("\nOr install in venv:", file=sys.stderr)
    print("  pip install evdev", file=sys.stderr)
    sys.exit(1)

def is_gamepad_device(device, caps):
    """Check if a device is a gamepad/joystick based on its capabilities"""
    # Skip if it doesn't have both ABS and KEY (gamepads need both)
    if ecodes.EV_ABS not in caps or ecodes.EV_KEY not in caps:
        return False
    
    abs_caps = caps[ecodes.EV_ABS]
    key_caps = caps[ecodes.EV_KEY] if ecodes.EV_KEY in caps else []
    
    # Check for gamepad/joystick characteristics:
    # 1. Has analog stick axes (ABS_X, ABS_Y, ABS_RX, ABS_RY)
    # 2. Has multiple buttons (more than just a few keys)
    # 3. Exclude keyboards (which have many keys but no analog sticks)
    # 4. Exclude mice (which have ABS_X/ABS_Y but are relative, not absolute)
    
    has_analog_sticks = any(code in abs_caps for code in [
        ecodes.ABS_X, ecodes.ABS_Y, 
        ecodes.ABS_RX, ecodes.ABS_RY,
        ecodes.ABS_HAT0X, ecodes.ABS_HAT0Y  # D-pad
    ])
    
    # Count gamepad buttons (not all keys, just gamepad buttons)
    button_count = 0
    if ecodes.EV_KEY in caps:
        # Count BTN_* codes which are gamepad buttons
        button_count = sum(1 for code in key_caps if code >= ecodes.BTN_MISC and code < ecodes.BTN_DIGI)
    
    # Also check for triggers (ABS_Z, ABS_RZ) which are common in gamepads
    has_triggers = any(code in abs_caps for code in [ecodes.ABS_Z, ecodes.ABS_RZ])
    
    # Consider it a gamepad if:
    # - Has analog sticks, OR
    # - Has triggers and multiple buttons, OR  
    # - Has multiple buttons (>= 8) and some ABS axes
    is_gamepad = (
        has_analog_sticks or
        (has_triggers and button_count >= 4) or
        (button_count >= 8 and len(abs_caps) >= 2)
    )
    
    # Exclude devices that look like keyboards (many keys, no analog sticks)
    if not has_analog_sticks and button_count > 20:
        return False
    
    return is_gamepad

def find_joystick_device_path():
    """Find and return the first available joystick device path"""
    import glob
    
    # Check /dev/input/js* devices first (these are always joysticks)
    js_devices = glob.glob('/dev/input/js*')
    for path in sorted(js_devices):
        try:
            device = InputDevice(path)
            return path
        except Exception:
            continue
    
    # Check /dev/input/event* devices (for Xbox controllers, etc.)
    event_devices = glob.glob('/dev/input/event*')
    for path in sorted(event_devices):
        try:
            device = InputDevice(path)
            caps = device.capabilities()
            if is_gamepad_device(device, caps):
                return path
        except PermissionError:
            continue
        except Exception:
            continue
    
    return None

def list_joystick_devices():
    """List all available joystick/gamepad devices"""
    print("Scanning for joystick/gamepad devices...\n")
    
    devices_found = []
    
    # Check /dev/input/js* devices
    js_devices = glob.glob('/dev/input/js*')
    for path in sorted(js_devices):
        try:
            device = InputDevice(path)
            devices_found.append((path, device.name, device.capabilities()))
            print(f"✓ Found: {device.name}")
            print(f"  Path: {path}")
            print(f"  Capabilities: {list(device.capabilities().keys())}")
            print()
        except Exception as e:
            print(f"✗ Error reading {path}: {e}")
            print()
    
    # Check /dev/input/event* devices (for Xbox controllers, etc.)
    event_devices = glob.glob('/dev/input/event*')
    for path in sorted(event_devices):
        try:
            device = InputDevice(path)
            caps = device.capabilities()
            
            # Use the shared gamepad detection function
            if is_gamepad_device(device, caps):
                # Get details for display
                abs_caps = caps[ecodes.EV_ABS]
                key_caps = caps[ecodes.EV_KEY] if ecodes.EV_KEY in caps else []
                has_analog_sticks = any(code in abs_caps for code in [
                    ecodes.ABS_X, ecodes.ABS_Y, 
                    ecodes.ABS_RX, ecodes.ABS_RY,
                    ecodes.ABS_HAT0X, ecodes.ABS_HAT0Y
                ])
                button_count = sum(1 for code in key_caps if code >= ecodes.BTN_MISC and code < ecodes.BTN_DIGI) if ecodes.EV_KEY in caps else 0
                has_triggers = any(code in abs_caps for code in [ecodes.ABS_Z, ecodes.ABS_RZ])
                devices_found.append((path, device.name, caps))
                print(f"✓ Found: {device.name}")
                print(f"  Path: {path}")
                print(f"  Type: Gamepad/Joystick (event device)")
                print(f"  Analog sticks: {has_analog_sticks}")
                print(f"  Triggers: {has_triggers}")
                print(f"  Buttons: {button_count}")
                print(f"  Capabilities: {list(caps.keys())}")
                print()
        except PermissionError:
            # Skip devices we don't have permission to read
            continue
        except Exception as e:
            # Skip other errors silently
            continue
    
    if not devices_found:
        print("✗ No joystick/gamepad devices found.")
        print("\nTroubleshooting:")
        print("  1. Make sure your joystick/gamepad is connected")
        print("  2. Check if you have permission to read /dev/input/*")
        print("  3. Try running with sudo or add your user to the 'input' group:")
        print("     sudo usermod -aG input $USER")
        print("     (then log out and log back in)")
        return None
    
    print(f"\nTotal devices found: {len(devices_found)}")
    print("\nRecommended device (first found):")
    if devices_found:
        path, name, _ = devices_found[0]
        print(f"  {path} ({name})")
    
    return devices_found


if __name__ == '__main__':
    list_joystick_devices()
