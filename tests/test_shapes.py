from gapbf.Config import Config
from gapbf.runtime_session import create_path_finder
from gapbf.shapes.geometry import render_multi, render_to_nodes, rotate90, walk_segment
from gapbf.shapes.library import BY_NAME, LIBRARY
from gapbf.shapes.source import ShapeCandidateSource


def _owner_cfg(**over):
    base = dict(
        grid_size=5,
        path_min_length=4,
        path_max_length=20,
        path_max_node_distance=1,
        no_diagonal_crossings=True,
        no_perpendicular_crossings=True,
    )
    base.update(over)
    return Config(**base)


class TestGeometry:
    def test_diagonal_renders_main_diagonal(self):
        assert render_to_nodes(((0.0, 0.0), (1.0, 1.0)), 5, 0, 0, 4, 4) == ["1", "7", "=", "C", "I"]

    def test_straight_run_includes_intermediate_dots(self):
        # half-width top edge must pull in the middle dot
        assert render_to_nodes(((0.0, 0.0), (1.0, 0.0)), 5, 0, 0, 2, 0) == ["1", "2", "3"]

    def test_walk_segment_unit_steps(self):
        assert walk_segment((0, 0), (4, 4)) == [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)]

    def test_rotate_four_times_identity(self):
        poly = ((0.0, 0.0), (1.0, 0.5), (0.3, 1.0))
        assert rotate90(poly, 4) == poly


class TestLibraryLegality:
    def test_initials_render_legal_on_5x5(self):
        src = ShapeCandidateSource(_owner_cfg())
        for name in ("R", "S"):
            seq = render_multi(BY_NAME[name].strokes, 5, 0, 0, 4, 4)
            assert src.is_legal(seq), (name, seq)

    def test_no_self_revisiting_template_yields_illegal_only_filtered(self):
        # every emitted candidate is a legal, non-revisiting pattern
        src = ShapeCandidateSource(_owner_cfg())
        cands = src.candidates(wildness=1)
        assert cands
        for c in cands:
            assert src.is_legal(c)
            assert len(c) == len(set(c))  # no node revisited


class TestSourceRanking:
    def test_drawn_shape_ranked_first(self):
        src = ShapeCandidateSource(_owner_cfg())
        drawn = ["1", "6", ";", "<", "7"]  # a legal drawn stroke
        assert src.is_legal(drawn)
        cands = src.candidates(drawn=[drawn], wildness=0)
        assert cands[0] == drawn

    def test_belief_prior_prefers_king_moves(self):
        # a dist-1 candidate must never rank below an otherwise-similar dist-2 one
        src = ShapeCandidateSource(_owner_cfg())
        cands = src.candidates(wildness=1)
        first_jumpy = next(
            (i for i, c in enumerate(cands) if src._max_move_distance(c) > 1), len(cands)
        )
        last_king = max(
            (i for i, c in enumerate(cands) if src._max_move_distance(c) == 1), default=-1
        )
        assert last_king < first_jumpy  # all king-move candidates come first

    def test_candidate_count_grows_with_wildness(self):
        src = ShapeCandidateSource(_owner_cfg())
        assert len(src.candidates(wildness=0)) < len(src.candidates(wildness=1))


class TestDrawnSymmetries:
    def test_drawn_line_expands_to_rotations_and_mirror(self):
        src = ShapeCandidateSource(_owner_cfg())
        syms = src.grid_symmetries(['1', '2', '3', '4', '5'])  # top edge
        assert all(src.is_legal(s) for s in syms)
        assert len({tuple(s) for s in syms}) == len(syms)  # deduped
        # a horizontal line must yield a vertical sibling
        vertical = [s for s in syms if len({src._coord[n][0] for n in s}) == 1]
        assert vertical

    def test_drawn_symmetries_dedup_against_library(self):
        src = ShapeCandidateSource(_owner_cfg())
        diag = ['1', '7', '=', 'C', 'I']  # matches the built-in line-diag
        cands = [''.join(c) for c in src.candidates(drawn=[diag], wildness=1)]
        assert cands.count('17=CI') == 1  # never duplicated with the library


class TestIntegration:
    def test_shape_mode_pathfinder(self):
        pf = create_path_finder(_owner_cfg(search_mode="shape", shape_wildness=1))
        assert type(pf).__name__ == "ShapePathFinder"
        cands = list(pf)
        assert cands and pf.total_paths == len(cands)
        assert all(all(ch in pf._node_to_index for ch in c) for c in cands)

    def test_graph_mode_unaffected(self):
        pf = create_path_finder(_owner_cfg(path_max_length=5, search_mode="graph"))
        assert type(pf).__name__ == "PathFinder"

    def test_shape_names_subset(self):
        pf = create_path_finder(
            _owner_cfg(search_mode="shape", shape_names=["R"], shape_wildness=0)
        )
        assert len(list(pf)) > 0

    def test_library_all_shapes_have_unique_names(self):
        names = [s.name for s in LIBRARY]
        assert len(names) == len(set(names))
