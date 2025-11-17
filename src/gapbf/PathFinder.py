"""Path generation and traversal for Android pattern brute forcing.

This module provides the PathFinder class which generates all valid paths
through an Android pattern lock grid using depth-first search.
"""
from typing import List, Union, Set, Tuple, Optional
from .PathHandler import PathHandler
import logging


class PathFinder:
    """Generates and processes paths through Android pattern lock grids.
    
    Supports 3x3, 4x4, 5x5, and 6x6 grids. Uses DFS with backtracking
    to efficiently explore the search space.
    """
    
    # Grid definitions for different sizes
    # Node mappings from TWRP: https://twrp.me/faq/openrecoveryscript.html
    _graphs: dict = {
            3: {
                "graph": [1,2,3,4,5,6,7,8,9], 
                "neighbors": {
                "1": [2, 4, 5],
                "2": [1, 3, 4, 5, 6], 
                "3": [2, 5, 6],
                "4": [1, 2, 5, 7, 8],
                "5": [1, 2, 3, 4, 6, 7, 8, 9],
                "6": [2, 3, 5, 8, 9],
                "7": [4, 5, 8],
                "8": [4, 5, 6, 7, 9],
                "9": [5, 6, 8]
                }
            },
            4: {
                "graph": [1,2,3,4,5,6,7,8,9,":",";","<","=",">","?","@"],
                "neighbors": {
                "1": [2, 5, 6], 
                "2": [1, 3, 5, 6, 7],
                "3": [2, 4, 6, 7, 8],
                "4": [3, 7, 8],
                "5": [1, 2, 6, 9, ":"],
                "6": [1, 2, 3, 5, 7, 9, ":", ";"],
                "7": [2, 3, 4, 6, 8, ":", ";", "<"],
                "8": [3, 4, 7, ";", "<"],
                "9": [5, 6, ":", "=", ">"],
                ":": [5, 6, 7, 9, ";", "=", ">", "?"],
                ";": [6, 7, 8, ":", "<", ">", "?", "@"],
                "<": [7, 8, ";", "?", "@"],
                "=": [9, ":", ">"],
                ">": [9, ":", ";", "=", "?"],
                "?": [":", ";", "<", ">", "@"],
                "@": [";", "<", "?"]
                }
            },
            5: {
                "graph": [1,2,3,4,5,6,7,8,9,":",";","<","=",">","?","@","A","B","C","D","E","F","G","H","I"],
                "neighbors": {
                    "1": [2, 6, 7], 
                    "2": [1, 3, 6, 7, 8],
                    "3": [2, 4, 7, 8, 9],
                    "4": [3, 5, 8, 9, ":"],
                    "5": [4, 9, ":"],
                    "6": [1, 2, 7, ";", "<"],
                    "7": [1, 2, 3, 6, 8, ";", "<", "="],
                    "8": [2, 3, 4, 7, 9, "<", "=", ">"],
                    "9": [3, 4, 5, 8, ":", "=", ">", "?"],
                    ":": [4, 5, 9, ">", "?"],
                    ";": [6, 7, "<", "@", "A"],
                    "<": [6, 7, 8, ";", "=", "@", "A", "B"],
                    "=": [7, 8, 9, "<", ">", "A", "B", "C"],
                    ">": [8, 9, ":", "=", "?", "B", "C", "D"],
                    "?": [9, ":", ">", "C", "D"],
                    "@": [";", "<", "A", "E", "F"],
                    "A": [";", "<", "=", "@", "B", "E", "F", "G"],
                    "B": ["<", "=", ">", "A", "C", "F", "G", "H"],
                    "C": ["=", ">", "?", "B", "D", "G", "H", "I"],
                    "D": [">", "?", "C", "H", "I"],
                    "E": ["@", "A", "F"],
                    "F": ["@", "A", "B", "E", "G"],
                    "G": ["A", "B", "C", "F", "H"],
                    "H": ["B", "C", "D", "G", "I"],
                    "I": ["C", "D", "H"]
                }
            },
            6: {
                "graph": [1, 2, 3, 4, 5, 6, 7, 8, 9, ":", ";", "<", "=", ">", "?", "@", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T"],
                "neighbors": {
                    "1": [2, 7, 8],
                    "2": [1, 3, 7, 8, 9],
                    "3": [2, 4, 8, 9, ":"],
                    "4": [3, 5, 9, ":", ";"],
                    "5": [4, 6, ":", ";", "<"],
                    "6": [5, ";", "<"],
                    "7": [1, 2, 8, "=", ">"],
                    "8": [1, 2, 3, 7, 9, "=", ">", "?"],
                    "9": [2, 3, 4, 8, ":", ">", "?", "@"],
                    ":": [3, 4, 5, 9, ";", "?", "@", "A"],
                    ";": [4, 5, 6, ":", "<", "@", "A", "B"],
                    "<": [5, 6, ";", "A", "B"],
                    "=": [7, 8, ">", "C", "D"],
                    ">": [7, 8, 9, "=", "?", "C", "D", "E"],
                    "?": [8, 9, ":", ">", "@", "D", "E", "F"],
                    "@": [9, ":", ";", "?", "A", "E", "F", "G"],
                    "A": [":", ";", "<", "@", "B", "F", "G", "H"],
                    "B": [";", "<", "A", "G", "H"],
                    "C": ["=", ">", "D", "I", "J"],
                    "D": ["=", ">", "?", "C", "E", "I", "J", "K"],
                    "E": [">", "?", "@", "D", "F", "J", "K", "L"],
                    "F": ["?", "@", "A", "E", "G", "K", "L", "M"],
                    "G": ["@", "A", "B", "F", "H", "L", "M", "N"],
                    "H": ["A", "B", "G", "M", "N"],
                    "I": ["C", "D", "J", "O", "P"],
                    "J": ["C", "D", "E", "I", "K", "O", "P", "Q"],
                    "K": ["D", "E", "F", "J", "L", "P", "Q", "R"],
                    "L": ["E", "F", "G", "K", "M", "Q", "R", "S"],
                    "M": ["F", "G", "H", "L", "N", "R", "S", "T"],
                    "N": ["G", "H", "M", "S", "T"],
                    "O": ["I", "J", "P"],
                    "P": ["I", "J", "K", "O", "Q"],
                    "Q": ["J", "K", "L", "P", "R"],
                    "R": ["K", "L", "M", "Q", "S"],
                    "S": ["L", "M", "N", "R", "T"],
                    "T": ["M", "N", "S"]
                }
            },
        }

    def __init__(self, grid_size: int, path_min_len: int = 4, path_max_len: int = 36, 
                 path_max_node_distance: int = 1, path_prefix: List[Union[int, str]] = None, 
                 path_suffix: List[Union[int, str]] = None, excluded_nodes: List[Union[int, str]] = None):
        """Initialize PathFinder with grid configuration and constraints.
        
        All nodes are standardized to strings internally for consistency.
        
        Args:
            grid_size: Size of the grid (3, 4, 5, or 6)
            path_min_len: Minimum path length (default 4, Android minimum)
            path_max_len: Maximum path length
            path_max_node_distance: Maximum distance between consecutive nodes (unused currently)
            path_prefix: Required starting nodes for all paths
            path_suffix: Required ending nodes for all paths
            excluded_nodes: Nodes that cannot be used in any path
            
        Raises:
            ValueError: If grid_size is not supported
        """
        if grid_size not in self._graphs:
            raise ValueError(
                f'Unsupported grid size: {grid_size}. Supported sizes: {list(self._graphs.keys())}')
                
        self._grid_size = grid_size
        graph_data = self._graphs[grid_size]
        
        # Standardize all nodes to strings
        self._graph = [str(node) for node in graph_data["graph"]]
        self._neighbors = {str(k): [str(v) for v in vals] for k, vals in graph_data["neighbors"].items()}
        
        self._handlers: List[PathHandler] = []
        self._total_paths: Optional[int] = None
        self._path_min_len = path_min_len
        self._path_max_len = path_max_len
        self._path_max_node_distance = path_max_node_distance
        
        # Convert all input lists to strings for consistency
        self._path_prefix = [str(node) for node in path_prefix] if path_prefix else []
        self._path_suffix = [str(node) for node in path_suffix] if path_suffix else []
        self._excluded_nodes = {str(node) for node in excluded_nodes} if excluded_nodes else set()
        
        self.logger = logging.getLogger(__name__)

    @property
    def handlers(self) -> List[PathHandler]:
        """Get list of registered handlers."""
        return self._handlers
    
    @property
    def total_paths(self) -> int:
        """Get total number of valid paths (calculated on first access)."""
        if self._total_paths is None:
            self._total_paths = self._calculate_total_paths()
        return self._total_paths
    
    @property
    def grid_nodes(self) -> List[Union[int, str]]:
        """Get the list of nodes in the grid."""
        return self._graph
    
    def __iter__(self):
        """Make PathFinder iterable, yielding paths one at a time.
        
        Yields:
            List[Union[int, str]]: Valid paths that meet all constraints
            
        Example:
            for path in path_finder:
                success = handler.handle_path(path)
                if success:
                    break
        """
        def generate_paths(node: Union[int, str], path: List[Union[int, str]], visited: Set):
            """Recursive generator for paths with backtracking."""
            path.append(node)
            visited.add(node)
            
            try:
                # Yield path if it meets requirements
                if len(path) >= self._path_min_len:
                    suffix_match = True
                    if self._path_suffix:
                        if len(path) >= len(self._path_suffix):
                            path_suffix = path[-len(self._path_suffix):]
                            suffix_match = path_suffix == list(self._path_suffix)
                        else:
                            suffix_match = False
                    
                    if suffix_match:
                        yield list(path)  # Yield a copy of the current path

                # Continue DFS if we haven't reached max length
                if len(path) < self._path_max_len:
                    for neighbor in self._neighbors[str(node)]:
                        if neighbor not in self._excluded_nodes and neighbor not in visited:
                            yield from generate_paths(neighbor, path, visited)
            
            finally:
                path.pop()
                visited.discard(node)

        # Initialize and start generation
        path = []
        visited = set()
        
        if self._path_prefix:
            # Build initial path from prefix
            for node in self._path_prefix[:-1]:
                path.append(node)
                visited.add(node)
            
            # Generate from last node in prefix
            yield from generate_paths(self._path_prefix[-1], path, visited)
        else:
            # Generate starting from each node
            for node in self._graph:
                if node not in self._excluded_nodes:
                    yield from generate_paths(node, path, visited)
    
    def add_handler(self, handler: PathHandler) -> None:
        """Register a path handler.
        
        Args:
            handler: Handler to process paths
            
        Raises:
            TypeError: If handler is not a PathHandler instance
        """
        if not isinstance(handler, PathHandler):
            raise TypeError(f"Expected PathHandler, got {type(handler).__name__}")
        self._handlers.append(handler)
        self.logger.debug(f"Added handler: {handler.__class__.__name__}")
        
    def process_path(self, path: List[Union[int, str]]) -> Tuple[bool, Optional[List]]:
        """Process a path through all registered handlers.
        
        Args:
            path: The path to process
            
        Returns:
            Tuple of (success, path) where success is True if any handler succeeded
        """
        for handler in self._handlers:
            success, result_path = handler.handle_path(path, self.total_paths)
            if success:
                return True, result_path
        return False, None
    
    def _calculate_total_paths(self) -> int:
        visited = set(self._path_prefix)
        if self._path_suffix:
            path_suffix = set(self._path_suffix)  # Keep original types
        else:
            path_suffix = set()

        total_paths = 0

        def dfs_counter(node: Union[int, str], path: List[Union[int, str]]) -> None:
            nonlocal total_paths
            path = list(path)
            path.append(node)
            visited.add(node)

            if len(path) >= self._path_min_len:
                if path[-1] in path_suffix or not path_suffix:
                    total_paths += 1

            if len(path) < self._path_max_len:
                for neighbor in self._neighbors[str(node)]:
                    if neighbor not in self._excluded_nodes and neighbor not in visited:
                        dfs_counter(neighbor, path)

            path.pop()
            visited.remove(node)

        if not self._path_prefix:
            for node in self._graph:
                dfs_counter(node, [])
        else:
            dfs_counter(self._path_prefix[-1], self._path_prefix[:-1])

        if total_paths == 0:
            raise ValueError(
                "No paths found with given configuration. Check constraints.")
        
        self.logger.info(f"Calculated {total_paths} total possible paths")
        return total_paths

    def dfs(self) -> Tuple[bool, List]:
        """Perform depth-first search to find a successful path.
        
        Uses proper backtracking to avoid unnecessary list copying.
        
        Returns:
            Tuple of (success, path) where success is True if pattern found
        """
        def dfs_helper(node: Union[int, str], path: List[Union[int, str]], visited: Set) -> Tuple[bool, Optional[List]]:
            """Recursive DFS helper with backtracking.
            
            Args:
                node: Current node to visit
                path: Current path (modified in-place)
                visited: Set of visited nodes (modified in-place)
            
            Returns:
                Tuple of (success, path) if found, else (False, None)
            """
            # Add current node to path and visited
            path.append(node)
            visited.add(node)
            
            try:
                # Check if current path meets requirements
                if len(path) >= self._path_min_len:
                    # Check suffix constraint
                    suffix_match = True
                    if self._path_suffix:
                        if len(path) >= len(self._path_suffix):
                            path_suffix = path[-len(self._path_suffix):]
                            suffix_match = path_suffix == list(self._path_suffix)
                        else:
                            suffix_match = False
                    
                    if suffix_match:
                        # Process the path through handlers
                        success, result_path = self.process_path(list(path))
                        if success:
                            return (True, result_path)

                # Continue DFS if we haven't reached max length
                if len(path) < self._path_max_len:
                    for neighbor in self._neighbors[str(node)]:
                        # Skip excluded nodes and already visited nodes
                        if neighbor not in self._excluded_nodes and neighbor not in visited:
                            success, result_path = dfs_helper(neighbor, path, visited)
                            if success:
                                return (True, result_path)

                return (False, None)
            
            finally:
                # Backtrack: remove node from path and visited
                path.pop()
                visited.discard(node)

        # Initialize path and visited set
        path = []
        visited = set()
        
        # Start DFS from prefix if specified, otherwise try all nodes
        if self._path_prefix:
            # Build initial path from prefix
            for node in self._path_prefix[:-1]:
                path.append(node)
                visited.add(node)
            
            # Start DFS from last node in prefix
            last_node = self._path_prefix[-1]
            success, result_path = dfs_helper(last_node, path, visited)
            if success:
                return (True, result_path)
        else:
            # Try starting from each node
            for node in self._graph:
                if node not in self._excluded_nodes:
                    success, result_path = dfs_helper(node, path, visited)
                    if success:
                        return (True, result_path)

        return (False, [])
