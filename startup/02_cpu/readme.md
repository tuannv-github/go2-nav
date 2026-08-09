# Jetson max power (02_cpu)

Locks the Orin NX to **MAXN** and static max CPU / GPU / EMC clocks, plus max fan.

Orin NX modes in `/etc/nvpmodel.conf`:

| ID | Name |
|----|------|
| 0  | MAXN |
| 1  | 10W  |
| 2  | 15W (factory default) |
| 3  | 25W  |

`nvpmodel` persists across reboot (`nvpmodel.service`). `jetson_clocks` does **not** — this unit re-applies clocks every boot, after NVIDIA power services.

## Install (start at boot)

```bash
sudo ./startup/02_cpu/install.sh
```

```bash
systemctl status go2-cpu.service
journalctl -u go2-cpu.service -f
```

Uninstall:

```bash
sudo ./startup/02_cpu/install.sh uninstall
```

## Manual run

```bash
./startup/02_cpu/cpu.sh
./startup/02_cpu/cpu.sh status
```

Tmux stacks still call this via `startup/cpu.sh` (wrapper).
