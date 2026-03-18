import os
import tempfile
from unittest.mock import Mock, patch

import pytest
import yaml

from gapbf.Config import Config
from gapbf.Database import RunDatabase
from gapbf.PathFinder import PathFinder
from gapbf.PathHandler import ADBHandler, PrintHandler
from gapbf.PathHandler import TestHandler as GapbfTestHandler


class TestFullIntegration:
    """Integration tests that test the complete system."""

    def test_config_to_pathfinder_integration(self):
        """Test that Config integrates properly with PathFinder."""
        # Create a temporary config file
        config_data = {
            "grid_size": 3,
            "path_min_length": 4,
            "path_max_length": 6,
            "path_max_node_distance": 1,
            "path_prefix": [1, 2],
            "path_suffix": [8, 9],
            "excluded_nodes": [5],
            "attempt_delay": 10.0,
            "test_path": [1, 2, 3, 4],
            "stdout_normal": "Failed",
            "stdout_success": "Success",
            "stdout_error": "Error",
            "adb_timeout": 30,
            "total_paths": 0,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            # Load config
            config = Config.load_config(config_file)

            # Create PathFinder with config values
            pf = PathFinder(
                grid_size=config.grid_size,
                path_min_len=config.path_min_length,
                path_max_len=config.path_max_length,
                path_max_node_distance=config.path_max_node_distance,
                path_prefix=config.path_prefix,
                path_suffix=config.path_suffix,
                excluded_nodes=config.excluded_nodes,
            )

            # Verify PathFinder uses config values correctly
            assert pf._grid_size == 3
            assert pf._path_min_len == 4
            assert pf._path_max_len == 6
            assert pf._path_prefix == ["1", "2"]  # Nodes are strings
            assert pf._path_suffix == ["8", "9"]  # Nodes are strings
            assert pf._excluded_nodes == {"5"}  # Nodes are strings

        finally:
            os.unlink(config_file)

    def test_pathfinder_with_test_handler_integration(self):
        """Test PathFinder working with TestHandler end-to-end."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config_data = {
                "grid_size": 3,
                "path_min_length": 4,
                "path_max_length": 5,
                "path_prefix": [1],
                "path_suffix": [5],
                "test_path": [1, 2, 3, 6, 5],
                "excluded_nodes": [],
                "stdout_normal": "Failed",
                "stdout_success": "Success",
                "stdout_error": "Error",
                "total_paths": 0,
            }
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            mock_config = Config.load_config(config_file)

            pf = PathFinder(
                grid_size=3,
                path_min_len=4,
                path_max_len=5,
                path_prefix=[1],
                path_suffix=[5],
                excluded_nodes=[],
            )

            test_handler = GapbfTestHandler(mock_config, Mock())
            pf.add_handler(test_handler)

            success, found_path = pf.dfs()

            assert success is True
            assert found_path == ["1", "2", "3", "6", "5"]

        finally:
            os.unlink(config_file)

    @patch("subprocess.run")
    def test_pathfinder_with_adb_handler_integration(self, mock_subprocess):
        """Test PathFinder working with ADBHandler (mocked)."""
        db_path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config_data = {
                "grid_size": 3,
                "path_min_length": 4,
                "path_max_length": 4,
                "path_prefix": [1],
                "path_suffix": [],
                "excluded_nodes": [],
                "attempt_delay": 0,
                "stdout_normal": "Failed to decrypt",
                "stdout_success": "Data successfully decrypted",
                "stdout_error": "Error",
                "db_path": db_path,
                "echo_commands": False,
                "adb_timeout": 30,
                "total_paths": 0,
            }
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            mock_config = Config.load_config(config_file)
            database = RunDatabase(mock_config.db_path)
            run = database.create_run(mock_config, "SERIAL123", "a")

            def mock_adb_response(command, **kwargs):
                if command[:2] == ["adb", "start-server"]:
                    result = Mock()
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""
                    return result
                if "decrypt" in command and "1236" in command:
                    result = Mock()
                    result.returncode = 0
                    result.stdout = "Data successfully decrypted"
                    result.stderr = ""
                    return result

                result = Mock()
                result.returncode = 0
                result.stdout = "Failed to decrypt"
                result.stderr = ""
                return result

            mock_subprocess.side_effect = mock_adb_response

            pf = PathFinder(
                grid_size=3,
                path_min_len=4,
                path_max_len=4,
                path_prefix=[1],
                path_suffix=[],
                excluded_nodes=[],
            )

            adb_handler = ADBHandler(
                mock_config,
                database=database,
                run_id=run.run_id,
                device_id="SERIAL123",
                output=Mock(),
            )
            pf.add_handler(adb_handler)

            success, found_path = pf.dfs()

            assert success is True
            assert found_path == ["1", "2", "3", "6"]
            logged = database.get_attempted_paths(mock_config, "SERIAL123")
            assert "1236" in logged
            database.close()

        finally:
            os.unlink(config_file)
            os.unlink(db_path)

    def test_multiple_handlers_priority(self):
        """Test that multiple handlers work and first success is returned."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config_data = {
                "grid_size": 3,
                "path_min_length": 4,
                "path_max_length": 4,
                "test_path": [1, 2, 3, 6],
                "path_prefix": [],
                "path_suffix": [],
                "excluded_nodes": [],
                "stdout_normal": "Failed",
                "stdout_success": "Success",
                "stdout_error": "Error",
                "total_paths": 0,
            }
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            mock_config = Config.load_config(config_file)

            pf = PathFinder(
                grid_size=3,
                path_min_len=4,
                path_max_len=4,
                path_prefix=[],
                path_suffix=[],
                excluded_nodes=[],
            )

            print_handler = PrintHandler(mock_config, pf.grid_nodes, Mock())
            test_handler = GapbfTestHandler(mock_config, Mock())

            pf.add_handler(print_handler)
            pf.add_handler(test_handler)

            success, found_path = pf.dfs()

            assert success is True
            assert found_path == ["1", "2", "3", "6"]

        finally:
            os.unlink(config_file)

    def test_constraint_validation_end_to_end(self):
        """Test that constraints are properly enforced end-to-end."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config_data = {
                "grid_size": 3,
                "path_min_length": 5,
                "path_max_length": 5,
                "path_prefix": [1, 2],
                "path_suffix": [9],
                "excluded_nodes": [5],  # Exclude center node
                "test_path": [1, 2, 3, 6, 9],  # Valid path meeting all constraints
                "stdout_normal": "Failed",
                "stdout_success": "Success",
                "stdout_error": "Error",
                "total_paths": 0,
            }
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            mock_config = Config.load_config(config_file)

            pf = PathFinder(
                grid_size=3,
                path_min_len=5,
                path_max_len=5,
                path_prefix=[1, 2],
                path_suffix=[9],
                excluded_nodes=[5],
            )

            attempted_paths = []

            class TrackingHandler(GapbfTestHandler):
                def handle_path(self, path, total_paths=None):
                    attempted_paths.append(path.copy())
                    return super().handle_path(path, total_paths)

            tracking_handler = TrackingHandler(mock_config, Mock())
            pf.add_handler(tracking_handler)

            success, found_path = pf.dfs()

            assert success is True
            assert found_path == ["1", "2", "3", "6", "9"]

            for path in attempted_paths:
                assert len(path) == 5
                assert path[0] == "1" and path[1] == "2"
                assert path[-1] == "9"
                assert "5" not in path

        finally:
            os.unlink(config_file)


class TestErrorHandling:
    """Test error handling across the system."""

    def test_invalid_config_file_handling(self):
        """Test system handles invalid config files gracefully."""
        with pytest.raises(ValueError, match="Configuration file not found"):
            Config.load_config("nonexistent_file.yaml")

    def test_unsupported_grid_size_handling(self):
        """Test system handles unsupported grid sizes gracefully."""
        with pytest.raises(ValueError, match="Unsupported grid size"):
            PathFinder(grid_size=10, path_min_len=4, path_max_len=9)

    def test_impossible_constraints_handling(self):
        """Test system handles impossible constraints gracefully."""
        pf = PathFinder(
            grid_size=3,
            path_min_len=20,  # Impossible for 3x3 grid
            path_max_len=25,
            path_prefix=[],
            path_suffix=[],
            excluded_nodes=[],
        )

        with pytest.raises(ValueError, match="No paths found with given configuration"):
            pf._calculate_total_paths()

    @patch("subprocess.run")
    def test_adb_subprocess_error_handling(self, mock_subprocess):
        """Test ADB handler handles subprocess errors gracefully."""
        mock_subprocess.side_effect = Exception("ADB not found")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config_data = {
                "grid_size": 3,
                "stdout_normal": "Failed",
                "stdout_success": "Success",
                "stdout_error": "Error",
                "adb_timeout": 30,
                "attempt_delay": 100,
                "total_paths": 100,
            }
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            mock_config = Config.load_config(config_file)
            database = Mock()
            database.get_attempted_paths.return_value = set()

            with pytest.raises(Exception, match="ADB not found"):
                ADBHandler(
                    mock_config,
                    database=database,
                    run_id="run-1",
                    device_id="SERIAL123",
                    output=Mock(),
                )

        finally:
            os.unlink(config_file)
