#!/usr/bin/env python3
"""Check whether a Goldshell miner's web API looks compatible with goldshell-scheduler.

Read-only: only ever sends GET requests, never modifies any device setting.

Useful if goldshell-scheduler doesn't work on your model - run this against
your own device and share the output (redact anything you don't want public,
the raw JSON doesn't contain anything sensitive besides your device's local
IP/MAC) when opening a GitHub issue, so support for your model can be added.

Usage:
    python3 check_compatibility.py <ip>
    python3 check_compatibility.py <ip> --password yourpassword
"""
from __future__ import annotations

import argparse
import getpass
import json

import requests

from goldshell_client import GoldshellClient, GoldshellError


def check(ip: str, password: str) -> None:
    print(f"=== Checking {ip} ===\n")

    print("[1/3] GET /mcb/status (no auth required)")
    try:
        r = requests.get(f"http://{ip}/mcb/status", timeout=8)
        r.raise_for_status()
        status = r.json()
        print(json.dumps(status, indent=2))
        print(f"  model: {status.get('model', '<missing>')}")
        print(f"  mcbversion: {status.get('mcbversion', '<missing>')}")
    except Exception as e:  # noqa: BLE001
        print(f"  FAILED: {e}")
        print("  This device doesn't seem to respond on this endpoint at all - it")
        print("  probably isn't running the same web API this tool targets.")
        return
    print()

    print("[2/3] Login (GET /user/login with AES-encrypted password)")
    client = GoldshellClient(ip, password)
    try:
        client.login()
        print("  OK: got a JWT token back")
    except GoldshellError as e:
        print(f"  FAILED: {e}")
        print("  Either the password is wrong, or this model's login doesn't use the")
        print("  same AES-CBC scheme (key '!!!!!!!!!!!!!!!!', zero IV, zero padding).")
        return
    except Exception as e:  # noqa: BLE001
        print(f"  FAILED: {e}")
        return
    print()

    print("[3/3] GET /mcb/setting")
    try:
        setting = client.get_setting()
        print(json.dumps(setting, indent=2))
    except Exception as e:  # noqa: BLE001
        print(f"  FAILED: {e}")
        return
    print()

    print("=== Compatibility summary ===")
    missing = [f for f in ("select", "powerplans") if f not in setting]
    if missing:
        print(f"  MISSING required field(s): {missing} - this tool cannot work as-is.")
        return
    print("  Has 'select' and 'powerplans' fields - basic shape matches.")

    plans = setting.get("powerplans", [])
    if not plans:
        print("  WARNING: 'powerplans' is empty - nothing to switch between.")
        return

    print(f"  {len(plans)} power plan(s) found:")
    all_parse_ok = True
    for i, p in enumerate(plans):
        info = p.get("info", "")
        mhz = GoldshellClient._parse_mhz(info)
        ok = mhz >= 0
        all_parse_ok = all_parse_ok and ok
        print(f"    [{i}] level={p.get('level')!r} info={info!r} -> {'OK' if ok else 'COULD NOT PARSE MHz'}")

    if all_parse_ok:
        print("  All plans parsed correctly - mode: hashrate/idle should work as-is.")
    else:
        print("  Some plans' 'info' text doesn't match the expected 'XXX MHz ...' format -")
        print("  mode: hashrate/idle matching would need adjusting for this model.")
        print("  You can still use 'level: N' in your schedule to target a plan directly.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ip", help="the miner's IP address")
    parser.add_argument("--password", help="admin password (omit to be prompted instead, safer than shell history)")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Admin password: ")
    check(args.ip, password)


if __name__ == "__main__":
    main()
