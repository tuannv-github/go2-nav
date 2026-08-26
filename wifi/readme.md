# Unitree Go2 Wi-Fi Mesh Monitor & Handover Tool

Real-time signal monitoring, multi-node tracking, and fast handover (roaming) utility designed for the **Unitree Go2** quadruped robot on **TP-Link Deco BE85 (Wi-Fi 7)** mesh networks.

---

## 📁 Files

- **`wifi_mesh.py`**: Core Python script implementing fast single-channel scanning, live BSSID tracking, auto-roaming, Unix domain socket & UDP IPC broadcasting.
- **`wifi_mesh.sh`**: Executable CLI wrapper script.
- **`wifi_console.sh`**: Lightweight IPC terminal client that connects to the background daemon's live socket stream (`/tmp/go2_wifi_mesh.sock`).
- **`install.sh`**: Systemd installation script to enable auto-roaming automatically on boot (`go2-wifi-mesh.service`).
- **`wifi_ho.log`**: Persistent disk log recording all manual & auto-roam handover events.

---

## 🚀 Quick Start

### 1. Install & Enable Startup Service (Recommended)
Run `install.sh` to install the `go2-wifi-mesh.service` systemd daemon. Auto-roaming will start automatically on boot:
```bash
sudo /home/unitree/go2-nav/wifi/install.sh
```

### 2. View Live Console Stream (IPC Client)
Connect to the background daemon's live Unix socket stream (`/tmp/go2_wifi_mesh.sock`) to view the dashboard without starting another monitor process:
```bash
/home/unitree/go2-nav/wifi/wifi_console.sh
```

### 3. Live Continuous Monitor (Manual CLI)
Runs an interactive dashboard updating every second with live signal bars and link bitrates:
```bash
./wifi_mesh.sh
# or from any path:
/home/unitree/go2-nav/wifi/wifi_mesh.sh
```
*(Press `Ctrl+C` to exit cleanly)*

### 4. Single Snapshot
Takes an instant reading and exits immediately:
```bash
./wifi_mesh.sh --once
```

### 5. Custom Refresh Interval
Update at a custom interval (e.g., every 0.5 seconds or 2 seconds):
```bash
./wifi_mesh.sh -i 0.5
```

### 6. Smart Auto-Roaming Mode
Automatically hands over to a significantly stronger AP whenever active signal drops below threshold (default `-65 dBm` and candidate is `+8 dB` stronger):
```bash
./wifi_mesh.sh --auto-roam
# Custom threshold (-70 dBm) and delta (+6 dB):
./wifi_mesh.sh -a -t -70 -d 6
```

### 7. Instant Manual Handover (HO) to a Specific Node
Force the robot to immediately switch to a target node:
```bash
./wifi_mesh.sh --roam 18:69:45:84:FB:EB
```

---

## 📡 Lab Mesh Topology (TP-Link Deco BE85)

All nodes operate on **5 GHz Channel 36 (5180 MHz)** under the **`FCCLab`** SSID:

| Node | Physical Unit | 5 GHz BSSID (MAC) | 2.4 GHz BSSID | Role |
| :--- | :--- | :--- | :--- | :--- |
| **Node 1** | Main Deco Unit | `18:69:45:84:FB:EB` | `18:69:45:84:FB:EA` | Gateway Mesh Node |
| **Node 2** | Satellite Unit 1 | `18:69:45:84:FC:45` | `18:69:45:84:FC:44` | Mid-Lab Mesh Node |
| **Node 3** | Satellite Unit 2 | `18:69:45:84:FB:0D` | `18:69:45:84:FB:0C` | End-Lab Mesh Node |

---

## 📊 Dashboard Display Breakdown

```text
======================================================================================
       📶  UNITREE GO2 WI-FI 5GHz MESH SIGNAL & HANDOVER (HO) MONITOR
======================================================================================
Active Network:  FCCLab  |  Robot IP: 10.1.100.210  |  Mesh: TP-Link Deco BE85 (3 Nodes)
Active BSSID:    18:69:45:84:FC:45 (Mesh Node 2 (5GHz))  |  Channel: CH 36 (5 GHz)
Link Bitrate:    RX: 1080.6 MBit/s  |  TX: 1200.9 MBit/s
--------------------------------------------------------------------------------------

STATE         NODE / IDENTITY              BSSID (MAC)          BAND & CHANNEL     SIGNAL STRENGTH         
-----------------------------------------------------------------------------------------------------------
[ACTIVE]      Mesh Node 2 (5GHz)           18:69:45:84:FC:45    CH 36 (5 GHz)       -47 dBm  [████████] 100%
 CANDIDATE    Mesh Node 1 (5GHz)           18:69:45:84:FB:EB    CH 36 (5 GHz)       -77 dBm  [██░░░░░░]  26%
 [OUT OF RANGE] Mesh Node 3 (5GHz)         18:69:45:84:FB:0D    CH 36 (5 GHz)        N/A dBm  [░░░░░░░░]   0% (OUT OF RANGE)
```

- **`[ACTIVE]` (Bright Green):** Currently associated mesh node with real-time TX/RX link metrics.
- **`CANDIDATE` (Bright White):** Reachable roaming targets with active signal bars.
- **`[WEAK]` / `[OUT OF RANGE]` (Light Gray):** Nodes with signal below `-85 dBm` or out of range.

---

## ⚙️ Wi-Fi Configuration Commands

### Lock Robot to 5 GHz Only (Recommended for Mesh)
Prevents the robot from ever degrading to 2.4 GHz while allowing roaming across all 5 GHz nodes:
```bash
sudo nmcli connection modify "FCCLab" 802-11-wireless.band a
sudo nmcli connection up "FCCLab"
```

### Pin to One Specific AP (Disable Roaming)
Lock the robot strictly to one AP MAC address:
```bash
sudo nmcli connection modify "FCCLab" 802-11-wireless.bssid "18:69:45:84:FB:EB"
sudo nmcli connection up "FCCLab"
```

### Revert to Auto-Roaming
```bash
sudo nmcli connection modify "FCCLab" 802-11-wireless.bssid ""
sudo nmcli connection up "FCCLab"
```

---

## 🔧 Technical Details & Optimization

1. **Targeted Single-Frequency Fast Scan (`freq=5180`):**
   - Standard full-spectrum scans check 30+ channels (~1000 ms, causes audio/video jitter).
   - This tool scans **strictly 5180 MHz**, completing in **~150 ms** without the Wi-Fi radio ever leaving Channel 36.
   - **Zero packet loss** for ROS 2 DDS telemetry, camera streams, or SSH sessions during active monitoring.

2. **Fast Transition Handover (802.11r FT-PSK):**
   - Active key management: `WPA-PSK FT-PSK WPA-PSK-SHA256`.
   - Pre-cached cryptographic handshakes enable sub-50ms handovers between Deco BE85 nodes without TCP socket drops.
