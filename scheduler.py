#!/usr/bin/env python3
"""Apply power-plan schedules to one or more Goldshell miners from a YAML config.

Usage:
    python3 scheduler.py -c config.yaml            # apply once (for cron)
    python3 scheduler.py -c config.yaml --dry-run   # show what would happen
    python3 scheduler.py -c config.yaml --loop 60   # run continuously instead of cron
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

import yaml

from goldshell_client import GoldshellClient
from schedule_resolver import resolve_active_entry


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def apply_schedules(config: dict, now: datetime | None = None, dry_run: bool = False) -> None:
    now = now or datetime.now()
    for device in config.get("devices", []):
        name = device.get("name", device.get("ip", "<unknown>"))
        try:
            entry = resolve_active_entry(device["schedule"], now)
            if entry is None:
                print(f"[{name}] no applicable schedule entry for {now:%Y-%m-%d %H:%M}, skipping")
                continue

            mode = entry.get("mode")
            level = entry.get("level")

            if dry_run:
                print(f"[{name}] would apply mode={mode!r} level={level!r} (scheduled {entry['time']})")
                continue

            client = GoldshellClient(device["ip"], device["password"])
            result = client.apply_mode(mode=mode, level=level)
            if result["changed"]:
                print(f"[{name}] switched power plan -> select={result['select']} (mode={mode!r} level={level!r})")
            else:
                print(f"[{name}] already on the scheduled plan (select={result['select']})")
        except Exception as e:  # noqa: BLE001 - a bad entry/unreachable device shouldn't stop the others
            print(f"[{name}] ERROR: {e}", file=sys.stderr)


def main() -> None:
    # force line-buffering even when stdout/stderr aren't a TTY (e.g. under systemd/journald),
    # otherwise output can sit unflushed for a long time - or get lost entirely on SIGTERM
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-c", "--config", default="config.yaml", help="path to config file (default: config.yaml)")
    parser.add_argument("--dry-run", action="store_true", help="print actions without applying them")
    parser.add_argument("--loop", type=int, metavar="SECONDS", help="run continuously, checking every N seconds, instead of relying on cron")
    args = parser.parse_args()

    if args.loop:
        print(f"running in loop mode, checking every {args.loop}s (Ctrl+C to stop)")
        print(f"reloading {args.config} on every check, so edits take effect without a restart")
        try:
            while True:
                try:
                    config = load_config(args.config)
                except Exception as e:  # noqa: BLE001 - keep the service alive through a bad edit
                    print(f"failed to reload {args.config}: {e}", file=sys.stderr)
                else:
                    apply_schedules(config, dry_run=args.dry_run)
                time.sleep(args.loop)
        except KeyboardInterrupt:
            print("\nstopping.")
    else:
        config = load_config(args.config)
        apply_schedules(config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
