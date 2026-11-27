"""Core Vestaboard helpers: character codes, frame parsing, text layout, validation."""
from __future__ import annotations

import textwrap
from pathlib import Path

SIZES = {"flagship": (6, 22), "note": (3, 15)}

# Literal characters -> Vestaboard codes (cloud API)
CHAR_CODES = {" ": 0}
for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", start=1):
    CHAR_CODES[c] = i
for i, c in enumerate("1234567890", start=27):
    CHAR_CODES[c] = i
CHAR_CODES.update({
    "!": 37, "@": 38, "#": 39, "$": 40, "(": 41, ")": 42, "-": 44, "+": 46,
    "&": 47, "=": 48, ";": 49, ":": 50, "'": 52, '"': 53, "%": 54, ",": 55,
    ".": 56, "/": 59, "?": 60, "°": 62,
})

# Color tiles in grid frames are written as lowercase letters
COLOR_CODES = {"r": 63, "o": 64, "y": 65, "g": 66, "b": 67, "v": 68, "w": 69, "k": 70, "*": 71}

GRID_CODES = {**CHAR_CODES, **COLOR_CODES}

# For previews
CODE_TO_CHAR = {v: k for k, v in CHAR_CODES.items()}
COLOR_HEX = {63: "#d6342b", 64: "#f08a24", 65: "#f5c518", 66: "#3a9d4a", 67: "#2a6fc9",
             68: "#7b4bb5", 69: "#f4f1ea", 70: "#111111"}


class FrameError(ValueError):
    pass


def parse_grid(src: str, rows: int, cols: int, name: str = "frame") -> list[list[int]]:
    """Parse a grid frame. Uppercase/digits/punctuation are literal, lowercase r o y g b v w k
    are color tiles, '*' is the filled tile, space or '_' is blank. Lines starting with '#'
    followed by a space are comments. Rows are padded/validated to the board size."""
    lines = [ln.rstrip("\n") for ln in src.splitlines() if not ln.startswith("# ")]
    # Drop trailing empty lines only
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) > rows:
        raise FrameError(f"{name}: {len(lines)} rows, board has {rows}")
    grid = []
    for r, line in enumerate(lines, start=1):
        if len(line) > cols:
            raise FrameError(f"{name}: row {r} is {len(line)} wide, board has {cols}: {line!r}")
        row = []
        for ch in line.ljust(cols):
            ch = " " if ch == "_" else ch
            if ch not in GRID_CODES:
                raise FrameError(f"{name}: row {r} has unsupported character {ch!r}")
            row.append(GRID_CODES[ch])
        grid.append(row)
    while len(grid) < rows:
        grid.append([0] * cols)
    return grid


def layout_text(text: str, rows: int, cols: int, align: str = "center",
                valign: str = "middle", name: str = "frame") -> list[list[int]]:
    """Word-wrap plain text onto the board. Blank lines in the source force line breaks."""
    text = text.upper().replace("’", "'").replace("“", '"').replace("”", '"')
    out_lines: list[str] = []
    for para in text.strip().split("\n"):
        if not para.strip():
            out_lines.append("")
            continue
        wrapped = textwrap.wrap(para.strip(), width=cols, break_long_words=True,
                                break_on_hyphens=False)
        out_lines.extend(wrapped or [""])
    if len(out_lines) > rows:
        raise FrameError(f"{name}: text needs {len(out_lines)} rows, board has {rows}. Shorten it.")
    for ln in out_lines:
        for ch in ln:
            if ch not in CHAR_CODES:
                raise FrameError(f"{name}: unsupported character {ch!r} in text")
    pad_top = {"top": 0, "middle": (rows - len(out_lines)) // 2, "bottom": rows - len(out_lines)}[valign]
    grid = [[0] * cols for _ in range(rows)]
    for i, ln in enumerate(out_lines):
        if align == "left":
            ln = ln.ljust(cols)
        elif align == "right":
            ln = ln.rjust(cols)
        else:
            left = (cols - len(ln)) // 2
            ln = (" " * left + ln).ljust(cols)
        grid[pad_top + i] = [CHAR_CODES[c] for c in ln]
    return grid


def bordered(lines: list[str], rows: int, cols: int, top: str, side: str = "",
             bottom: str | None = None) -> str:
    """Build grid-frame source: a colored top/bottom row pattern, optional side tiles, centered text."""
    def pattern(p: str) -> str:
        return (p * cols)[:cols]
    side = side or ""
    inner_w = cols - 2 * len(side[:1])
    body_rows = rows - 2
    body = [""] * ((body_rows - len(lines)) // 2) + list(lines)
    body += [""] * (body_rows - len(body))
    out = [pattern(top)]
    for ln in body:
        s = side[:1]
        out.append(s + ln.center(inner_w) + s)
    out.append(pattern(bottom if bottom is not None else top))
    return "\n".join(out)


def load_frame(spec: dict, frames_dir: Path, rows: int, cols: int) -> list[list[int]]:
    """A schedule entry references either `frame: file.txt` (grid art) or `text: ...`."""
    name = spec.get("id", "?")
    if "frame" in spec:
        path = frames_dir / spec["frame"]
        if not path.exists():
            raise FrameError(f"{name}: frame file not found: {path}")
        return parse_grid(path.read_text(encoding="utf-8"), rows, cols, name=spec["frame"])
    if "grid" in spec:  # generated on the fly (e.g. game day)
        return parse_grid(spec["grid"], rows, cols, name=name)
    if "text" in spec:
        return layout_text(str(spec["text"]), rows, cols,
                           align=spec.get("align", "center"),
                           valign=spec.get("valign", "middle"), name=name)
    raise FrameError(f"{name}: entry needs either 'frame' or 'text'")
