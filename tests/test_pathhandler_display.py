from unittest.mock import Mock

from gapbf.Config import Config
from gapbf.PathHandler import PrintHandler
from gapbf.PathHandler import TestHandler as GapbfTestHandler


class TestTestHandler:
    def test_testhandler_init(self):
        config = Config(
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            test_path=["1", "2", "3", "4", "5"],
            path_prefix=["1", "2"],
            path_suffix=["4", "5"],
            excluded_nodes=["6", "7"],
        )
        handler = GapbfTestHandler(config, Mock())
        assert handler.test_path == ["1", "2", "3", "4", "5"]

    def test_handle_path_success(self):
        config = Config(
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            test_path=["1", "2", "3", "4", "5"],
        )
        reporter = Mock()
        handler = GapbfTestHandler(config, reporter)

        success, path = handler.handle_path(["1", "2", "3", "4", "5"])

        assert success is True
        assert path == ["1", "2", "3", "4", "5"]
        reporter.show_test_result.assert_called_once()

    def test_handle_path_failure(self):
        config = Config(
            grid_size=3,
            path_min_length=4,
            path_max_length=9,
            test_path=["1", "2", "3", "4", "5"],
        )
        reporter = Mock()
        handler = GapbfTestHandler(config, reporter)

        success, path = handler.handle_path(["1", "2", "3"])

        assert success is False
        assert path is None
        reporter.show_test_result.assert_called_once()


class TestPrintHandler:
    def test_printhandler_init(self):
        config = Config(grid_size=3, path_min_length=4, path_max_length=9)
        grid_nodes = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
        handler = PrintHandler(config, grid_nodes, Mock())
        assert handler.grid_size == 3

    def test_handle_path_prints_grid(self):
        config = Config(grid_size=3, path_min_length=4, path_max_length=9)
        grid_nodes = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
        reporter = Mock()
        handler = PrintHandler(config, grid_nodes, reporter)

        success, path = handler.handle_path(["1", "2", "3"])

        assert success is False
        assert path is None
        reporter.show_print_path.assert_called_once()

    def test_render_path_3x3(self):
        config = Config(grid_size=3, path_min_length=4, path_max_length=9)
        grid_nodes = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
        handler = PrintHandler(config, grid_nodes, Mock())
        grid_rows = handler.render_path(["1", "5", "9"])

        assert len(grid_rows) == 3
        assert "●" in grid_rows[0]
        assert "●" in grid_rows[1]
        assert "●" in grid_rows[2]