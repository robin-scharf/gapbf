"""A PathFinder whose iteration yields ranked shape candidates.

Subclasses PathFinder so it reuses everything the run pipeline needs
(handlers, process_path, coordinates) while replacing the graph DFS with a
precomputed, ranked shape-candidate list. `search_mode: shape_then_graph`
yields the shapes first, then falls back to the full graph enumeration.
"""

from __future__ import annotations

from collections.abc import Iterator

from ..Config import Config
from ..PathFinder import PathFinder
from .source import ShapeCandidateSource


class ShapePathFinder(PathFinder):
    def __init__(self, config: Config) -> None:
        super().__init__(
            grid_size=config.grid_size,
            path_min_len=config.path_min_length,
            path_max_len=config.path_max_length,
            path_max_node_distance=config.path_max_node_distance,
            path_prefix=config.path_prefix,
            path_suffix=config.path_suffix,
            excluded_nodes=config.excluded_nodes,
            no_diagonal_crossings=config.no_diagonal_crossings,
            no_perpendicular_crossings=config.no_perpendicular_crossings,
        )
        self._config = config
        self._then_graph = config.search_mode == "shape_then_graph"
        source = ShapeCandidateSource(config)
        shapes = (
            [source.by_name[n] for n in config.shape_names if n in source.by_name]
            if config.shape_names
            else None
        )
        self._shape_candidates: list[list[str]] = source.candidates(
            shapes=shapes,
            drawn=[list(d) for d in config.drawn_shapes],
            wildness=config.shape_wildness,
        )
        self._total_paths = len(self._shape_candidates)

    def __iter__(self) -> Iterator[list[str]]:
        for candidate in self._shape_candidates:
            yield list(candidate)
        if self._then_graph:
            yield from super().__iter__()

    def _calculate_total_paths(self) -> int:
        # Report the bounded shape count; the optional graph fallback is unbounded
        # and would be centuries, so it is not included in the progress total.
        return len(self._shape_candidates)
