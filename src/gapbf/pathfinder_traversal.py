from __future__ import annotations

from .pathfinder_geometry import canonical_edge_key


class PathFinderTraversalMixin:
    _path_prefix: list[str]
    _path_suffix: list[str]
    _excluded_nodes: set[str]
    _node_to_index: dict[str, int]
    _no_diagonal_crossings: bool
    _no_perpendicular_crossings: bool
    _crossing_cache: dict[str, dict[tuple[str, str], frozenset[tuple[str, str]]]]
    _intermediate_nodes: dict[tuple[str, str], tuple[str, ...]]
    _coordinates: dict[str, tuple[int, int]]
    _path_max_node_distance: int
    _move_candidates: dict[str, tuple[tuple[str, tuple[str, ...]], ...]]
    _path_min_len: int
    _path_max_len: int
    _graph: list[str]

    def process_path(
        self,
        path: list[str],
        total_paths: int | None = None,
    ) -> tuple[bool, list[str] | None]:
        raise NotImplementedError

    def _validate_prefix(self) -> None:
        if not self._path_prefix:
            return
        visited: set[str] = set()
        used_edges: set[tuple[str, str]] = set()
        previous: str | None = None
        for node in self._path_prefix:
            if node in self._excluded_nodes:
                raise ValueError(f"path_prefix contains excluded node: {node}")
            if node in visited:
                raise ValueError("path_prefix cannot revisit nodes")
            if previous is not None and not self._is_move_legal(
                previous,
                node,
                visited,
                used_edges,
            ):
                raise ValueError(f"illegal move in path_prefix: {previous} -> {node}")
            if previous is not None:
                used_edges.add(self._canonical_edge(previous, node))
            visited.add(node)
            previous = node

    def _canonical_edge(self, start: str, end: str) -> tuple[str, str]:
        return canonical_edge_key(start, end, self._node_to_index)

    def _selected_crossing_types(self) -> tuple[str, ...]:
        crossing_types: list[str] = []
        if self._no_diagonal_crossings:
            crossing_types.append("diagonal")
        if self._no_perpendicular_crossings:
            crossing_types.append("perpendicular")
        return tuple(crossing_types)

    def _violates_crossing_constraints(
        self, start: str, end: str, used_edges: set[tuple[str, str]]
    ) -> bool:
        crossing_types = self._selected_crossing_types()
        if not crossing_types or not used_edges:
            return False

        candidate_edge = self._canonical_edge(start, end)
        return any(
            any(
                edge in used_edges
                for edge in self._crossing_cache[crossing_type][candidate_edge]
            )
            for crossing_type in crossing_types
        )

    def _is_move_legal(
        self,
        start: str,
        end: str,
        visited: set[str],
        used_edges: set[tuple[str, str]],
    ) -> bool:
        if start == end or end in visited or end in self._excluded_nodes:
            return False
        if not self._is_within_max_node_distance(start, end):
            return False
        blockers = self._intermediate_nodes[(start, end)]
        if not all(blocker in visited for blocker in blockers):
            return False
        return not self._violates_crossing_constraints(start, end, used_edges)

    def _is_within_max_node_distance(self, start: str, end: str) -> bool:
        start_x, start_y = self._coordinates[start]
        end_x, end_y = self._coordinates[end]
        return (
            max(abs(end_x - start_x), abs(end_y - start_y))
            <= self._path_max_node_distance
        )

    def _legal_moves(
        self, node: str, visited: set[str], used_edges: set[tuple[str, str]]
    ) -> list[str]:
        return [
            candidate
            for candidate, blockers in self._move_candidates[node]
            if candidate not in visited
            and all(blocker in visited for blocker in blockers)
            and not self._violates_crossing_constraints(node, candidate, used_edges)
        ]

    def _path_matches_constraints(self, path: list[str]) -> bool:
        if len(path) < self._path_min_len:
            return False
        if not self._path_suffix:
            return True
        if len(path) < len(self._path_suffix):
            return False
        return path[-len(self._path_suffix) :] == self._path_suffix

    def _initial_search_states(
        self,
    ) -> list[tuple[str, list[str], set[str], set[tuple[str, str]]]]:
        if self._path_prefix:
            initial_path = list(self._path_prefix[:-1])
            initial_visited = set(initial_path)
            initial_edges = {
                self._canonical_edge(start, end)
                for start, end in zip(initial_path, initial_path[1:])
            }
            return [
                (self._path_prefix[-1], initial_path, initial_visited, initial_edges)
            ]
        return [
            (node, [], set(), set())
            for node in self._graph
            if node not in self._excluded_nodes
        ]

    def _generate_paths(
        self,
        node: str,
        path: list[str],
        visited: set[str],
        used_edges: set[tuple[str, str]],
    ):
        added_edge: tuple[str, str] | None = None
        if path:
            added_edge = self._canonical_edge(path[-1], node)
            used_edges.add(added_edge)
        path.append(node)
        visited.add(node)
        try:
            if self._path_matches_constraints(path):
                yield list(path)
            if len(path) >= self._path_max_len:
                return
            for neighbor in self._legal_moves(node, visited, used_edges):
                yield from self._generate_paths(neighbor, path, visited, used_edges)
        finally:
            path.pop()
            visited.discard(node)
            if added_edge is not None:
                used_edges.discard(added_edge)

    def __iter__(self):
        for start_node, path, visited, used_edges in self._initial_search_states():
            yield from self._generate_paths(start_node, path, visited, used_edges)

    def _count_paths_via_dfs(self) -> int:
        total_paths = 0

        def count_from(
            node: str,
            path: list[str],
            visited: set[str],
            used_edges: set[tuple[str, str]],
        ) -> None:
            nonlocal total_paths

            added_edge: tuple[str, str] | None = None
            if path:
                added_edge = self._canonical_edge(path[-1], node)
                used_edges.add(added_edge)

            path.append(node)
            visited.add(node)
            try:
                if self._path_matches_constraints(path):
                    total_paths += 1
                if len(path) >= self._path_max_len:
                    return
                for neighbor in self._legal_moves(node, visited, used_edges):
                    count_from(neighbor, path, visited, used_edges)
            finally:
                path.pop()
                visited.discard(node)
                if added_edge is not None:
                    used_edges.discard(added_edge)

        for start_node, path, visited, used_edges in self._initial_search_states():
            count_from(start_node, path, visited, used_edges)

        return total_paths

    def dfs(self, total_paths: int | None = None) -> tuple[bool, list[str]]:
        for path in self:
            success, result_path = self.process_path(path, total_paths)
            if success:
                return True, result_path or path
        return False, []