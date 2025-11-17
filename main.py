import argparse
import sys
from Config import Config
from PathFinder import PathFinder
from PathHandler import ADBHandler, PrintHandler, TestHandler, LogHandler
from Logging import get_logger, add_file_handler

# Define handler_classes at module level so it's available to validate_mode
handler_classes = {
    'a': {'class': ADBHandler, 'help': 'Attempt decryption via ADB shell on Android device (includes logging)'},
    'p': {'class': PrintHandler, 'help': 'Print attempted path to console'},
    't': {'class': TestHandler, 'help': 'Run mock brute force against test_path in config'},
}

config = Config.load_config('config.yaml')
path_finder = PathFinder(config.grid_size, config.path_min_length, config.path_max_length,
                         config.path_max_node_distance, config.path_prefix, config.path_suffix, config.excluded_nodes)


def validate_mode(value):
    valid_modes = ''.join(handler_classes.keys())
    if not set(value).issubset(set(valid_modes)):
        available_options = ', '.join(valid_modes)
        raise argparse.ArgumentTypeError(
            f"Invalid mode: {value}. Allowed values are combinations of {available_options}.")
    return value


def main():
    parser = argparse.ArgumentParser(
        description='Please configure applicable handlers. Example: python3 main.py -m ap -l w')

    mode_help = "Select modes: "
    for arg, handler_info in handler_classes.items():
        mode_help += f"{arg} ({handler_info['help']}), "
    
    mode_help = mode_help.rstrip(", ")

    parser.add_argument('-m', '--mode', type=validate_mode, required=True, help=mode_help)
    parser.add_argument('-l', '--logging', choices=['error', 'warning', 'debug', 'info'], default='error', help='Set logging level: e for error, w for warnings, d for debug, i for info. Critical errors will always be shown. Default is \'error\'')
    parser.add_argument('--file', action='store_true', default=False, help='Enable logging to file')

    try:
        args = parser.parse_args()
    except SystemExit:
        valid_modes = ', '.join(handler_classes.keys())
        sys.exit(1)

    # Set up logging based on arguments
    logger = get_logger('main', args.logging)
    
    # Set up file logging if requested
    if args.file:
        add_file_handler(logger, config.process_log_file_path)
        logger.info(f"File logging enabled to: {config.process_log_file_path}")

    logger.info(f"Starting GAPBF with modes: {args.mode}, logging level: {args.logging}")

    modes = args.mode

    for mode in modes:
        if mode in handler_classes:
            handler_info = handler_classes[mode]
            handler_class = handler_info['class']
            handler = handler_class()
            
            # Set up file logging for handlers if requested
            if args.file and hasattr(handler, 'logger'):
                add_file_handler(handler.logger, config.process_log_file_path)
                
            path_finder.add_handler(handler)
        else:
            print(
                f"Warning: Mode '{mode}' is not recognized and will be ignored.")

    print(f"Starting main.py with config: {config}")
    print(f"Calculating possible paths...")
    handler_names_str = ', '.join([handler_info['class'].__name__ for arg, handler_info in handler_classes.items() if arg in args.mode])
    print(
        f"Completed calculations. Attempting brute force with {path_finder.total_paths} possible paths via {handler_names_str}.")
    success, successful_path = path_finder.dfs()
    if not success:
        print(f"Reached end of paths to try. Check path_logs.csv for more information. Exiting.")
    else:
        print(f"Success! The path is: {successful_path}")


if __name__ == "__main__":
    main()
