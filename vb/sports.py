"""Game-day logic for Kentucky football and basketball (ESPN public schedule feed).

- During a game window the rotation pauses, so the Vestaboard+ live-score channels own the board.
- Earlier on a game day, a "GAME DAY" frame is added to the rotation.
If the feed can't be reached, the rotation runs normally (fail-open).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.request
from zoneinfo import ZoneInfo

ESPN = "https://site.api.espn.com/apis/site/v2/sports/{league}/teams/{team}/schedule"


def _fetch(league: str, team: int) -> list[dict]:
    fixture = os.environ.get("SPORTS_FIXTURE")  # offline testing
    if fixture:
        with open(fixture, encoding="utf-8") as f:
            return json.load(f).get(league, [])
    req = urllib.request.Request(ESPN.format(league=league, team=team),
                                 headers={"User-Agent": "vestaboard-automation"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode()).get("events", [])


def games_today(cfg: dict, now: dt.datetime) -> list[dict]:
    sp = cfg.get("sports") or {}
    if not sp.get("enabled"):
        return []
    tz = ZoneInfo(cfg["timezone"])
    out = []
    for league in sp.get("leagues", []):
        try:
            events = _fetch(league, sp["team_id"])
        except Exception as e:  # noqa: BLE001 - never let the feed break the board
            print(f"Sports feed unavailable for {league} ({e}); continuing without it.")
            continue
        for ev in events:
            try:
                start = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(tz)
            except (KeyError, ValueError):
                continue
            if start.date() != now.date():
                continue
            comp = ev["competitions"][0]
            teams = {c["homeAway"]: c["team"] for c in comp["competitors"]}
            out.append({
                "league": league,
                "kind": "football" if league.startswith("football") else "basketball",
                "start": start,
                "state": comp.get("status", {}).get("type", {}).get("state", "pre"),
                "home": teams.get("home", {}),
                "away": teams.get("away", {}),
            })
    return out


def in_game_window(cfg: dict, game: dict, now: dt.datetime) -> bool:
    sp = cfg["sports"]
    before = dt.timedelta(minutes=int(sp.get("pregame_minutes", 30)))
    length = dt.timedelta(minutes=int(sp.get("game_minutes", {}).get(game["kind"], 210)))
    if game["state"] == "in":
        return True
    return game["start"] - before <= now <= game["start"] + length


def _name(team: dict, width: int) -> str:
    for key in ("location", "shortDisplayName", "abbreviation"):
        n = str(team.get(key, "")).upper()
        if n and len(n) <= width:
            return n
    return str(team.get("abbreviation", "TBD")).upper()[:width]


def gameday_frame_text(game: dict, cols: int) -> list[str]:
    """Inner text lines for the GAME DAY frame (border added by caller)."""
    inner = cols - 2
    sport = "FOOTBALL" if game["kind"] == "football" else "BASKETBALL"
    t = game["start"].strftime("%I:%M %p").lstrip("0")
    when = ("KICKOFF " if game["kind"] == "football" else "TIP-OFF ") + t
    def short(team):  # Kentucky -> UK when space is tight; opponents keep their name
        return "UK" if team.get("abbreviation") == "UK" else _name(team, inner - 6)
    away, home = _name(game["away"], inner), _name(game["home"], inner)
    matchup = f"{away} AT {home}"
    if len(matchup) > inner:
        matchup = f"{short(game['away'])} AT {short(game['home'])}"
    return ["GAME DAY! GO CATS!", f"UK {sport}", matchup[:inner], when]
