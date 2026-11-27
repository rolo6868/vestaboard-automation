#!/usr/bin/env python3
"""Push the scheduled frame to the Vestaboard via the Cloud API.

Usage:
  python send.py                    # send whatever the schedule says is due now
  python send.py --dry-run          # show what would be sent, send nothing
  python send.py --at "2026-12-05 09:30" --dry-run   # simulate a moment in time
  python send.py --frame test       # send one entry by id (ignores schedule + enabled flag)
  python send.py --validate         # check every entry renders on the board size

Needs the env var VESTABOARD_TOKEN (Cloud API token) for real sends.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

from vb.board import SIZES, FrameError, bordered, load_frame
from vb.sports import gameday_frame_text, games_today, in_game_window
from vb.schedule import (ROOT, load_config, load_schedule, now_local, pick,
                         within_active_hours)

API = "https://cloud.vestaboard.com/"
FRAMES_DIR = ROOT / "frames"


def api(method: str, path: str = "", body: dict | None = None) -> tuple[int, dict]:
    token = os.environ.get("VESTABOARD_TOKEN")
    if not token:
        sys.exit("VESTABOARD_TOKEN is not set")
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-Vestaboard-Token": token, "Content-Type": "application/json"})
    err: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read().decode() or "{}"
                return r.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            if e.code < 500:  # 4xx (incl. 423 muted) are final answers, not retryable
                return e.code, {"error": e.read().decode(errors="replace")}
            err = e
        except urllib.error.URLError as e:
            err = e
        time.sleep(5 * (attempt + 1))
    sys.exit(f"Vestaboard API unreachable after retries: {err}")


def render(grid: list[list[int]]) -> str:
    from vb.board import CODE_TO_CHAR, COLOR_CODES
    inv = {v: k for k, v in COLOR_CODES.items()}
    return "\n".join("|" + "".join(CODE_TO_CHAR.get(c) or inv.get(c, "?") for c in row) + "|"
                     for row in grid)


def current_layout() -> list[list[int]] | None:
    status, data = api("GET")
    if status != 200:
        print(f"Could not read current board ({status}): {data}")
        return None
    layout = (data.get("currentMessage") or {}).get("layout")
    return json.loads(layout) if isinstance(layout, str) else layout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--at", help="simulate local time, e.g. '2026-12-05 09:30'")
    ap.add_argument("--frame", help="send a specific entry id now")
    ap.add_argument("--validate", action="store_true")
    a = ap.parse_args()

    cfg = load_config()
    rows, cols = SIZES[cfg["board_size"]]
    entries = load_schedule()

    if a.validate:
        bad = 0
        for e in entries:
            try:
                load_frame(e, FRAMES_DIR, rows, cols)
                print(f"ok    {e.get('id')}")
            except FrameError as ex:
                bad += 1
                print(f"ERROR {ex}")
        print(f"{len(entries) - bad}/{len(entries)} entries valid for {cfg['board_size']} ({rows}x{cols})")
        return 1 if bad else 0

    if a.frame:
        matches = [e for e in entries if e.get("id") == a.frame]
        if not matches:
            print(f"No entry with id '{a.frame}' in schedule.yaml")
            return 1
        entry = matches[0]
    else:
        if not cfg["enabled"]:
            print("Automation is disabled in config.yaml (enabled: false). Nothing sent.")
            return 0
        now = now_local(cfg, a.at)
        if not within_active_hours(cfg, now):
            print(f"{now:%a %H:%M} is outside active hours. Nothing sent.")
            return 0
        for g in games_today(cfg, now):
            label = f"{g['away'].get('abbreviation')} at {g['home'].get('abbreviation')} {g['start']:%I:%M %p}"
            if in_game_window(cfg, g, now):
                print(f"Game window ({label}, {g['state']}): board handed to Vestaboard+ live scores. Nothing sent.")
                return 0
            if now < g["start"]:
                entries.append({
                    "id": f"gameday-{g['kind']}",
                    "grid": bordered(gameday_frame_text(g, cols), rows, cols, top="bw", side="b"),
                    "weight": int((cfg.get("sports") or {}).get("gameday_weight", 2)),
                })
        entry = pick(entries, cfg, now)
        if not entry:
            print(f"{now:%a %Y-%m-%d %H:%M}: no eligible entries. Nothing sent.")
            return 0
        print(f"{now:%a %Y-%m-%d %H:%M}: due -> {entry['id']}")

    grid = load_frame(entry, FRAMES_DIR, rows, cols)
    print(render(grid))

    if a.dry_run:
        print("(dry run, not sent)")
        return 0

    if not a.frame and current_layout() == grid:
        print("Board already shows this frame. Skipping to avoid a needless flip.")
        return 0

    tr = cfg.get("transition")
    if tr:
        api("PUT", "transition", {"transition": tr["style"], "transitionSpeed": tr.get("speed", "gentle")})

    status, data = api("POST", body={"characters": grid})
    if status == 423:
        print("Board is muted / in quiet hours. Not forcing. Nothing sent.")
        return 0
    if status != 200:
        print(f"Send failed ({status}): {data}")
        return 1
    print(f"Sent '{entry['id']}' -> message {data.get('id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
