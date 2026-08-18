# sclite-scheduler

Switches Goldshell miners between power plans (e.g. "Hashrate Mode" / "Idle
Mode") on a schedule, across multiple devices, driven by a config file.

Works against any Goldshell device that exposes the same web API as the
SC-LITE (`/user/login`, `/mcb/setting`) - the login/encryption scheme and
power-plan control were reverse-engineered from that device's web UI.

## Setup (Linux)

If this is running on a dedicated machine/container (e.g. its own LXC), a venv
is unnecessary overhead - just install straight to the system Python:

```bash
cd sclite-scheduler
pip3 install -r requirements.txt
# if that errors with "externally-managed-environment" (Debian 12+/Ubuntu 23.04+):
#   pip3 install -r requirements.txt --break-system-packages

cp config.example.yaml config.yaml
chmod 600 config.yaml   # it contains plaintext admin passwords - keep it locked down
$EDITOR config.yaml
```

If instead this shares a machine with other Python projects, use a venv to
avoid dependency conflicts:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

(the cron/systemd examples below assume a venv at `venv/bin/python3` - swap
in plain `python3`/`pip3 install --user` paths if you skipped it)

Edit `config.yaml` with your device(s)' IP, admin password, and schedule.

## Try it first

```bash
python3 scheduler.py -c config.yaml --dry-run
```

This prints what it *would* do without touching any device. Run it for real
by dropping `--dry-run`.

## Running on a schedule

### Option A: cron (recommended)

Add a crontab entry to apply the schedule every few minutes - it's cheap and
idempotent (it only sends an update if the mode actually needs to change):

```
*/5 * * * * /path/to/sclite-scheduler/venv/bin/python3 /path/to/sclite-scheduler/scheduler.py -c /path/to/sclite-scheduler/config.yaml >> /var/log/sclite-scheduler.log 2>&1
```

`crontab -e` to add it. Adjust the paths and `*/5` interval to taste - lower
intervals mean transitions happen closer to their scheduled time.

### Option B: built-in loop (no cron needed)

```bash
python3 scheduler.py -c config.yaml --loop 60
```

Runs forever, re-checking every 60 seconds. Useful for testing, or wrap it in
a systemd service if you want it supervised:

```ini
# /etc/systemd/system/sclite-scheduler.service
[Unit]
Description=Goldshell miner power-plan scheduler
After=network-online.target

[Service]
ExecStart=/path/to/sclite-scheduler/venv/bin/python3 /path/to/sclite-scheduler/scheduler.py -c /path/to/sclite-scheduler/config.yaml --loop 60
Restart=on-failure
User=youruser

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now sclite-scheduler
```

## Config format

```yaml
devices:
  - name: sclite-office        # label, just for log output
    ip: 192.168.1.100
    password: "..."            # the device's web UI admin password
    schedule:
      - time: "08:00"
        mode: hashrate          # matches the power plan with the highest MHz
      - time: "22:00"
        mode: idle               # matches the power plan with the lowest MHz
      - time: "23:00"           # optional: restrict an entry to specific days
        mode: hashrate
        days: [mon, tue, wed, thu, fri]
      # - time: "12:00"        # advanced: pick a plan by its exact "level"
      #   level: 3             # number instead of a named mode
```

The schedule uses "last transition wins" semantics: at any moment, the
active entry is whichever one most recently passed, looking back across day
boundaries as needed - so you don't need a `00:00` entry for a schedule to
carry over correctly past midnight.

`mode: hashrate` / `mode: idle` are resolved generically by parsing the
"XXX MHz" figure out of each power plan's description and picking the
highest/lowest - this matched the SC-LITE's two default plans (`615 MHz` /
`0 MHz`) without hardcoding model-specific values, but if a device has more
than two plans, use `level: N` on a schedule entry to target one exactly.

## Security note

The device's login endpoint only accepts a password (no separate API key),
so this tool has to hold the plaintext admin password in `config.yaml` to do
its job - same as the web UI itself does client-side. Keep the file
permissioned to `600` and don't commit it anywhere.
