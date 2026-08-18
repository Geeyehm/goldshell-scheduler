# goldshell-scheduler

Switches Goldshell miners between power plans (e.g. "Hashrate Mode" / "Idle
Mode") on a schedule, across multiple devices, driven by a config file.

> **Tested scope:** this has only been built and confirmed working against a
> **Goldshell SC-LITE**. It's written generically against the web API shared
> across Goldshell control boards (`/user/login`, `/mcb/setting`), so other
> models likely work too, but that's untested - if you try it on another
> model, treat the first run as an experiment (`--dry-run` first) rather than
> an assumption.

## How it works

1. `scheduler.py` reads `config.yaml` and, for each device, works out which
   schedule entry should currently be active (`schedule_resolver.py`) - the
   most recent entry whose time has already passed, looking back across
   day/weekday boundaries as needed.
2. It logs into the device's web UI over HTTP (`goldshell_client.py`),
   replicating exactly what the browser does: the password is AES-encrypted
   client-side with the device's fixed key before being sent, and the device
   returns a JWT bearer token used for subsequent requests.
3. It reads the device's current power-plan settings (`GET /mcb/setting`),
   works out which of the device's own existing presets matches the
   scheduled mode (by parsing the clock speed out of each preset's
   description), and - only if it isn't already active - switches to it
   (`PUT /mcb/setting`).
4. Nothing is brute-forced or invented: every request mirrors what the
   device's own web UI sends when you use it by hand.

## Setup (Linux)

If this is running on a dedicated machine/container (e.g. its own LXC), a venv
is unnecessary overhead - just install straight to the system Python:

```bash
cd goldshell-scheduler
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
*/5 * * * * /path/to/goldshell-scheduler/venv/bin/python3 /path/to/goldshell-scheduler/scheduler.py -c /path/to/goldshell-scheduler/config.yaml >> /var/log/goldshell-scheduler.log 2>&1
```

`crontab -e` to add it. Adjust the paths and `*/5` interval to taste - lower
intervals mean transitions happen closer to their scheduled time, but watch
out for schedule windows narrower than your interval (a 2-minute window can
get skipped entirely by a 5-minute cron tick).

### Option B: built-in loop (manual/foreground)

```bash
python3 scheduler.py -c config.yaml --loop 60
```

Runs forever in the foreground, re-checking every 60 seconds, reloading
`config.yaml` on every check so edits take effect without a restart. Good
for testing or a quick one-off session, but it stops if your terminal closes
- for anything long-running unattended, use Option C instead.

### Option C: systemd service (recommended for unattended/long-running use)

Wraps Option B's loop mode in a proper supervised service - starts on boot,
restarts on failure/crash, and logs to `journalctl`:

```ini
# /etc/systemd/system/goldshell-scheduler.service
[Unit]
Description=Goldshell miner power-plan scheduler
After=network-online.target

[Service]
ExecStart=/path/to/goldshell-scheduler/venv/bin/python3 /path/to/goldshell-scheduler/scheduler.py -c /path/to/goldshell-scheduler/config.yaml --loop 60
Restart=on-failure
User=youruser

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now goldshell-scheduler
```

Watch its logs with:

```bash
journalctl -u goldshell-scheduler -f
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
