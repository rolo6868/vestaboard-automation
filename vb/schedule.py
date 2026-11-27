"""Pick which schedule entry should be on the board at a given moment."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
ROOT = Path(__file__).resolve().parent.parent


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config() -> dict:
    cfg = load_yaml(ROOT / "config.yaml")
    cfg.setdefault("enabled", False)
    cfg.setdefault("timezone", "America/New_York")
    cfg.setdefault("board_size", "flagship")
    cfg.setdefault("slot_minutes", 20)
    cfg.setdefault("active_hours", {"start": "00:00", "end": "24:00"})
    return cfg


def load_schedule() -> list[dict]:
    data = load_yaml(ROOT / "schedule.yaml")
    entries = data.get("rotation") or []
    ids = [e.get("id") for e in entries]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate ids in schedule.yaml: {sorted(dupes)}")
    return entries


def _hm(s: str) -> int:
    h, m = str(s).split(":")
    return int(h) * 60 + int(m)


def _as_date(v):
    if v is None or isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v))


def in_window(now_min: int, start: str, end: str) -> bool:
    a, b = _hm(start), _hm(end)
    if a <= b:
        return a <= now_min < b
    return now_min >= a or now_min < b  # window crosses midnight


def eligible(entry: dict, now: dt.datetime) -> bool:
    if entry.get("enabled", True) is False:
        return False
    days = [d.lower()[:3] for d in entry.get("days", DAYS)]
    if DAYS[now.weekday()] not in days:
        return False
    d_from, d_until = _as_date(entry.get("from")), _as_date(entry.get("until"))
    if d_from and now.date() < d_from:
        return False
    if d_until and now.date() > d_until:
        return False
    now_min = now.hour * 60 + now.minute
    return in_window(now_min, entry.get("start", "00:00"), entry.get("end", "24:00"))


def now_local(cfg: dict, at: str | None = None) -> dt.datetime:
    tz = ZoneInfo(cfg["timezone"])
    if at:
        return dt.datetime.fromisoformat(at).replace(tzinfo=tz)
    return dt.datetime.now(tz)


def within_active_hours(cfg: dict, now: dt.datetime) -> bool:
    ah = cfg["active_hours"]
    return in_window(now.hour * 60 + now.minute, ah["start"], ah["end"])


def pick(entries: list[dict], cfg: dict, now: dt.datetime) -> dict | None:
    """Highest-priority eligible entries win; among those, rotate one per time slot."""
    pool = [e for e in entries if eligible(e, now)]
    if not pool:
        return None
    top = max(int(e.get("priority", 0)) for e in pool)
    pool = [e for e in pool if int(e.get("priority", 0)) == top]
    # weight: 2 means the entry gets two turns per cycle (spread out, not back to back)
    weighted = []
    max_w = max(int(e.get("weight", 1)) for e in pool)
    for rnd in range(max_w):
        weighted += [e for e in pool if int(e.get("weight", 1)) > rnd]
    pool = weighted
    minutes_today = now.hour * 60 + now.minute
    slot = (now.toordinal() * 1440 + minutes_today) // int(cfg["slot_minutes"])
    return pool[slot % len(pool)]
