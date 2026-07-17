"""Seed shape library, grid-independent (unit-square polylines).

Priority/order is empirically motivated (Loge 2015; Munyendo SOUPS'21): the
owner's initials first, then the letters that most commonly appear as real
patterns, then digits and geometric strokes. `base_rank` is the tie-break
priority (lower = tried earlier). See SHAPE_MODE_PLAN.md section 5/11.

Coordinates are in the unit square [0,1]^2, origin top-left, y downward.
Each shape is drawn as a single continuous stroke (patterns cannot lift the
finger); multi-stroke letters are approximated by one stroke.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .geometry import Polyline


@dataclass(frozen=True)
class Shape:
    name: str
    strokes: tuple[Polyline, ...]
    base_rank: int
    tags: tuple[str, ...] = field(default_factory=tuple)


def _s(*points: tuple[float, float]) -> tuple[Polyline, ...]:
    return (tuple(points),)


# ---- Tier A: owner's initials -------------------------------------------------
_INITIALS = [
    # R: stem up, top bowl closing to the CENTRE (not back onto the stem, which
    # would revisit a dot), then the diagonal leg. Revisit-free + king-drawable.
    Shape("R", _s((0, 1), (0, 0), (1, 0), (1, 0.5), (0.5, 0.5), (1, 1)), 0, ("letter", "initial")),
    # S: top-right, across to left, down to middle, across to right, down, back left.
    Shape("S", _s((1, 0), (0, 0), (0, 0.5), (1, 0.5), (1, 1), (0, 1)), 1, ("letter", "initial")),
]

# ---- Tier B: empirically common letter shapes --------------------------------
_LETTERS = [
    Shape("Z", _s((0, 0), (1, 0), (0, 1), (1, 1)), 5, ("letter",)),
    Shape("L", _s((0, 0), (0, 1), (1, 1)), 6, ("letter",)),
    Shape("U", _s((0, 0), (0, 1), (1, 1), (1, 0)), 7, ("letter",)),
    Shape("V", _s((0, 0), (0.5, 1), (1, 0)), 8, ("letter",)),
    Shape("M", _s((0, 1), (0, 0), (0.5, 1), (1, 0), (1, 1)), 11, ("letter",)),
    Shape("W", _s((0, 0), (0.25, 1), (0.5, 0), (0.75, 1), (1, 0)), 12, ("letter",)),
    Shape("G", _s((1, 0), (0, 0), (0, 1), (1, 1), (1, 0.5), (0.5, 0.5)), 14, ("letter",)),
    Shape("A", _s((0, 1), (0.5, 0), (1, 1), (0.75, 0.5), (0.25, 0.5)), 16, ("letter",)),
    Shape("P", _s((0, 1), (0, 0), (1, 0), (1, 0.5), (0.5, 0.5)), 17, ("letter",)),
]

# ---- Tier C: digits -----------------------------------------------------------
_DIGITS = [
    Shape("7", _s((0, 0), (1, 0), (0, 1)), 21, ("digit",)),
    Shape("1", _s((0.5, 0), (0.5, 1)), 22, ("digit",)),
    Shape("4", _s((1, 0), (0, 0.5), (1, 0.5), (1, 1)), 23, ("digit",)),
]

# ---- Tier D: geometric strokes ------------------------------------------------
_GEOMETRIC = [
    Shape("line-diag", _s((0, 0), (1, 1)), 30, ("geometric", "line")),
    # only one line per orbit: line-h covers line-v (rotation), line-diag covers
    # line-antidiag (mirror) — since every shape auto-expands to its symmetries.
    Shape("line-h", _s((0, 0), (1, 0)), 32, ("geometric", "line")),
    Shape("zigzag", _s((0, 0), (1, 0.33), (0, 0.66), (1, 1)), 37, ("geometric",)),
    Shape("checkmark", _s((0, 0.5), (0.33, 1), (1, 0)), 38, ("geometric",)),
]

# ---- Tier E: household / objects ---------------------------------------------
_OBJECTS = [
    # open house outline (a pattern cannot close a loop back onto its start)
    Shape("house", _s((0, 1), (0, 0.4), (0.5, 0), (1, 0.4), (1, 1)), 50, ("object",)),
]

LIBRARY: list[Shape] = [*_INITIALS, *_LETTERS, *_DIGITS, *_GEOMETRIC, *_OBJECTS]

BY_NAME: dict[str, Shape] = {s.name: s for s in LIBRARY}


def load_extra_shapes(path: str) -> list[Shape]:
    """Parse a JSON file of extra shapes: [{name, strokes:[[[x,y],...]], base_rank?, tags?}]."""
    raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    shapes: list[Shape] = []
    for item in raw:
        strokes = tuple(
            tuple((float(p[0]), float(p[1])) for p in stroke) for stroke in item["strokes"]
        )
        shapes.append(
            Shape(
                name=str(item["name"]),
                strokes=strokes,
                base_rank=int(item.get("base_rank", 100)),
                tags=tuple(item.get("tags", ("custom",))),
            )
        )
    return shapes


def library_for(shape_dict_path: str = "") -> list[Shape]:
    """Built-in library, plus any shapes from the config's dict file if present."""
    if shape_dict_path:
        p = Path(shape_dict_path).expanduser()
        if p.exists():
            return [*LIBRARY, *load_extra_shapes(str(p))]
    return list(LIBRARY)
