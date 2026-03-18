from .Config import Config
from .Output import Output
from .pathhandler_common import PathHandler


class TestHandler(PathHandler):
    def __init__(self, config: Config, output: Output):
        super().__init__(config, output)
        self.test_path = list(config.test_path)
        self.current_path_number = 0
        self.output.show_test_configuration(
            grid_size=config.grid_size,
            path_max_node_distance=config.path_max_node_distance,
            path_prefix=config.path_prefix,
            path_suffix=config.path_suffix,
            excluded_nodes=config.excluded_nodes,
            test_path=self.test_path,
        )

    def handle_path(
        self, path: list[str], total_paths: int | None = None
    ) -> tuple[bool, list[str] | None]:
        self.current_path_number += 1
        percentage = (self.current_path_number / total_paths * 100) if total_paths else 0

        if path == self.test_path:
            self.output.show_test_result(
                success=True,
                current=self.current_path_number,
                total=total_paths,
                percentage=percentage,
                path=path,
            )
            return True, path

        self.output.show_test_result(
            success=False,
            current=self.current_path_number,
            total=total_paths,
            percentage=percentage,
            path=path,
        )
        return False, None


class PrintHandler(PathHandler):
    def __init__(self, config: Config, grid_nodes: list[str], output: Output):
        super().__init__(config, output)
        self.grid_size = config.grid_size
        self.grid_nodes = grid_nodes
        self.node_positions = {}
        for index, node in enumerate(grid_nodes):
            row = index // self.grid_size
            col = index % self.grid_size
            self.node_positions[(row, col)] = node

    def handle_path(
        self, path: list[str], total_paths: int | None = None
    ) -> tuple[bool, list[str] | None]:
        path_rows = self.render_path(path)
        steps_rows = self.render_path_steps(path)
        self.output.show_print_path(path, path_rows, steps_rows)
        return False, None

    def render_path(self, path: list[str]) -> list[str]:
        rows = []
        for y in range(self.grid_size):
            row = []
            for x in range(self.grid_size):
                node_value = self.node_positions.get((y, x))
                row.append("●" if node_value in path else "○")
            rows.append("".join(row))
        return rows

    def render_path_steps(self, path: list[str]) -> list[str]:
        rows = []
        for y in range(self.grid_size):
            row = []
            for x in range(self.grid_size):
                node_value = self.node_positions.get((y, x))
                if node_value in path:
                    row.append(f"{path.index(node_value) + 1}")
                else:
                    row.append("·")
            rows.append(" ".join(row))
        return rows
