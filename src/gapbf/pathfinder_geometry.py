from __future__ import annotations

from math import gcd

EdgeKey = tuple[str, str]
CrossingCache = dict[str, dict[EdgeKey, frozenset[EdgeKey]]]


def build_intermediate_node_cache(
    graph: list[str],
    coordinates: dict[str, tuple[int, int]],
    nodes_by_coordinate: dict[tuple[int, int], str],
) -> dict[tuple[str, str], tuple[str, ...]]:
    intermediate_nodes: dict[tuple[str, str], tuple[str, ...]] = {}

    for start in graph:
        start_x, start_y = coordinates[start]
        for end in graph:
            if start == end:
                continue

            end_x, end_y = coordinates[end]
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
                blocker = nodes_by_coordinate.get(coordinate)
                if blocker is not None:
                    blockers.append(blocker)

            intermediate_nodes[(start, end)] = tuple(blockers)

    return intermediate_nodes


def build_immediate_neighbors(
    graph: list[str],
    intermediate_nodes: dict[tuple[str, str], tuple[str, ...]],
) -> dict[str, list[str]]:
    neighbors: dict[str, list[str]] = {node: [] for node in graph}
    for start in graph:
        for end in graph:
            if start == end:
                continue
            if not intermediate_nodes[(start, end)]:
                neighbors[start].append(end)
    return neighbors


def canonical_edge_key(start: str, end: str, node_to_index: dict[str, int]) -> EdgeKey:
    if node_to_index[start] <= node_to_index[end]:
        return (start, end)
    return (end, start)


def classify_segment_crossing(
    first: EdgeKey,
    second: EdgeKey,
    coordinates: dict[str, tuple[int, int]],
) -> frozenset[str]:
    first_start, first_end = first
    second_start, second_end = second

    if len({first_start, first_end, second_start, second_end}) < 4:
        return frozenset()

    first_start_point = coordinates[first_start]
    first_end_point = coordinates[first_end]
    second_start_point = coordinates[second_start]
    second_end_point = coordinates[second_end]

    def orientation(
        point_a: tuple[int, int], point_b: tuple[int, int], point_c: tuple[int, int]
    ) -> int:
        return ((point_b[0] - point_a[0]) * (point_c[1] - point_a[1])) - (
            (point_b[1] - point_a[1]) * (point_c[0] - point_a[0])
        )

    first_orientation_start = orientation(
        first_start_point, first_end_point, second_start_point
    )
    first_orientation_end = orientation(first_start_point, first_end_point, second_end_point)
    second_orientation_start = orientation(
        second_start_point, second_end_point, first_start_point
    )
    second_orientation_end = orientation(
        second_start_point, second_end_point, first_end_point
    )

    properly_intersects = (
        first_orientation_start * first_orientation_end < 0
        and second_orientation_start * second_orientation_end < 0
    )
    if not properly_intersects:
        return frozenset()

    first_dx = first_end_point[0] - first_start_point[0]
    first_dy = first_end_point[1] - first_start_point[1]
    second_dx = second_end_point[0] - second_start_point[0]
    second_dy = second_end_point[1] - second_start_point[1]

    crossing_types: set[str] = set()
    if first_dx != 0 and first_dy != 0 and second_dx != 0 and second_dy != 0:
        crossing_types.add("diagonal")
    if (first_dx * second_dx) + (first_dy * second_dy) == 0:
        crossing_types.add("perpendicular")

    return frozenset(crossing_types)


def build_crossing_cache(
    graph: list[str],
    coordinates: dict[str, tuple[int, int]],
    node_to_index: dict[str, int],
) -> CrossingCache:
    edges: list[EdgeKey] = []
    for start_index, start in enumerate(graph):
        for end in graph[start_index + 1 :]:
            edges.append(canonical_edge_key(start, end, node_to_index))

    diagonal_crossings: dict[EdgeKey, set[EdgeKey]] = {edge: set() for edge in edges}
    perpendicular_crossings: dict[EdgeKey, set[EdgeKey]] = {edge: set() for edge in edges}

    for index, edge in enumerate(edges):
        for other_edge in edges[index + 1 :]:
            crossing_types = classify_segment_crossing(edge, other_edge, coordinates)
            if "diagonal" in crossing_types:
                diagonal_crossings[edge].add(other_edge)
                diagonal_crossings[other_edge].add(edge)
            if "perpendicular" in crossing_types:
                perpendicular_crossings[edge].add(other_edge)
                perpendicular_crossings[other_edge].add(edge)

    return {
        "diagonal": {edge: frozenset(crossings) for edge, crossings in diagonal_crossings.items()},
        "perpendicular": {
            edge: frozenset(crossings) for edge, crossings in perpendicular_crossings.items()
        },
    }