# Vestaboard automation

Pushes a scheduled rotation of frames (tile art and text) to the Vestaboard through the
Vestaboard Cloud API. It runs on GitHub Actions every 5 minutes, so your computer doesn't need to be on.

## How it works

- `schedule.yaml` lists what rotates and when: days, hours, date ranges and priority takeovers.
- `frames/` holds the tile-art files. Uppercase letters and punctuation print as text. Lowercase
  `r o y g b v w k` are red, orange, yellow, green, blue, violet, white and black tiles. `*` is the
  filled tile, and a space or `_` is blank.
- `config.yaml` holds the master on/off switch (`enabled`), board size, slot length, active hours and transition.
- `.github/workflows/vestaboard.yml` is the job that sends frames on a schedule, plus a manual "Run workflow" button.

Each run checks what's on the board and only flips it when the frame should change. If the
board is muted or in quiet hours, the run doesn't force a send.

## Commands

```
python send.py --validate                        # every entry fits the board?
python send.py --dry-run --at "2026-12-05 09:30" # what would show at that moment
python send.py --frame test                      # send one entry now (needs VESTABOARD_TOKEN)
python preview.py --date 2026-12-05              # preview.html with board mockups + day rotation
```

## One-time setup

1. In web.vestaboard.com, go to Developer and create a Cloud API token with read and write access.
2. In this repo on GitHub, go to Settings, then Secrets and variables, then Actions, then New repository secret.
   Name it `VESTABOARD_TOKEN` and paste the token as the value.
3. Go to Actions, then Vestaboard rotation, then Run workflow, and enter `test` in the frame box. The board shows the test frame.
4. Load content into the schedule, then set `enabled: true` in `config.yaml`.

## Limits to remember

- Vestaboard drops messages sent less than about 15 seconds apart, so no animation.
- Vestaboard+ isn't needed, because game-day live scores come from ESPN. If Vestaboard+ is ever reactivated,
  its saved channels (Morning Coffee, Brunch, Lunch, Afternoon coffee, Dinner) will fight this rotation.
- The repo is public, so Actions minutes are free. (A private repo on the free plan would get 2,000 minutes a month; this schedule would need about
  6,000.) The token stays in encrypted secrets and never appears in the code.
