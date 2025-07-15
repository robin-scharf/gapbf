#!/usr/bin/env python3

# Quick test script to verify path skipping works

from PathHandler import ADBHandler

def test_path_skipping():
    print("Creating ADB handler...")
    handler = ADBHandler()
    print(f"Loaded {len(handler.attempted_paths)} attempted paths")
    
    # Test with a path that should be in the attempted paths (from CSV)
    test_path = [1, 2, 3, 5]
    print(f"\nTesting path: {test_path}")
    print(f"Path string format: {str(test_path)}")
    print(f"Is in attempted paths: {str(test_path) in handler.attempted_paths}")
    
    print("\nCalling handle_path...")
    result, data = handler.handle_path(test_path, total_paths=100)
    print(f"Result: {result}, Data: {data}")

if __name__ == "__main__":
    test_path_skipping()
