import pytest
from unittest.mock import Mock, patch, mock_open
from PathFinder import PathFinder
from PathHandler import PathHandler


class MockHandler(PathHandler):
    """Mock handler for testing."""
    
    def __init__(self, return_value=(False, None)):
        # Don't call super().__init__() to avoid loading config
        self.return_value = return_value
        self.called_paths = []
    
    def handle_path(self, path, total_paths=None):
        self.called_paths.append(path)
        return self.return_value


class TestPathFinder:
    """Unit tests for the PathFinder class."""
    
    def test_init_3x3_grid(self):
        """Test PathFinder initialization with 3x3 grid."""
        pf = PathFinder(
            grid_size=3,
            path_min_len=4,
            path_max_len=9,
            path_max_node_distance=1,
            path_prefix=[],
            path_suffix=[],
            excluded_nodes=[]
        )
        
        assert pf._grid_size == 3
        assert pf._path_min_len == 4
        assert pf._path_max_len == 9
        assert len(pf._graph) == 9  # 3x3 grid has 9 nodes
        assert 1 in pf._graph
        assert 9 in pf._graph

    def test_init_4x4_grid(self):
        """Test PathFinder initialization with 4x4 grid."""
        pf = PathFinder(
            grid_size=4,
            path_min_len=4,
            path_max_len=16,
            path_max_node_distance=1,
            path_prefix=[],
            path_suffix=[],
            excluded_nodes=[]
        )
        
        assert pf._grid_size == 4
        assert len(pf._graph) == 16  # 4x4 grid has 16 nodes
        assert ":" in pf._graph
        assert "@" in pf._graph

    def test_init_invalid_grid_size(self):
        """Test PathFinder with invalid grid size raises error."""
        with pytest.raises(ValueError, match="Unsupported grid size"):
            PathFinder(
                grid_size=7,  # Unsupported
                path_min_len=4,
                path_max_len=9
            )

    def test_add_handler(self):
        """Test adding handlers to PathFinder."""
        pf = PathFinder(grid_size=3, path_min_len=4, path_max_len=9)
        handler = MockHandler()
        
        pf.add_handler(handler)
        assert len(pf.handlers) == 1
        assert pf.handlers[0] == handler

    def test_process_path_success(self):
        """Test process_path returns success when handler succeeds."""
        pf = PathFinder(grid_size=3, path_min_len=4, path_max_len=9)
        success_handler = MockHandler(return_value=(True, [1, 2, 3]))
        pf.add_handler(success_handler)
        
        success, path = pf.process_path([1, 2, 3])
        assert success is True
        assert path == [1, 2, 3]

    def test_process_path_failure(self):
        """Test process_path returns failure when all handlers fail."""
        pf = PathFinder(grid_size=3, path_min_len=4, path_max_len=9)
        fail_handler = MockHandler(return_value=(False, None))
        pf.add_handler(fail_handler)
        
        success, path = pf.process_path([1, 2, 3])
        assert success is False
        assert path is None

    def test_constraints_path_prefix(self):
        """Test PathFinder respects path prefix constraint."""
        pf = PathFinder(
            grid_size=3,
            path_min_len=3,
            path_max_len=5,
            path_prefix=[1, 2]
        )
        
        assert pf._path_prefix == (1, 2)

    def test_constraints_path_suffix(self):
        """Test PathFinder respects path suffix constraint."""
        pf = PathFinder(
            grid_size=3,
            path_min_len=3,
            path_max_len=5,
            path_suffix=[8, 9]
        )
        
        assert pf._path_suffix == (8, 9)

    def test_constraints_excluded_nodes(self):
        """Test PathFinder respects excluded nodes constraint."""
        pf = PathFinder(
            grid_size=3,
            path_min_len=3,
            path_max_len=5,
            excluded_nodes=[5, 6]
        )
        
        assert pf._excluded_nodes == {5, 6}

    @patch('builtins.open', mock_open())
    @patch('yaml.safe_load')
    @patch('yaml.safe_dump')
    def test_calculate_total_paths_updates_config(self, mock_dump, mock_load):
        """Test that _calculate_total_paths updates config file."""
        mock_load.return_value = {'grid_size': 3, 'total_paths': 0}
        
        pf = PathFinder(
            grid_size=3,
            path_min_len=4,
            path_max_len=6,
            path_prefix=[],
            path_suffix=[],
            excluded_nodes=[]
        )
        
        total_paths = pf._calculate_total_paths()
        
        # Verify config file was updated
        mock_dump.assert_called_once()
        args, kwargs = mock_dump.call_args
        updated_config = args[0]
        assert 'total_paths' in updated_config
        assert updated_config['total_paths'] == total_paths

    def test_calculate_total_paths_no_valid_paths(self):
        """Test _calculate_total_paths raises error when no valid paths exist."""
        pf = PathFinder(
            grid_size=3,
            path_min_len=20,  # Impossible length for 3x3 grid
            path_max_len=25,
            path_prefix=[],
            path_suffix=[],
            excluded_nodes=[]
        )
        
        with pytest.raises(ValueError, match="No paths found with the given configuration"):
            pf._calculate_total_paths()

    def test_dfs_with_successful_path(self):
        """Test DFS search finds successful path."""
        pf = PathFinder(
            grid_size=3,
            path_min_len=4,
            path_max_len=5,
            path_prefix=[],
            path_suffix=[],
            excluded_nodes=[]
        )
        
        # Mock handler that succeeds on specific path
        def mock_handler_success(path, total_paths=None):
            if len(path) == 4 and path[0] == 1:
                return (True, path)
            return (False, None)
        
        handler = MockHandler()
        handler.handle_path = mock_handler_success
        pf.add_handler(handler)
        
        success, path = pf.dfs()
        assert success is True
        assert len(path) >= 4

    def test_dfs_no_successful_path(self):
        """Test DFS search when no path succeeds."""
        pf = PathFinder(
            grid_size=3,
            path_min_len=4,
            path_max_len=5,
            path_prefix=[],
            path_suffix=[],
            excluded_nodes=[]
        )
        
        # Handler that always fails
        fail_handler = MockHandler(return_value=(False, None))
        pf.add_handler(fail_handler)
        
        success, path = pf.dfs()
        assert success is False
        assert path == []

    def test_dfs_with_path_prefix(self):
        """Test DFS search respects path prefix."""
        pf = PathFinder(
            grid_size=3,
            path_min_len=4,
            path_max_len=6,
            path_prefix=[1, 2],
            path_suffix=[],
            excluded_nodes=[]
        )
        
        handler = MockHandler()
        pf.add_handler(handler)
        
        # Run DFS (will fail but we check the paths attempted)
        pf.dfs()
        
        # All attempted paths should start with [1, 2]
        for attempted_path in handler.called_paths:
            if len(attempted_path) >= 2:
                assert attempted_path[0] == 1
                assert attempted_path[1] == 2

    def test_dfs_with_excluded_nodes(self):
        """Test DFS search respects excluded nodes."""
        pf = PathFinder(
            grid_size=3,
            path_min_len=4,
            path_max_len=6,
            path_prefix=[],
            path_suffix=[],
            excluded_nodes=[5]  # Exclude center node
        )
        
        handler = MockHandler()
        pf.add_handler(handler)
        
        # Run DFS
        pf.dfs()
        
        # No attempted path should contain node 5
        for attempted_path in handler.called_paths:
            assert 5 not in attempted_path

    def test_neighbors_accessibility(self):
        """Test that neighbor relationships are properly defined."""
        pf = PathFinder(grid_size=3, path_min_len=4, path_max_len=9)
        
        # Test some known neighbor relationships for 3x3 grid
        # Note: neighbors are stored as integers, not strings
        assert 2 in pf._neighbors['1']  # 1 connects to 2
        assert 4 in pf._neighbors['1']  # 1 connects to 4
        assert 5 in pf._neighbors['1']  # 1 connects to 5 (diagonal)
        
        # Center node (5) should connect to all others
        assert len(pf._neighbors['5']) == 8

    def test_path_length_constraints_in_dfs(self):
        """Test that DFS respects min and max path length constraints."""
        pf = PathFinder(
            grid_size=3,
            path_min_len=5,
            path_max_len=6,
            path_prefix=[],
            path_suffix=[],
            excluded_nodes=[]
        )
        
        handler = MockHandler()
        pf.add_handler(handler)
        
        pf.dfs()
        
        # All attempted paths should be between min and max length
        for attempted_path in handler.called_paths:
            assert 5 <= len(attempted_path) <= 6


class TestPathFinderIntegration:
    """Integration tests for PathFinder with realistic scenarios."""
    
    def test_complete_search_small_grid(self):
        """Test complete search on small constrained grid."""
        pf = PathFinder(
            grid_size=3,
            path_min_len=4,
            path_max_len=4,  # Only 4-node paths
            path_prefix=[1],  # Must start with 1
            path_suffix=[9],  # Must end with 9
            excluded_nodes=[5]  # Exclude center
        )
        
        handler = MockHandler()
        pf.add_handler(handler)
        
        pf.dfs()
        
        # Verify all paths meet constraints
        for path in handler.called_paths:
            assert len(path) == 4
            assert path[0] == 1
            assert path[-1] == 9
            assert 5 not in path

    @patch('PathFinder.yaml')
    @patch('builtins.open', mock_open())
    def test_total_paths_calculation_accuracy(self, mock_yaml):
        """Test that total paths calculation is accurate."""
        mock_yaml.safe_load.return_value = {'total_paths': 0}
        
        pf = PathFinder(
            grid_size=3,
            path_min_len=4,
            path_max_len=4,
            path_prefix=[1],
            path_suffix=[9],
            excluded_nodes=[]
        )
        
        calculated_total = pf._calculate_total_paths()
        
        # Now count actual paths by running DFS
        handler = MockHandler()
        pf.add_handler(handler)
        pf.dfs()
        
        actual_paths = len(handler.called_paths)
        assert calculated_total == actual_paths
