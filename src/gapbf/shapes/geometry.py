"""Grid-independent shape geometry.

A shape is one or more strokes, each a polyline of points in the unit square
[0,1]^2 (origin top-left, y downward — screen coordinates). Rendering maps a
polyline onto an N x N dot grid, snapping vertices to dots and walking the
lattice dots each straight segment passes over (Android auto-includes collinear
intermediate dots). Node identifiers come from Config.NODE_SEQUENCE, where the
dot at grid (x, y) has index y*N + x.
"""

from __future__ import annotations

from math import gcd

from ..Config import NODE_SEQUENCE

Point = tuple[float, float]
Polyline = tuple[Point, ...]
Cell = tuple[int, int]


def rotate90(poly: Polyline, k: int) -> Polyline:
    """Rotate a unit-square polyline by 90*k degrees about the centre.
    One step maps (x, y) -> (1 - y, x); applied 4 times it is the identity,
    so k in {0,1,2,3} yields all four orientations."""
    pts = list(poly)
    for _ in range(k % 4):
        pts = [(1.0 - y, x) for (x, y) in pts]
    return tuple(pts)


def mirror(poly: Polyline, axis: str) -> Polyline:
    if axis == "h":  # flip left/right
        return tuple((1.0 - x, y) for (x, y) in poly)
    if axis == "v":  # flip top/bottom
        return tuple((x, 1.0 - y) for (x, y) in poly)
    raise ValueError(f"axis must be 'h' or 'v', got {axis!r}")


def reverse(poly: Polyline) -> Polyline:
    return tuple(reversed(poly))


def place_on_grid(poly: Polyline, grid_size: int, ox: int, oy: int, w: int, h: int) -> list[Cell]:
    """Map a unit-square polyline into the grid bounding box with top-left
    (ox, oy) and span (w, h) in dot units, snapping each vertex to the nearest
    dot and clamping into the grid."""
    n = grid_size
    cells: list[Cell] = []
    for x, y in poly:
        gx = min(n - 1, max(0, round(ox + x * w)))
        gy = min(n - 1, max(0, round(oy + y * h)))
        cells.append((gx, gy))
    return cells


def walk_segment(a: Cell, b: Cell) -> list[Cell]:
    """Lattice dots lying exactly on the straight segment a->b, in order,
    inclusive of both ends. Collinear intermediate dots are at gcd steps."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return [a]
    g = gcd(abs(dx), abs(dy))
    sx, sy = dx // g, dy // g
    return [(a[0] + k * sx, a[1] + k * sy) for k in range(g + 1)]


def _cell_to_node(cell: Cell, grid_size: int) -> str:
    x, y = cell
    return NODE_SEQUENCE[y * grid_size + x]


def render_to_nodes(
    poly: Polyline, grid_size: int, ox: int, oy: int, w: int, h: int
) -> list[str]:
    """Render one placed polyline to an ordered node-character sequence,
    including collinear intermediate dots and dropping consecutive repeats."""
    snapped = place_on_grid(poly, grid_size, ox, oy, w, h)
    coords: list[Cell] = []
    for i, cell in enumerate(snapped):
        segment = [cell] if i == 0 else walk_segment(snapped[i - 1], cell)[1:]
        for c in segment:
            if not coords or coords[-1] != c:
                coords.append(c)
    return [_cell_to_node(c, grid_size) for c in coords]


def render_multi(
    strokes: tuple[Polyline, ...], grid_size: int, ox: int, oy: int, w: int, h: int
) -> list[str]:
    """Render a multi-stroke shape as one continuous sequence (strokes joined
    in order; the join between strokes is walked like any other segment)."""
    seq: list[str] = []
    prev_cell: Cell | None = None
    for stroke in strokes:
        snapped = place_on_grid(stroke, grid_size, ox, oy, w, h)
        pts = snapped if prev_cell is None else [prev_cell, *snapped]
        coords: list[Cell] = []
        for i, cell in enumerate(pts):
            segment = [cell] if i == 0 else walk_segment(pts[i - 1], cell)[1:]
            coords.extend(segment)
        for c in coords:
            node = _cell_to_node(c, grid_size)
            if not seq or seq[-1] != node:
                seq.append(node)
        prev_cell = snapped[-1]
    return seq


if __name__ == "__main__":
    # ponytail: self-check — the diagonal top-left->bottom-right on 5x5 must
    # render to the five main-diagonal dots, in order.
    diag = ((0.0, 0.0), (1.0, 1.0))
    got = render_to_nodes(diag, 5, ox=0, oy=0, w=4, h=4)
    assert got == ["1", "7", "=", "C", "I"], got
    # a horizontal top edge, half width, must include the intermediate dot.
    top = ((0.0, 0.0), (1.0, 0.0))
    assert render_to_nodes(top, 5, 0, 0, 2, 0) == ["1", "2", "3"], render_to_nodes(
        top, 5, 0, 0, 2, 0
    )
    # rotation by 4 is identity
    assert rotate90(diag, 4) == diag
    print("geometry self-check OK")
