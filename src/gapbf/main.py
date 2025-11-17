import argparse
import sys
import logging
import time
from datetime import datetime
from tqdm import tqdm
from .Config import Config
from .PathFinder import PathFinder
from .PathHandler import ADBHandler, PrintHandler, TestHandler, LogHandler
from .Logging import setup_logging

# Define handler_classes at module level so it's available to validate_mode
handler_classes = {
    'a': {'class': ADBHandler, 'help': 'Attempt decryption via ADB shell on Android device (includes logging)'},
    'p': {'class': PrintHandler, 'help': 'Print attempted path to console'},
    't': {'class': TestHandler, 'help': 'Run mock brute force against test_path in config'},
}


def validate_mode(value):
    valid_modes = ''.join(handler_classes.keys())
    if not set(value).issubset(set(valid_modes)):
        available_options = ', '.join(valid_modes)
        raise argparse.ArgumentTypeError(
            f"Invalid mode: {value}. Allowed values are combinations of {available_options}.")
    return value


def _generate_sample_paths(path_finder, limit=10):
    """Generate a limited number of sample paths for dry-run mode.
    
    Args:
        path_finder: PathFinder instance
        limit: Maximum number of paths to generate
        
    Yields:
        Path lists
    """
    count = 0
    
    def dfs_sample(node, path, visited):
        nonlocal count
        if count >= limit:
            return
            
        path.append(node)
        visited.add(node)
        
        try:
            if len(path) >= path_finder._path_min_len:
                suffix_match = True
                if path_finder._path_suffix:
                    if len(path) >= len(path_finder._path_suffix):
                        path_suffix = path[-len(path_finder._path_suffix):]
                        suffix_match = path_suffix == list(path_finder._path_suffix)
                    else:
                        suffix_match = False
                
                if suffix_match:
                    yield list(path)
                    count += 1
                    if count >= limit:
                        return

            if len(path) < path_finder._path_max_len and count < limit:
                for neighbor in path_finder._neighbors[str(node)]:
                    if neighbor not in path_finder._excluded_nodes and neighbor not in visited:
                        yield from dfs_sample(neighbor, path, visited)
                        if count >= limit:
                            return
        finally:
            path.pop()
            visited.discard(node)
    
    # Start generation
    if path_finder._path_prefix:
        path = []
        visited = set()
        for node in path_finder._path_prefix[:-1]:
            path.append(node)
            visited.add(node)
        yield from dfs_sample(path_finder._path_prefix[-1], path, visited)
    else:
        for node in path_finder._graph:
            if node not in path_finder._excluded_nodes:
                yield from dfs_sample(node, [], set())
                if count >= limit:
                    break


def main():
    parser = argparse.ArgumentParser(
        description='Graph-based Android Pattern Brute Force - TWRP recovery pattern cracker')

    parser.add_argument('-m', '--mode', type=validate_mode, required=True,
                       help=f"Select handler modes: {', '.join([f'{k}={v['help']}' for k,v in handler_classes.items()])}")
    parser.add_argument('-c', '--config', default='config.yaml',
                       help='Path to configuration file (default: config.yaml)')
    parser.add_argument('-l', '--logging', choices=['error', 'warning', 'debug', 'info'], default='error',
                       help='Set logging level (default: error)')
    parser.add_argument('--log-file', help='Enable logging to specified file')
    parser.add_argument('--dry-run', action='store_true',
                       help='Test mode: show paths without executing (implies test handler)')

    try:
        args = parser.parse_args()
    except SystemExit:
        sys.exit(1)

    # Set up logging
    setup_logging(args.logging, args.log_file)
    logger = logging.getLogger('gapbf')
    
    # Load configuration
    try:
        config = Config.load_config(args.config)
        logger.info(f"Loaded configuration from {args.config}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)
    
    # Initialize PathFinder
    try:
        path_finder = PathFinder(
            config.grid_size,
            config.path_min_length,
            config.path_max_length,
            config.path_max_node_distance,
            config.path_prefix,
            config.path_suffix,
            config.excluded_nodes
        )
        logger.info(f"Initialized PathFinder with {path_finder.total_paths} total possible paths")
    except Exception as e:
        logger.error(f"Failed to initialize PathFinder: {e}")
        sys.exit(1)

    # Handle dry-run mode
    if args.dry_run:
        print(f"\n{'='*60}")
        print("DRY RUN MODE - No actual execution")
        print(f"{'='*60}\n")
        print(f"Configuration would generate {path_finder.total_paths:,} paths")
        print(f"Grid: {config.grid_size}x{config.grid_size}")
        print(f"Length: {config.path_min_length} to {config.path_max_length}")
        print(f"Prefix: {config.path_prefix if config.path_prefix else 'None'}")
        print(f"Suffix: {config.path_suffix if config.path_suffix else 'None'}")
        print(f"Excluded: {list(config.excluded_nodes) if config.excluded_nodes else 'None'}")
        print(f"\nFirst 10 paths that would be attempted:")
        count = 0
        for path in _generate_sample_paths(path_finder, 10):
            count += 1
            print(f"  {count}. {path}")
        print(f"\nDry run complete. Use without --dry-run to execute.")
        return

    # Initialize handlers based on selected modes
    for mode in args.mode:
        if mode in handler_classes:
            handler_class = handler_classes[mode]['class']
            try:
                # PrintHandler needs grid nodes from PathFinder
                if handler_class == PrintHandler:
                    handler = handler_class(config, path_finder.grid_nodes)
                else:
                    handler = handler_class(config)
                path_finder.add_handler(handler)
                logger.info(f"Added handler: {handler_class.__name__}")
            except Exception as e:
                logger.error(f"Failed to initialize {handler_class.__name__}: {e}")
                sys.exit(1)
        else:
            logger.warning(f"Mode '{mode}' is not recognized and will be ignored")

    # Display configuration summary
    print(f"\n{'='*60}")
    print(f"GAPBF - Graph-based Android Pattern Brute Force")
    print(f"{'='*60}")
    print(f"Grid Size: {config.grid_size}x{config.grid_size}")
    print(f"Path Length: {config.path_min_length} to {config.path_max_length}")
    print(f"Path Prefix: {config.path_prefix if config.path_prefix else 'None'}")
    print(f"Path Suffix: {config.path_suffix if config.path_suffix else 'None'}")
    print(f"Excluded Nodes: {config.excluded_nodes if config.excluded_nodes else 'None'}")
    print(f"Total Possible Paths: {path_finder.total_paths:,}")
    handler_names = ', '.join([handler_classes[m]['class'].__name__ for m in args.mode if m in handler_classes])
    print(f"Active Handlers: {handler_names}")
    
    # Check for resume capability
    attempted_count = 0
    if hasattr(path_finder.handlers[0], 'attempted_paths'):
        attempted_count = len(path_finder.handlers[0].attempted_paths)
        if attempted_count > 0:
            print(f"Resuming: {attempted_count:,} paths already attempted")
    
    print(f"{'='*60}\n")
    
    # Execute brute force with progress bar
    logger.info("Starting brute force search")
    start_time = time.time()
    
    try:
        # Create progress bar
        with tqdm(
            total=path_finder.total_paths,
            desc="Searching paths",
            unit="path",
            initial=attempted_count,
            bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]',
            ncols=100
        ) as pbar:
            
            success = False
            successful_path = None
            
            # Use the DFS method but update progress bar
            def dfs_with_progress():
                nonlocal success, successful_path
                
                # Wrapper to track progress
                original_process = path_finder.process_path
                
                def process_with_progress(path):
                    result_success, result_path = original_process(path)
                    pbar.update(1)
                    pbar.set_postfix_str(f"Current: {path}")
                    return result_success, result_path
                
                path_finder.process_path = process_with_progress
                success, successful_path = path_finder.dfs()
                path_finder.process_path = original_process
                
                return success, successful_path
            
            success, successful_path = dfs_with_progress()
        
        elapsed_time = time.time() - start_time
        hours, remainder = divmod(int(elapsed_time), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if success:
            print(f"\n{'='*60}")
            print(f"SUCCESS! Pattern found: {successful_path}")
            print(f"Time elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}")
            print(f"{'='*60}\n")
            logger.info(f"Successfully found pattern: {successful_path} in {elapsed_time:.2f}s")
        else:
            print(f"\n{'='*60}")
            print(f"Search completed. No successful pattern found.")
            print(f"Time elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}")
            print(f"Check {config.paths_log_file_path} for details.")
            print(f"{'='*60}\n")
            logger.info(f"Search completed without finding successful pattern after {elapsed_time:.2f}s")
            
    except KeyboardInterrupt:
        elapsed_time = time.time() - start_time
        print(f"\n\n{'='*60}")
        print(f"Search interrupted by user")
        hours, remainder = divmod(int(elapsed_time), 3600)
        minutes, seconds = divmod(remainder, 60)
        print(f"Time elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}")
        print(f"{'='*60}\n")
        logger.info("Search interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error during search: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
