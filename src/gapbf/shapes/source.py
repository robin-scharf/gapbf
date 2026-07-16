"""Turn shapes into ranked, legal pattern candidates for the configured grid.

Reuses PathFinder's legality primitives (distance, blocker/intermediate nodes,
crossing constraints) so shape candidates are exactly the same "legal patterns"
the graph mode produces, and map to the same twrp-decrypt strings + DB keys.
Ranking follows the empirical priors in SHAPE_MODE_PLAN.md section 8.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from ..Config import Config
from ..PathFinder import PathFinder
from .geometry import Polyline, mirror, render_multi, reverse, rotate90
from .library import LIBRARY, Shape


class ShapeCandidateSource:
    def __init__(self, config: Config, path_finder: PathFinder | None = None) -> None:
        self.config = config
        self.n = config.grid_size
        # Legality uses FULL Android rules (max distance = grid-1, crossings
        # allowed) so a real finger-drawn shape is never dropped. The user's
        # dist-1 / no-crossing belief is applied as a ranking prior, not a
        # hard filter (see _prior_score). Excluded nodes + length still apply.
        self.pf = path_finder or PathFinder(
            grid_size=config.grid_size,
            path_min_len=config.path_min_length,
            path_max_len=config.path_max_length,
            path_max_node_distance=config.grid_size - 1,
            excluded_nodes=config.excluded_nodes,
            no_diagonal_crossings=False,
            no_perpendicular_crossings=False,
        )
        self._coord = self.pf._coordinates  # node char -> (x, y)
        # what the owner believes about their pattern, used only for ranking
        self._pref_max_distance = config.path_max_node_distance

    # --- legality ------------------------------------------------------------
    def is_legal(self, seq: list[str]) -> bool:
        if not (self.config.path_min_length <= len(seq) <= self.config.path_max_length):
            return False
        visited: set[str] = set()
        used: set[tuple[str, str]] = set()
        prev: str | None = None
        for node in seq:
            if node in visited:
                return False
            if prev is not None:
                if not self.pf._is_move_legal(prev, node, visited, used):
                    return False
                used.add(self.pf._canonical_edge(prev, node))
            visited.add(node)
            prev = node
        return True

    # --- variation engine ----------------------------------------------------
    def _orientations(self, shape: Shape, wildness: int) -> list[tuple[Polyline, ...]]:
        rots = [tuple(rotate90(p, k) for p in shape.strokes) for k in range(4)]
        variants = list(rots)
        variants += [tuple(mirror(p, "h") for p in v) for v in rots]
        if wildness >= 2:  # also draw the stroke the other way round
            variants += [tuple(reverse(p) for p in reversed(v)) for v in list(variants)]
        seen: set[tuple[Polyline, ...]] = set()
        out: list[tuple[Polyline, ...]] = []
        for v in variants:
            if v not in seen:
                seen.add(v)
                out.append(v)
        return out

    def _placements(self, wildness: int) -> Iterator[tuple[int, int, int, int]]:
        n = self.n
        if wildness <= 0:
            spans = [(n - 1, n - 1)]
        elif wildness == 1:
            spans = [(s, s) for s in range(2, n)]
        else:
            spans = [(w, h) for w in range(2, n) for h in range(2, n)]
        for w, h in spans:
            if wildness <= 0:
                offsets = [((n - 1 - w) // 2, (n - 1 - h) // 2)]
            else:
                offsets = [
                    (ox, oy)
                    for ox in range(0, n - w)
                    for oy in range(0, n - h)
                ]
            for ox, oy in offsets:
                yield ox, oy, w, h

    def expand(self, shape: Shape, wildness: int = 1) -> Iterator[list[str]]:
        seen: set[tuple[str, ...]] = set()
        for strokes in self._orientations(shape, wildness):
            for ox, oy, w, h in self._placements(wildness):
                seq = render_multi(strokes, self.n, ox, oy, w, h)
                if len(seq) < 2 or not self.is_legal(seq):
                    continue
                key = tuple(seq)
                if key not in seen:
                    seen.add(key)
                    yield seq

    # --- ranking -------------------------------------------------------------
    def _max_move_distance(self, seq: list[str]) -> int:
        worst = 0
        for a, b in zip(seq, seq[1:]):
            ax, ay = self._coord[a]
            bx, by = self._coord[b]
            worst = max(worst, abs(bx - ax), abs(by - ay))
        return worst

    def _priors(self, seq: list[str]) -> tuple[int, int, int]:
        """Empirical prior components (lower = more likely; SHAPE_MODE_PLAN 8):
        (belief_pen, start_pen, length_pen).
        belief_pen: deviation from the owner's believed king-move (dist-1) style.
        start_pen: top-left(0) < other corner(1) < edge(2) < centre(3).
        length_pen: distance from the real-world average length ~5."""
        n = self.n
        belief_pen = max(0, self._max_move_distance(seq) - self._pref_max_distance)
        x, y = self._coord[seq[0]]
        if x == 0 and y == 0:
            start = 0
        elif x in (0, n - 1) and y in (0, n - 1):
            start = 1
        elif x in (0, n - 1) or y in (0, n - 1):
            start = 2
        else:
            start = 3
        return (belief_pen, start, abs(len(seq) - 5))

    def candidates(
        self,
        shapes: Iterable[Shape] | None = None,
        drawn: Iterable[list[str]] = (),
        wildness: int = 1,
    ) -> list[list[str]]:
        shapes = list(shapes) if shapes is not None else LIBRARY
        # Global ordering (each key ascending, lower = tried earlier):
        #   drawn-first, then king-move belief, then shape priority, then
        #   corner-start prior, then length prior. So all dist-1 candidates of
        #   any shape precede dist-2 ones, with the initials first within each.
        scored: list[tuple[tuple[int, int, int, int, int], list[str]]] = []
        seen: set[tuple[str, ...]] = set()

        def add(seq: list[str], shape_rank: int, is_drawn: bool) -> None:
            key = tuple(seq)
            if key in seen:
                return
            seen.add(key)
            belief_pen, start_pen, length_pen = self._priors(seq)
            sort_key = (0 if is_drawn else 1, belief_pen, shape_rank, start_pen, length_pen)
            scored.append((sort_key, seq))

        for d in drawn:
            if self.is_legal(list(d)):
                add(list(d), -1, True)
        for shape in sorted(shapes, key=lambda s: s.base_rank):
            for seq in self.expand(shape, wildness):
                add(seq, shape.base_rank, False)

        scored.sort(key=lambda t: t[0])
        return [seq for _, seq in scored]
