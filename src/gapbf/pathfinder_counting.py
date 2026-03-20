from __future__ import annotations

from functools import lru_cache
from typing import Callable

MoveCandidates = dict[str, tuple[tuple[str, tuple[str, ...]], ...]]
IndexedMoves = tuple[tuple[tuple[int, int], ...], ...]
CountState = tuple[int, int, int]


def build_move_candidates(
    graph: list[str],
    excluded_nodes: set[str],
    intermediate_nodes: dict[tuple[str, str], tuple[str, ...]],
    is_within_max_node_distance: Callable[[str, str], bool],
) -> MoveCandidates:
    move_candidates: MoveCandidates = {}

    for start in graph:
        candidates: list[tuple[str, tuple[str, ...]]] = []
        for end in graph:
            if start == end or end in excluded_nodes:
                continue
            if not is_within_max_node_distance(start, end):
                continue
            candidates.append((end, intermediate_nodes[(start, end)]))
        move_candidates[start] = tuple(candidates)

    return move_candidates


def build_indexed_moves(
    graph: list[str],
    move_candidates: MoveCandidates,
    node_to_index: dict[str, int],
    node_masks: tuple[int, ...],
) -> IndexedMoves:
    indexed_moves: list[tuple[tuple[int, int], ...]] = []

    for start in graph:
        candidates: list[tuple[int, int]] = []
        for end, blockers in move_candidates[start]:
            blocker_mask = 0
            for blocker in blockers:
                blocker_mask |= node_masks[node_to_index[blocker]]
            candidates.append((node_to_index[end], blocker_mask))
        indexed_moves.append(tuple(candidates))

    return tuple(indexed_moves)


def build_suffix_transitions(
    suffix_sequence: tuple[int, ...],
    alphabet_size: int,
) -> tuple[tuple[int, ...], ...]:
    if not suffix_sequence:
        return ()

    pattern_length = len(suffix_sequence)
    prefix_table = [0] * pattern_length
    matched = 0
    for index in range(1, pattern_length):
        while matched > 0 and suffix_sequence[index] != suffix_sequence[matched]:
            matched = prefix_table[matched - 1]
        if suffix_sequence[index] == suffix_sequence[matched]:
            matched += 1
        prefix_table[index] = matched

    transitions: list[tuple[int, ...]] = []
    for state in range(pattern_length + 1):
        next_states: list[int] = []
        for symbol in range(alphabet_size):
            probe = prefix_table[state - 1] if state == pattern_length else state
            while probe > 0 and suffix_sequence[probe] != symbol:
                probe = prefix_table[probe - 1]
            if suffix_sequence[probe] == symbol:
                probe += 1
            next_states.append(probe)
        transitions.append(tuple(next_states))

    return tuple(transitions)


def initial_count_states(
    graph: list[str],
    path_prefix: list[str],
    excluded_nodes: set[str],
    node_to_index: dict[str, int],
    node_masks: tuple[int, ...],
    suffix_transitions: tuple[tuple[int, ...], ...],
) -> tuple[CountState, ...]:
    if path_prefix:
        visited_mask = 0
        suffix_state = 0
        for node in path_prefix:
            node_index = node_to_index[node]
            visited_mask |= node_masks[node_index]
            if suffix_transitions:
                suffix_state = suffix_transitions[suffix_state][node_index]
        last_index = node_to_index[path_prefix[-1]]
        return ((last_index, visited_mask, suffix_state),)

    states: list[CountState] = []
    for node in graph:
        if node in excluded_nodes:
            continue
        node_index = node_to_index[node]
        suffix_state = suffix_transitions[0][node_index] if suffix_transitions else 0
        states.append((node_index, node_masks[node_index], suffix_state))
    return tuple(states)


def count_paths_via_dp(
    initial_states: tuple[CountState, ...],
    indexed_moves: IndexedMoves,
    node_masks: tuple[int, ...],
    suffix_transitions: tuple[tuple[int, ...], ...],
    suffix_length: int,
    path_min_len: int,
    path_max_len: int,
) -> int:
    if suffix_transitions:

        @lru_cache(maxsize=None)
        def count_from(node_index: int, visited_mask: int, suffix_state: int) -> int:
            path_length = visited_mask.bit_count()
            total = 1 if path_length >= path_min_len and suffix_state == suffix_length else 0
            if path_length >= path_max_len:
                return total

            for next_index, blocker_mask in indexed_moves[node_index]:
                next_mask = node_masks[next_index]
                if visited_mask & next_mask:
                    continue
                if blocker_mask & ~visited_mask:
                    continue
                total += count_from(
                    next_index,
                    visited_mask | next_mask,
                    suffix_transitions[suffix_state][next_index],
                )
            return total

        return sum(
            count_from(node_index, visited_mask, suffix_state)
            for node_index, visited_mask, suffix_state in initial_states
        )

    @lru_cache(maxsize=None)
    def count_from_without_suffix(node_index: int, visited_mask: int) -> int:
        path_length = visited_mask.bit_count()
        total = 1 if path_length >= path_min_len else 0
        if path_length >= path_max_len:
            return total

        for next_index, blocker_mask in indexed_moves[node_index]:
            next_mask = node_masks[next_index]
            if visited_mask & next_mask:
                continue
            if blocker_mask & ~visited_mask:
                continue
            total += count_from_without_suffix(next_index, visited_mask | next_mask)
        return total

    return sum(
        count_from_without_suffix(node_index, visited_mask)
        for node_index, visited_mask, _ in initial_states
    )