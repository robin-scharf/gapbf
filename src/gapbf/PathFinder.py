import logging
from concurrent.futures import Future
from threading import Lock

from .Config import valid_nodes_for_grid
from .pathfinder_async import _run_async, calculate_total_paths_async
from .pathfinder_counting import (
    build_indexed_moves,
    build_move_candidates,
    build_suffix_transitions,
    count_paths_via_dp,
    initial_count_states,
)
from .pathfinder_geometry import (
    build_crossing_cache,
    build_immediate_neighbors,
    build_intermediate_node_cache,
)
from .pathfinder_traversal import PathFinderTraversalMixin
from .PathHandler import PathHandler


class PathFinder(PathFinderTraversalMixin):
    """Generate Android pattern paths using Android-style legality rules."""

    _graphs: dict[int, dict[str, list[str]]] = {
        size: {"graph": valid_nodes_for_grid(size)} for size in (3, 4, 5, 6)
    }

    def __init__(
        self,
        grid_size: int,
        path_min_len: int = 4,
        path_max_len: int = 36,
        path_max_node_distance: int | None = None,
        path_prefix: list[str] | None = None,
        path_suffix: list[str] | None = None,
        excluded_nodes: list[str] | None = None,
        no_diagonal_crossings: bool = False,
        no_perpendicular_crossings: bool = False,
    ):
        if grid_size not in self._graphs:
            raise ValueError(
                f"Unsupported grid size: {grid_size}. Supported sizes: {list(self._graphs.keys())}"
            )

        self._grid_size = grid_size
        self._graph = list(self._graphs[grid_size]["graph"])
        self._node_to_index = {node: index for index, node in enumerate(self._graph)}
        self._node_masks = tuple(1 << index for index in range(len(self._graph)))
        self._coordinates = {
            node: (index % grid_size, index // grid_size) for index, node in enumerate(self._graph)
        }
        self._nodes_by_coordinate = {
            coordinate: node for node, coordinate in self._coordinates.items()
        }
        self._intermediate_nodes = build_intermediate_node_cache(
            self._graph,
            self._coordinates,
            self._nodes_by_coordinate,
        )
        self._neighbors = build_immediate_neighbors(self._graph, self._intermediate_nodes)
        self._crossing_cache = build_crossing_cache(
            self._graph,
            self._coordinates,
            self._node_to_index,
        )

        self._handlers: list[PathHandler] = []
        self._total_paths: int | None = None
        self._total_paths_future: Future[int] | None = None
        self._total_paths_lock = Lock()
        self._path_min_len = path_min_len
        self._path_max_len = path_max_len
        self._path_max_node_distance = (
            path_max_node_distance if path_max_node_distance is not None else grid_size - 1
        )
        self._no_diagonal_crossings = no_diagonal_crossings
        self._no_perpendicular_crossings = no_perpendicular_crossings
        self._path_prefix = [str(node) for node in path_prefix] if path_prefix else []
        self._path_suffix = [str(node) for node in path_suffix] if path_suffix else []
        self._excluded_nodes = {str(node) for node in excluded_nodes} if excluded_nodes else set()

        self.logger = logging.getLogger(__name__)
        self._validate_prefix()
        self._move_candidates = build_move_candidates(
            self._graph,
            self._excluded_nodes,
            self._intermediate_nodes,
            self._is_within_max_node_distance,
        )
        self._indexed_moves = build_indexed_moves(
            self._graph,
            self._move_candidates,
            self._node_to_index,
            self._node_masks,
        )
        self._suffix_index_sequence = tuple(
            self._node_to_index[node] for node in self._path_suffix if node in self._node_to_index
        )
        self._suffix_transitions = build_suffix_transitions(
            self._suffix_index_sequence,
            len(self._graph),
        )

    @property
    def handlers(self) -> list[PathHandler]:
        return self._handlers

    @property
    def total_paths(self) -> int:
        if self._total_paths is None:
            self._total_paths = self._calculate_total_paths()
        return self._total_paths

    @property
    def grid_nodes(self) -> list[str]:
        return self._graph

    def add_handler(self, handler: PathHandler) -> None:
        if not isinstance(handler, PathHandler):
            raise TypeError(f"Expected PathHandler, got {type(handler).__name__}")
        self._handlers.append(handler)
        self.logger.debug(f"Added handler: {handler.__class__.__name__}")

    def process_path(
        self, path: list[str], total_paths: int | None = None
    ) -> tuple[bool, list[str] | None]:
        for handler in self._handlers:
            success, result_path = handler.handle_path(path, total_paths)
            if success:
                return True, result_path
        return False, None

    def calculate_total_paths_async(self) -> Future[int]:
        with self._total_paths_lock:
            if self._total_paths is not None:
                future: Future[int] = Future()
                future.set_result(self._total_paths)
                return future

            if self._total_paths_future is not None and not self._total_paths_future.done():
                return self._total_paths_future

            def calculate_and_cache() -> int:
                total_paths = self._calculate_total_paths()
                with self._total_paths_lock:
                    self._total_paths = total_paths
                return total_paths

            future = _run_async(calculate_and_cache)
            self._total_paths_future = future
            return future

    def _calculate_total_paths(self) -> int:
        if self._selected_crossing_types():
            total_paths = self._count_paths_via_dfs()
            if total_paths == 0:
                raise ValueError("No paths found with given configuration. Check constraints.")
            self.logger.info(
                "Calculated %s total possible paths with DFS fallback for crossing constraints",
                total_paths,
            )
            return total_paths

        total_paths = count_paths_via_dp(
            initial_count_states(
                self._graph,
                self._path_prefix,
                self._excluded_nodes,
                self._node_to_index,
                self._node_masks,
                self._suffix_transitions,
            ),
            self._indexed_moves,
            self._node_masks,
            self._suffix_transitions,
            len(self._suffix_index_sequence),
            self._path_min_len,
            self._path_max_len,
        )

        if total_paths == 0:
            raise ValueError("No paths found with given configuration. Check constraints.")

        self.logger.info(f"Calculated {total_paths} total possible paths")
        return total_paths


__all__ = ["PathFinder", "calculate_total_paths_async"]
