from rich.console import Console

from gapbf.Config import Config
from gapbf.Output import Output
from gapbf.PathHandler import PathHandler


class TestPathHandlerBase:
    def test_pathhandler_init_uses_provided_config(self):
        class ConcreteHandler(PathHandler):
            def handle_path(self, path, total_paths=None):
                return False, None

        config = Config(grid_size=3, path_min_length=4, path_max_length=9)
        handler = ConcreteHandler(config, Output(Console(record=True)))
        assert handler.config == config