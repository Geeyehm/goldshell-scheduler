"""Resolve which schedule entry is currently active for a device.

Each entry: {"time": "HH:MM", "mode": "hashrate"|"idle", "days": [optional list],
"months": [optional list]} (or {"time": ..., "level": N} instead of "mode" for
direct control).

The active entry is the most recent one (walking back day by day, respecting
optional weekday/month restrictions) whose time is at or before `now` - i.e.
standard "last transition wins" schedule semantics, so a schedule set once
continues to apply correctly across midnight/day boundaries without needing
an entry at 00:00.
"""
from __future__ import annotations

from datetime import datetime, timedelta

WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MONTH_NAMES = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
LOOKBACK_DAYS = 8  # covers weekday-restricted schedules with gaps up to a week


def resolve_active_entry(schedule: list[dict], now: datetime | None = None) -> dict | None:
    now = now or datetime.now()

    for days_back in range(LOOKBACK_DAYS):
        day = (now - timedelta(days=days_back)).date()
        weekday_name = WEEKDAY_NAMES[day.weekday()]
        month_name = MONTH_NAMES[day.month - 1]

        best_entry = None
        best_dt = None
        for entry in schedule:
            days = entry.get("days")
            if days and weekday_name not in (d.lower() for d in days):
                continue
            months = entry.get("months")
            if months and month_name not in (m.lower() for m in months):
                continue
            hh, mm = map(int, entry["time"].split(":"))
            entry_dt = datetime(day.year, day.month, day.day, hh, mm)
            if entry_dt <= now and (best_dt is None or entry_dt > best_dt):
                best_dt = entry_dt
                best_entry = entry

        if best_entry is not None:
            return best_entry

    return None
