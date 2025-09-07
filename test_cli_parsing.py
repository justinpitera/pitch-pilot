#!/usr/bin/env python3
"""
Test the CLI argument parsing for pause functionality.
"""

import sys
import os

# Add the source directory to the path
sys.path.insert(0, '/home/runner/work/pitch-pilot/pitch-pilot/source/ghost-scroll/src')

def test_cli_parsing(test_args, description):
    print(f"\nTesting: {description}")
    print(f"Args: {test_args}")
    
    # Save original argv
    original_argv = sys.argv[:]
    sys.argv = test_args
    
    try:
        from ghostscroll.main import parse_pause_points
        
        # Mimic the parsing logic from main()
        pause_arg = next((arg for arg in sys.argv if arg.startswith("--pause")), None)
        if pause_arg:
            pause_value = pause_arg.replace("--pause", "").strip()
            if not pause_value and "--pause" in sys.argv:
                # Handle '--pause 2:3,5:1' format (space separated)
                pause_index = sys.argv.index("--pause")
                if pause_index + 1 < len(sys.argv):
                    pause_value = sys.argv[pause_index + 1]
            pause_points = parse_pause_points(pause_value) if pause_value else []
        else:
            pause_points = []
            
        print(f"✓ Parsed pause points: {pause_points}")
        return pause_points
        
    except Exception as e:
        print(f"❌ CLI parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return None
        
    finally:
        # Restore original argv
        sys.argv = original_argv

# Test different CLI formats
test_cases = [
    (["main.py", "https://example.com", "8", "--pause2:3,5:1"], "Format: --pause2:3,5:1"),
    (["main.py", "https://example.com", "8", "--pause", "2:3,5:1"], "Format: --pause 2:3,5:1"),
    (["main.py", "https://example.com", "8"], "No pause argument"),
    (["main.py", "https://example.com", "8", "--pause"], "Empty pause argument"),
]

for test_args, description in test_cases:
    result = test_cli_parsing(test_args, description)
    
print("\n✓ All CLI parsing tests completed")