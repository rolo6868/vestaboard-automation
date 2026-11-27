#!/usr/bin/env python3
"""Render every schedule entry as a board mockup, plus the rotation for one day, into preview.html.

  python preview.py                       # today's rotation
  python preview.py --date 2026-12-05     # a specific day
  python preview.py --all                 # include disabled entries
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
from zoneinfo import ZoneInfo

from vb.board import CODE_TO_CHAR, COLOR_HEX, SIZES, FrameError, load_frame
from vb.schedule import ROOT, load_config, load_schedule, pick, within_active_hours

FRAMES_DIR = ROOT / "frames"


def board_html(grid, black_board=True) -> str:
    bg = "#1b1b1b" if black_board else "#ece8df"
    fg = "#f4f1ea" if black_board else "#1b1b1b"
    cells = []
    for row in grid:
        for c in row:
            if c in COLOR_HEX:
                cells.append(f'<i style="background:{COLOR_HEX[c]}"></i>')
            elif c == 71:
                cells.append(f'<i style="background:{fg}"></i>')
            else:
                cells.append(f'<i style="color:{fg}">{html.escape(CODE_TO_CHAR.get(c, " "))}</i>')
    cols = len(grid[0])
    return f'<div class="board" style="background:{bg};grid-template-columns:repeat({cols},1fr)">{"".join(cells)}</div>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="preview.html")
    a = ap.parse_args()

    cfg = load_config()
    rows, cols = SIZES[cfg["board_size"]]
    entries = load_schedule()
    tz = ZoneInfo(cfg["timezone"])
    day = dt.date.fromisoformat(a.date) if a.date else dt.datetime.now(tz).date()

    cards, errors = [], []
    for e in entries:
        if not a.all and e.get("enabled", True) is False:
            continue
        try:
            g = load_frame(e, FRAMES_DIR, rows, cols)
        except FrameError as ex:
            errors.append(str(ex))
            continue
        meta = " · ".join(str(x) for x in [
            ",".join(e["days"]) if "days" in e else "every day",
            f'{e.get("start", "00:00")}–{e.get("end", "24:00")}',
            f'{e.get("from", "")}→{e.get("until", "")}' if ("from" in e or "until" in e) else "",
            f'priority {e["priority"]}' if e.get("priority") else "",
            "DISABLED" if e.get("enabled", True) is False else "",
        ] if x)
        cards.append(f'<figure>{board_html(g)}<figcaption><b>{html.escape(e["id"])}</b> — {html.escape(meta)}</figcaption></figure>')

    # Rotation timeline for the day
    timeline = []
    t = dt.datetime.combine(day, dt.time(0, 0), tz)
    last = None
    while t.date() == day:
        if within_active_hours(cfg, t):
            p = pick(entries, cfg, t)
            pid = p["id"] if p else "(nothing new — board holds)"
            if pid != last:
                timeline.append(f"<tr><td>{t:%I:%M %p}</td><td>{html.escape(pid)}</td></tr>")
                last = pid
        t += dt.timedelta(minutes=int(cfg["slot_minutes"]))

    status = "LIVE" if cfg["enabled"] else "DISABLED (nothing is sent until enabled: true)"
    doc = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Vestaboard preview</title>
<style>
body{{font-family:-apple-system,Segoe UI,sans-serif;margin:32px;background:#f6f5f2;color:#222}}
.board{{display:grid;gap:3px;padding:14px;border-radius:6px;width:min(100%,640px);box-shadow:0 2px 8px #0003}}
.board i{{aspect-ratio:3/4;display:flex;align-items:center;justify-content:center;font:700 clamp(8px,1.6vw,17px)/1 Helvetica,Arial,sans-serif;font-style:normal;background:#2a2a2a;border-radius:2px}}
figure{{margin:0 0 28px}} figcaption{{margin-top:8px;font-size:14px}}
table{{border-collapse:collapse;font-size:14px}} td{{padding:3px 14px 3px 0;border-bottom:1px solid #ddd}}
.err{{color:#b00020}}
</style></head><body>
<h1>Vestaboard preview</h1>
<p>Board: {cfg["board_size"]} ({rows}×{cols}) · Rotation every {cfg["slot_minutes"]} min · Active {cfg["active_hours"]["start"]}–{cfg["active_hours"]["end"]} · Status: <b>{status}</b></p>
{"".join(f'<p class="err">{html.escape(x)}</p>' for x in errors)}
<h2>Frames</h2>{"".join(cards) or "<p>No enabled frames yet.</p>"}
<h2>Rotation for {day:%A, %B %d, %Y}</h2><table>{"".join(timeline)}</table>
</body></html>"""
    (ROOT / a.out).write_text(doc, encoding="utf-8")
    print(f"wrote {ROOT / a.out} ({len(cards)} frames, {len(errors)} errors)")


if __name__ == "__main__":
    main()
