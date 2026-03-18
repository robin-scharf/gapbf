import logging
from concurrent.futures import Future
from math import gcd
from threading import Lock

from .Config import valid_nodes_for_grid
from .pathfinder_async import _run_async, calculate_total_paths_async
from .PathHandler import PathHandler


class PathFinder:
    """Generate Android pattern paths using Android-style legality rules."""

    _graphs: dict[int, dict[str, list[str]]] = {
        size: {"graph": valid_nodes_for_grid(size)} for size in (3, 4, 5, 6)
    }

    def __init__(
        self,
        grid_size: int,
        path_min_len: int = 4,
        path_max_len: int = 36,
        path_max_node_distance: int = 1,
        path_prefix: list[str] | None = None,
        path_suffix: list[str] | None = None,
        excluded_nodes: list[str] | None = None,
    ):
        if grid_size not in self._graphs:
            raise ValueError(
                f"Unsupported grid size: {grid_size}. Supported sizes: {list(self._graphs.keys())}"
            )

        self._grid_size = grid_size
        self._graph = list(self._graphs[grid_size]["graph"])
        self._coordinates = {
            node: (index % grid_size, index // grid_size) for index, node in enumerate(self._graph)
        }
        self._nodes_by_coordinate = {
            coordinate: node for node, coordinate in self._coordinates.items()
        }
        self._intermediate_nodes = self._build_intermediate_node_cache()
        self._neighbors = self._build_immediate_neighbors()

        self._handlers: list[PathHandler] = []
        self._total_paths: int | None = None
        self._total_paths_future: Future[int] | None = None
        self._total_paths_lock = Lock()
        self._path_min_len = path_min_len
        self._path_max_len = path_max_len
        self._path_max_node_distance = path_max_node_distance
        self._path_prefix = [str(node) for node in path_prefix] if path_prefix else []
        self._path_suffix = [str(node) for node in path_suffix] if path_suffix else []
        self._excluded_nodes = {str(node) for node in excluded_nodes} if excluded_nodes else set()

        self.logger = logging.getLogger(__name__)
        self._validate_prefix()

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

    def _build_intermediate_node_cache(self) -> dict[tuple[str, str], tuple[str, ...]]:
        intermediate_nodes: dict[tuple[str, str], tuple[str, ...]] = {}

        for start in self._graph:
            start_x, start_y = self._coordinates[start]
            for end in self._graph:
                if start == end:
                    continue

                end_x, end_y = self._coordinates[end]
                dx = end_x - start_x
                dy = end_y - start_y
                steps = gcd(abs(dx), abs(dy))

                if steps <= 1:
                    intermediate_nodes[(start, end)] = ()
                    continue

                step_x = dx // steps
                step_y = dy // steps
                blockers = []
                for step in range(1, steps):
                    coordinate = (start_x + (step_x * step), start_y + (step_y * step))
                    blocker = self._nodes_by_coordinate.get(coordinate)
                    if blocker is not None:
                        blockers.append(blocker)

                intermediate_nodes[(start, end)] = tuple(blockers)

        return intermediate_nodes

    def _build_immediate_neighbors(self) -> dict[str, list[str]]:
        neighbors: dict[str, list[str]] = {node: [] for node in self._graph}
        for start in self._graph:
            for end in self._graph:
                if start == end:
                    continue
                if not self._intermediate_nodes[(start, end)]:
                    neighbors[start].append(end)
        return neighbors

    def _validate_prefix(self) -> None:
        if not self._path_prefix:
            return
        visited: set[str] = set()
        previous: str | None = None
        for node in self._path_prefix:
            if node in self._excluded_nodes:
                raise ValueError(f"path_prefix contains excluded node: {node}")
            if node in visited:
                raise ValueError("path_prefix cannot revisit nodes")
            if previous is not None and not self._is_move_legal(previous, node, visited):
                raise ValueError(f"illegal move in path_prefix: {previous} -> {node}")
            visited.add(node)
            previous = node

    def _is_move_legal(self, start: str, end: str, visited: set[str]) -> bool:
        if start == end or end in visited or end in self._excluded_nodes:
            return False
        if not self._is_within_max_node_distance(start, end):
            return False
        blockers = self._intermediate_nodes[(start, end)]
        return all(blocker in visited for blocker in blockers)

    def _is_within_max_node_distance(self, start: str, end: str) -> bool:
        start_x, start_y = self._coordinates[start]
        end_x, end_y = self._coordinates[end]
        return max(abs(end_x - start_x), abs(end_y - start_y)) <= self._path_max_node_distance

    def _legal_moves(self, node: str, visited: set[str]) -> list[str]:
        return [
            candidate for candidate in self._graph if self._is_move_legal(node, candidate, visited)
        ]

    def _path_matches_constraints(self, path: list[str]) -> bool:
        if len(path) < self._path_min_len:
            return False
        if not self._path_suffix:
            return True
        if len(path) < len(self._path_suffix):
            return False
        return path[-len(self._path_suffix) :] == self._path_suffix

    def _initial_search_states(self) -> list[tuple[str, list[str], set[str]]]:
        if self._path_prefix:
            initial_path = list(self._path_prefix[:-1])
            initial_visited = set(initial_path)
            return [(self._path_prefix[-1], initial_path, initial_visited)]
        return [(node, [], set()) for node in self._graph if node not in self._excluded_nodes]

    def _generate_paths(self, node: str, path: list[str], visited: set[str]):
        path.append(node)
        visited.add(node)
        try:
            if self._path_matches_constraints(path):
                yield list(path)
            if len(path) >= self._path_max_len:
                return
            for neighbor in self._legal_moves(node, visited):
                yield from self._generate_paths(neighbor, path, visited)
        finally:
            path.pop()
            visited.discard(node)

    def __iter__(self):
        for start_node, path, visited in self._initial_search_states():
            yield from self._generate_paths(start_node, path, visited)

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
        total_paths = 0

        def dfs_counter(node: str, path: list[str], visited: set[str]) -> None:
            nonlocal total_paths
            path.append(node)
            visited.add(node)
            try:
                if self._path_matches_constraints(path):
                    total_paths += 1
                if len(path) >= self._path_max_len:
                    return
                for neighbor in self._legal_moves(node, visited):
                    dfs_counter(neighbor, path, visited)
            finally:
                path.pop()
                visited.discard(node)

        for start_node, path, visited in self._initial_search_states():
            dfs_counter(start_node, path, visited)

        if total_paths == 0:
            raise ValueError("No paths found with given configuration. Check constraints.")

        self.logger.info(f"Calculated {total_paths} total possible paths")
        return total_paths

    def dfs(self, total_paths: int | None = None) -> tuple[bool, list[str]]:
        for path in self:
            success, result_path = self.process_path(path, total_paths)
            if success:
                return True, result_path or path
        return False, []


__all__ = ["PathFinder", "calculate_total_paths_async"]
