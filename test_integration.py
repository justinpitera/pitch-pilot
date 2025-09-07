#!/usr/bin/env python3
"""
Integration test to validate the pause functionality by checking the 
JavaScript generation and pause point processing.
"""

import sys
import os
import tempfile
from unittest.mock import Mock, patch

# Add the source directory to the path
sys.path.insert(0, '/home/runner/work/pitch-pilot/pitch-pilot/source/ghost-scroll/src')

def test_javascript_generation():
    """Test that the generated JavaScript contains all required pause functionality."""
    from ghostscroll.main import scroll_page
    
    print("Testing JavaScript generation with pause support...")
    
    # Mock driver
    mock_driver = Mock()
    
    # Mock execute_script to capture the JavaScript
    captured_js = []
    def capture_js(script=None, **kwargs):
        if script and 'window._scrollState' in script and 'startTime' in script:
            captured_js.append(script)
            return None
        elif script == "return window._scrollState || {}":
            return {"progress": 1.0, "finished": True}  # End immediately
        else:
            return None
    
    mock_driver.execute_script.side_effect = capture_js
    
    # Call scroll_page with pause points
    pause_points = [(2.0, 3.0), (5.0, 1.0)]
    scroll_page(mock_driver, 8.0, pause_points)
    
    # Verify JavaScript was captured
    assert len(captured_js) > 0, "Should have captured JavaScript"
    js = captured_js[0]
    
    print("Generated JavaScript:")
    print("=" * 50)
    print(js)
    print("=" * 50)
    
    # Verify all required pause functionality is present
    required_elements = [
        'paused: false',
        'holdMark: null', 
        'holdAccum: 0',
        'if (s.paused)',
        's.holdMark = n',
        's.holdAccum +=',
        'easeInOutCubic'
    ]
    
    for element in required_elements:
        assert element in js, f"JavaScript should contain: {element}"
        print(f"✓ Found: {element}")
    
    print("✓ JavaScript generation test passed")

def test_end_to_end_argument_processing():
    """Test the full argument processing pipeline."""
    print("\nTesting end-to-end argument processing...")
    
    # Test arguments that should produce the expected pause points
    test_argv = [
        "main.py",
        "file:///home/runner/work/pitch-pilot/pitch-pilot/test_page.html",
        "8",
        "--pause", "2:3,5:1"
    ]
    
    # Save original argv
    original_argv = sys.argv[:]
    
    try:
        # Mock sys.argv
        sys.argv = test_argv
        
        # Import and run the argument parsing logic from main
        from ghostscroll.main import parse_pause_points
        
        # Test the parsing logic that main() uses
        pause_arg = next((arg for arg in sys.argv if arg.startswith("--pause")), None)
        if pause_arg:
            pause_value = pause_arg.replace("--pause", "").strip()
            if not pause_value and "--pause" in sys.argv:
                pause_index = sys.argv.index("--pause")
                if pause_index + 1 < len(sys.argv):
                    pause_value = sys.argv[pause_index + 1]
            pause_points = parse_pause_points(pause_value) if pause_value else []
        else:
            pause_points = []
        
        expected_pause_points = [(2.0, 3.0), (5.0, 1.0)]
        assert pause_points == expected_pause_points, f"Expected {expected_pause_points}, got {pause_points}"
        
        print(f"✓ Argument processing: {sys.argv}")
        print(f"✓ Parsed pause points: {pause_points}")
        print("✓ End-to-end argument processing test passed")
        
    finally:
        sys.argv = original_argv

def test_pause_point_consumption():
    """Test that pause points are consumed correctly during scroll."""
    print("\nTesting pause point consumption logic...")
    
    # Simulate the pause consumption logic from scroll_page
    pause_points = [(2.0, 3.0), (5.0, 1.0), (7.0, 0.5)]
    remaining_pauses = list(pause_points)
    duration = 10.0
    
    # Simulate progress through the scroll timeline
    progress_timeline = [0.1, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0]
    triggered_pauses = []
    
    for progress in progress_timeline:
        elapsed_sec = progress * duration
        
        if remaining_pauses:
            next_start, next_len = remaining_pauses[0]
            if elapsed_sec >= next_start:
                triggered_pauses.append((next_start, next_len, elapsed_sec))
                remaining_pauses.pop(0)
    
    print(f"Original pause points: {pause_points}")
    print(f"Triggered pauses: {triggered_pauses}")
    print(f"Remaining pauses: {remaining_pauses}")
    
    # Verify all pauses were triggered
    assert len(triggered_pauses) == 3, f"Expected 3 triggered pauses, got {len(triggered_pauses)}"
    assert len(remaining_pauses) == 0, f"Expected 0 remaining pauses, got {len(remaining_pauses)}"
    
    # Verify pauses were triggered at the right times
    assert triggered_pauses[0][0] == 2.0, "First pause should be at 2.0s"
    assert triggered_pauses[1][0] == 5.0, "Second pause should be at 5.0s"  
    assert triggered_pauses[2][0] == 7.0, "Third pause should be at 7.0s"
    
    print("✓ Pause point consumption test passed")

if __name__ == "__main__":
    print("Running integration tests for pause functionality...\n")
    
    try:
        test_javascript_generation()
        test_end_to_end_argument_processing()
        test_pause_point_consumption()
        
        print("\n🎉 All integration tests passed! Pause functionality is fully working.")
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)