#!/bin/bash
# Wi-Fi Mesh Monitor IPC Console Reader (Unix Domain Socket /tmp/go2_wifi_mesh.sock & UDP fallback)
# Location: /home/unitree/go2-nav/wifi/wifi_console.sh

SOCK_PATH=${1:-"/tmp/go2_wifi_mesh.sock"}
UDP_PORT=9999

echo -e "\033[1;36m[*] Connecting to Wi-Fi Mesh IPC Console Stream (${SOCK_PATH})...\033[0m"
echo -e "\033[90m[Press Ctrl+C to exit viewer]\033[0m"
sleep 0.3

python3 -c "
import socket
import sys
import os
import time

sock_path = '${SOCK_PATH}'
udp_port = ${UDP_PORT}

print('\033[2J\033[H', end='')

while True:
    try:
        if os.path.exists(sock_path):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(5.0)
            try:
                s.connect(sock_path)
            except Exception:
                time.sleep(0.5)
                continue

            while True:
                try:
                    data = s.recv(65535)
                    if not data:
                        break
                    print(data.decode('utf-8', errors='ignore'), end='')
                    sys.stdout.flush()
                except socket.timeout:
                    continue
                except Exception:
                    break
            s.close()
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.settimeout(5.0)
            try:
                s.bind(('127.0.0.1', udp_port))
            except Exception:
                time.sleep(0.5)
                continue

            while True:
                try:
                    data, _ = s.recvfrom(65535)
                    print(data.decode('utf-8', errors='ignore'), end='')
                    sys.stdout.flush()
                except socket.timeout:
                    continue
                except Exception:
                    break
            s.close()
    except KeyboardInterrupt:
        print('\n\033[92m[✓] Exited viewer cleanly.\033[0m')
        sys.exit(0)
    except Exception:
        time.sleep(0.5)
"
