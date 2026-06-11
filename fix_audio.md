# VLAA / Blink500B2+ USB audio fixes (Go2 + Livox LLM stack)

This document records what was done to get stable microphone and speaker access for VLAA (`main.py`) when launched from `startup/tmux.livox.nav.llm.sh`, and how to verify or re-apply fixes.

## Symptoms we started from

- VLAA **Recorder** / **Speaker** logged **device not found** for substrings like `Blink500B2` and `USB Composite Device: Audio` even though `lsusb` showed the hardware.
- After some fixes, **Recorder** ran for ~10s then **sample counters froze** (silent hang) or showed **timeouts / stalls** and periodic **re-inits**.

## Root causes (confirmed)

1. **PulseAudio holding ALSA PCM nodes**  
   Pulse could claim `/dev/snd/pcmC*D*` for those USB devices. VLAA uses **PyAudio → PortAudio → ALSA** and expects to open the hardware directly; with Pulse owning the device, enumeration or open could fail or behave inconsistently.

2. **Boot race**  
   `main.py` could start before ALSA + USB audio were fully ready, so the recorder spun on “device not found” until something else changed.

3. **Orphaned audio processes**  
   After `tmux` restarts, old `audio_recorder` / `audio_speaker` worker processes could survive and keep devices busy.

4. **USB bus and driver**  
   Full-speed isochronous audio can **stall or drop** under load, hub autosuspend, or xhci issues. Kernel logs and `/proc/asound/.../status` help confirm that layer; symptoms can look like frozen sample counts or gaps in `Recorder.log` even when Pulse and startup are correct.

---

## 1. Recommended: dynamic Pulse handoff (Option 1)

**Goal:** PulseAudio owns the Blink mic and the USB Composite speaker **only when VLAA is not running**. While `app_robots/main.py` is up, those cards are temporarily handed over via `pactl suspend-card <card> 1`, and resumed (`... 0`) on exit. This avoids permanently blocking Pulse from those USB devices when VLAA is off.

**Implemented by:** `startup/run_vlaa.sh` + `startup/tmux.livox.nav.llm.sh` in this repo.

### 1.1 Remove any old `PULSE_IGNORE` udev rules (if you installed them)

If you ever added udev rules that set `PULSE_IGNORE` on the Blink or USB Composite gadgets, remove them so Pulse can see the devices again when VLAA is off:

```bash
sudo rm -f /etc/udev/rules.d/89-pulseaudio-ignore-blink500b2.rules \
           /etc/udev/rules.d/90-pulseaudio-ignore-usb-composite.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=sound
sudo udevadm trigger --subsystem-match=usb

pulseaudio -k 2>/dev/null || true
sleep 1
pulseaudio --start 2>/dev/null || true
# (or: systemctl --user restart pulseaudio.service)

# Verify Pulse now sees the cards
pactl list short cards | grep -E 'Blink500B2|10d6_4803|USB_Composite|0909_005b' || \
  echo "Pulse does not see them yet — re-plug USB or reboot."
```

### 1.2 What the wrapper does (`startup/run_vlaa.sh`)

- Waits for the Blink mic (`wait_for_blink500b2.sh`).
- Calls `pactl suspend-card <card> 1` for each card whose Pulse name matches `VLAA_PULSE_CARD_PATTERNS` (default ERE: `Blink500B2|10d6_4803|USB_Composite|0909_005b`).
- After suspend, sets the **USB Composite speaker** ALSA hardware mixer **`PCM` to 100%** (`amixer -c <card> sset PCM 100% unmute`, with a numeric max fallback where needed). See **1.7** for rationale, detection, and overrides.
- Runs `python3 main.py --robot-model go2`.
- On exit (clean, SIGINT, SIGTERM, SIGHUP) resumes those cards via `pactl suspend-card <card> 0`.
- The startup script also does a **safety-net resume** in `kill_previous_children`, in case the wrapper was SIGKILLed before its trap could run.

### 1.3 How `tmux.livox.nav.llm.sh` invokes it

In the `llm` window the command is now:

```bash
VLAA_APP_ROBOTS="$VLAA_APP_ROBOTS" bash "$SCRIPT_DIR/run_vlaa.sh"
```

`SCRIPT_DIR` is the directory of `tmux.livox.nav.llm.sh`, so the wrapper next to it is used.

### 1.4 Override the matched cards (optional)

```bash
# Add another USB headset by VID:PID, plus a name substring:
export VLAA_PULSE_CARD_PATTERNS='Blink500B2|10d6_4803|USB_Composite|0909_005b|0d8c_0014|Logitech_G733'
./startup/tmux.livox.nav.llm.sh
```

If the wrong ALSA card is chosen for the **speaker `PCM` max** step (unusual unless USB enumeration order changes a lot), force the card index:

```bash
export VLAA_ALSA_SPEAKER_CARD=0   # match `aplay -l` / first column of /proc/asound/cards
./startup/tmux.livox.nav.llm.sh
```

### 1.5 Verify the dynamic handoff is working

Run these in another terminal **after** starting the stack:

```bash
# 1. While VLAA is running: those Pulse cards should be in 'suspended' state.
pactl list cards | awk '
  /^Card #/ {card=$0}
  /^\tName: /  {name=$2}
  /^\tDriver: alsa/ {driver=1}
  /^\tProperties:/ {p=1}
  p && /alsa\.card_name|device\.product\.name/ {print card, name, $0}'
pactl list short cards | grep -E 'Blink500B2|10d6_4803|USB_Composite|0909_005b'

# 2. While VLAA is running: VLAA should hold the ALSA PCM nodes
sudo fuser -v /dev/snd/pcmC*c /dev/snd/pcmC*p 2>/dev/null

# 3. Stop VLAA (Ctrl-C the llm pane). The Pulse cards should be back to
#    SUSPENDED state but with no pactl error, and a new pactl playback test
#    should work:
pactl list short sinks   | grep -E 'USB_Composite|0909_005b'
paplay /usr/share/sounds/alsa/Front_Center.wav 2>/dev/null || true
```

In `Recorder.log` / `Speaker.log` you should see clean opens and growing `Number of samples read` while VLAA is running.

### 1.6 Caveats

- Needs PulseAudio to be **running** on the user session that the tmux pane runs in. If Pulse is not present, the wrapper logs `pactl not installed; skipping Pulse handoff` and just runs VLAA — which is fine because there is no Pulse to compete with.
- If a different app **already** has the device open in Pulse (e.g. a browser tab), `suspend-card` releases Pulse's ALSA client but the app may need to re-pick a sink/source.
- Direct ALSA users (`arecord`, another `python` script using `hw:`) still must not run at the same time as VLAA on the same card — same constraint as before.

### 1.7 USB speaker: max ALSA `PCM` on every VLAA start

**Problem:** VLAA plays TTS through **PyAudio → ALSA** on the USB Composite gadget. After Pulse releases the card, playback can still sound **quiet** if the gadget’s **hardware** simple control `PCM` is not at its maximum. Adjusting Pulse sink volume or VLAA YAML `output_volume` often does **not** move that hardware path the same way once you are on direct `hw:` playback.

**What we added:** `startup/run_vlaa.sh` runs `max_speaker_alsa_pcm()` **after** `pactl suspend-card … 1` and **before** `python3 main.py`:

1. Resolve ALSA card index: `VLAA_ALSA_SPEAKER_CARD` if set, otherwise the first line in `/proc/asound/cards` whose long name contains **`USB Composite Device`** (matches the YunChen USB speaker on the Go2 setup used here).
2. Run `amixer -c <card> sset PCM 100% unmute`. If that fails, try the numeric max step (e.g. `312` on the device we tested).
3. Failures are **non-fatal** (wrapper logs a warning and still starts VLAA), e.g. missing `amixer`, no matching card line yet, or a different USB audio layout without a `PCM` control.

**Manual check** (adjust card if needed):

```bash
awk '/USB Composite Device/ {print "card", $1; exit}' /proc/asound/cards
amixer -c 0 sget PCM
# Expect Front L/R at max (e.g. 312 [100%] [0.00dB] [on]) after a fresh run_vlaa start.
```

---

## 2. go2-nav: startup script changes

**File:** `startup/tmux.livox.nav.llm.sh` (and the new `startup/run_vlaa.sh`).

### 2.1 Kill orphaned VLAA processes on stack restart

In `kill_previous_children`, after the ROS pkill list:

```bash
pkill -f '[a]pp_robots/main\.py' 2>/dev/null || true
pkill -f '[p]ython3 main\.py --robot-model' 2>/dev/null || true
pkill -f '[r]un_vlaa\.sh' 2>/dev/null || true
pkill -f '[a]udio_recorder' 2>/dev/null || true
pkill -f '[a]udio_speaker' 2>/dev/null || true
```

…plus a best-effort Pulse resume so a SIGKILL’d wrapper does not leave the cards suspended:

```bash
if command -v pactl >/dev/null 2>&1; then
    pactl list short cards 2>/dev/null \
        | awk '$2 ~ /Blink500B2|10d6_4803|USB_Composite|0909_005b/ {print $2}' \
        | xargs -r -I{} pactl suspend-card {} 0 2>/dev/null || true
fi
```

### 2.2 Gate VLAA + Pulse handoff in the `llm` window

The `llm` pane now invokes the wrapper instead of running Python directly:

```bash
tmux send-keys -t "$SESSION:llm.0" \
  "VLAA_APP_ROBOTS=\"$VLAA_APP_ROBOTS\" bash \"$SCRIPT_DIR/run_vlaa.sh\"" C-m
```

`run_vlaa.sh` itself runs the mic gate and the Pulse suspend/resume — see section 1.

### 2.3 Override the VLAA path

```bash
export VLAA_APP_ROBOTS=/path/to/app_robots
./startup/tmux.livox.nav.llm.sh
```

### 2.4 Run pieces alone (debug / no tmux)

```bash
VLAA="${VLAA_APP_ROBOTS:-$HOME/vlaa/app_robots}"

# Mic gate only (no VLAA, no Pulse handoff)
cd "$VLAA" && bash app_go2/setup/wait_for_blink500b2.sh && echo "mic OK"

# Full wrapper (mic gate + Pulse handoff + python3 main.py)
VLAA_APP_ROBOTS="$VLAA" bash /home/unitree/go2-nav/startup/run_vlaa.sh
```

---

## 3. Verification commands (detailed)

### USB and ALSA

```bash
lsusb
lsusb -t
cat /proc/asound/cards
arecord -l
aplay -l
```

### PulseAudio process (optional)

```bash
pgrep -a pulseaudio || true
pactl info 2>/dev/null | head -20 || true
```

### Who uses which PCM node

Replace card indices with yours from `arecord -l` / `aplay -l`:

```bash
# List all ALSA PCM char devices
ls -l /dev/snd/pcmC*

# Capture (mic) — example card 2, device 0
sudo fuser -v /dev/snd/pcmC2D0c

# Playback (speaker) — example card 0, device 0
sudo fuser -v /dev/snd/pcmC0D0p
```

### Quick capture test (does not need VLAA)

```bash
# Record 3 seconds from default card (-d hw:2,0 if Blink is card 2)
arecord -d 3 -f cd /tmp/test-mic.wav && ls -l /tmp/test-mic.wav
```

### VLAA logs (tail while app runs)

```bash
VLAA="${VLAA_APP_ROBOTS:-$HOME/vlaa/app_robots}"
tail -f "$VLAA/logs/Recorder.log"
# other pane:
tail -f "$VLAA/logs/Speaker.log"
```

Healthy recorder: `Number of samples read` increases every stats line; `Consecutive timeouts` (or read-error counter) stays low. Repeated `Audio stream stalled` + `Reinitializing` means USB/kernel still dropping isoch traffic — see section 4.

### PyAudio probe (same idea as wait script)

```bash
python3 - <<'PY'
import pyaudio
p = pyaudio.PyAudio()
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    name = info.get("name", "")
    if "Blink" in name or "Composite" in name or "Audio" in name:
        print(i, repr(name), "in=", info.get("maxInputChannels"), "out=", info.get("maxOutputChannels"))
p.terminate()
PY
```

---

## 4. If stalls continue — kernel and USB power (detailed)

### 4.1 Kernel log (needs root on restricted systems)

Plain `dmesg` may print `Operation not permitted`; use:

```bash
sudo dmesg -T --since '10 minutes ago' | grep -iE 'usb|xhci|isoch|audio|reset|overflow|error|blink' | tail -80
```

### 4.2 ALSA PCM status while VLAA is recording

Replace `card2` with your Blink capture card from `/proc/asound/cards`:

```bash
sudo cat /proc/asound/card2/pcm0c/sub0/status
```

Interpretation (rough): while capture is healthy, **`hw_ptr`** should increase over time. Streaks where **`hw_ptr` stays flat** while VLAA thinks it is running align with “stall” in `Recorder.log`. **`avail`** stuck at `0` with **`hw_ptr` at `0`** right after start can be a race sample right after re-init — sample again after a few seconds.

### 4.3 xhci interrupt counters (USB1 controller)

Run twice ~30s apart; the count should climb steadily while USB is active:

```bash
grep -E 'xhci|3610000' /proc/interrupts
sleep 30
grep -E 'xhci|3610000' /proc/interrupts
```

Optional one-liner for USB1 IRQ delta over 30s:

```bash
A=$(awk '/xhci-hcd:usb1/ {s=0; for(i=2;i<=NF-3;i++) s+=$i; print s; exit}' /proc/interrupts)
sleep 30
B=$(awk '/xhci-hcd:usb1/ {s=0; for(i=2;i<=NF-3;i++) s+=$i; print s; exit}' /proc/interrupts)
echo "USB1 xhci IRQs in 30s: $((B-A))"
```

### 4.4 Sample PCM status every 200ms for 12s (stall hunting)

Uses `grep` so parsing matches typical ALSA `status` files (`state: RUNNING`, `avail       : N`, etc.).

```bash
CARD=2   # set to your Blink capture card number
for i in $(seq 1 60); do
  ts=$(date +%H:%M:%S)
  echo -n "$ts  "
  sudo grep -E '^(state|hw_ptr|appl_ptr|avail\s)' "/proc/asound/card${CARD}/pcm0c/sub0/status" 2>/dev/null | tr '\n' ' ' || echo "(read failed)"
  echo
  sleep 0.2
done
```

If `hw_ptr` prints the same value for many consecutive lines while VLAA is supposed to be recording, the USB isoch stream is stalled at the kernel/driver layer.

### 4.5 Disable USB autosuspend on the controller, hubs, and devices

**Discover sysfs names** (examples from one robot: `usb1`, `1-3`, `1-3.1`, `1-3.1.2`):

```bash
lsusb -t
ls -d /sys/bus/usb/devices/usb* /sys/bus/usb/devices/[0-9]*-* 2>/dev/null | head -40
```

**Force `power/control` to `on`** for the root hub, intermediate hubs, and leaves (edit the list to match `lsusb -t`):

```bash
for d in usb1 1-3 1-3.1 1-3.1.2; do
  if [ -f "/sys/bus/usb/devices/$d/power/control" ]; then
    echo on | sudo tee "/sys/bus/usb/devices/$d/power/control" >/dev/null
    echo "$d -> $(cat /sys/bus/usb/devices/$d/power/control)"
  else
    echo "$d (no such sysfs node — skip)"
  fi
done
```

These sysfs writes reset on reboot; make a systemd oneshot or udev if you need them permanent.

### 4.6 Hardware / topology

- Try the Blink dongle on a **different USB port** (prefer a top-level port, not through the same internal hub as a heavy isoch device if you can avoid it).
- Check cable / RF dongle placement if dropouts correlate with motion.

---

## 5. File index

| Area | Path |
|------|------|
| Startup (tmux orchestrator) | `go2-nav/startup/tmux.livox.nav.llm.sh` |
| Pulse handoff wrapper | `go2-nav/startup/run_vlaa.sh` |
| VLAA wait script | `$VLAA_APP_ROBOTS/app_go2/setup/wait_for_blink500b2.sh` |
| Device names (config) | e.g. `robot.default.go2.conf.yaml` — `device_name_recorder` / speaker strings must match PyAudio names |

---

*Last updated: 2026-05-15 — documents dynamic Pulse handoff only; no udev `PULSE_IGNORE` recipe and no VLAA `AudioRecorder` patch guidance in this file.*
