# Reverse SSH tunnel (03_ssh)

Keeps a reverse tunnel up so the jump host can reach this robot's sshd:

```bash
ssh -N -v -R 4123:localhost:22 master
```

`master` is `fcp@10.1.100.220` in `~/.ssh/config`. Copy the robot key once:

```bash
ssh-copy-id -i ~/.ssh/id_rsa_unitree_robot.pub master
```

From `master` (`10.1.100.220`):

```bash
ssh -p 4123 unitree@127.0.0.1
```

Needs key auth (`BatchMode=yes`). Identity comes from `Host master` (`~/.ssh/id_rsa_unitree_robot`). Password / ssh-agent from a terminal will not be available to systemd.

Extra ssh options vs the one-liner: `ExitOnForwardFailure`, keepalives, `Restart=always`.

## Install (start at boot)

```bash
sudo ./startup/03_ssh/install.sh
```

```bash
systemctl status go2-ssh.service
journalctl -u go2-ssh.service -f
./startup/03_ssh/run_tunnel.sh status
```

Uninstall:

```bash
sudo ./startup/03_ssh/install.sh uninstall
```

## Manual run

```bash
./startup/03_ssh/run_tunnel.sh
```

Override target without editing the unit:

```bash
SSH_TUNNEL_HOST=master ./startup/03_ssh/run_tunnel.sh
```
