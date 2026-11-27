"""Game-day logic for Kentucky football and basketball (ESPN public schedule feed).

- During a game window the board becomes a live scoreboard (score + clock, then FINAL).
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
            scores = {}
            for c in comp["competitors"]:
                s = c.get("score")
                scores[c["homeAway"]] = (s.get("displayValue") if isinstance(s, dict) else s) or ""
            out.append({
                "id": ev.get("id"),
                "league": league,
                "scores": scores,
                "detail": comp.get("status", {}).get("type", {}).get("shortDetail", ""),
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


def refresh_live(game: dict) -> dict:
    """Pull the live score/clock for one game from ESPN's summary feed (schedule data lags)."""
    if os.environ.get("SPORTS_FIXTURE") or not game.get("id"):
        return game
    url = (f"https://site.api.espn.com/apis/site/v2/sports/{game['league']}/summary?event={game['id']}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "vestaboard-automation"})
        with urllib.request.urlopen(req, timeout=15) as r:
            comp = json.loads(r.read().decode())["header"]["competitions"][0]
        g = dict(game)
        g["state"] = comp["status"]["type"].get("state", game["state"])
        g["detail"] = comp["status"]["type"].get("shortDetail", game.get("detail", ""))
        g["scores"] = {c["homeAway"]: str(c.get("score", "")) for c in comp["competitors"]}
        return g
    except Exception as e:  # noqa: BLE001
        print(f"Live score unavailable ({e}); using schedule data.")
        return game


def _clean(s: str) -> str:
    from vb.board import CHAR_CODES
    return "".join(ch for ch in str(s).upper() if ch in CHAR_CODES).strip()


def score_frame_text(game: dict, cols: int) -> list[str]:
    """Inner lines for the live/final score frame."""
    inner = cols - 2
    sport = "UK FOOTBALL" if game["kind"] == "football" else "UK BASKETBALL"
    sc = game.get("scores", {})
    rows = []
    for side in ("away", "home"):
        score = _clean(sc.get(side, "")) or "0"
        name = _name(game[side], inner - len(score) - 1)
        rows.append(name.ljust(inner - len(score)) + score)
    if game["state"] == "post":
        status = "FINAL"
    else:
        status = _clean(game.get("detail", "")) or "LIVE"
    return [sport, rows[0], rows[1], status[:inner]]


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
