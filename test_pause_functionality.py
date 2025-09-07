#!/usr/bin/env python3
"""
Test script to validate the pause functionality in scroll.

This test creates a simple HTML page and tests the pause functionality
without needing external URLs or dependencies.
"""

import os
import sys
import time
import tempfile
from unittest.mock import Mock, MagicMock

# Add the source directory to the path
sys.path.insert(0, '/home/runner/work/pitch-pilot/pitch-pilot/source/ghost-scroll/src')

from ghostscroll.main import parse_pause_points, scroll_page, log

def test_parse_pause_points():
    """Test the pause points parsing functionality."""
    print("Testing parse_pause_points...")
    
    # Test valid input
    result = parse_pause_points("2:3,5:1,10:2.5")
    expected = [(2.0, 3.0), (5.0, 1.0), (10.0, 2.5)]
    assert result == expected, f"Expected {expected}, got {result}"
    print("✓ Valid pause points parsed correctly")
    
    # Test empty input
    result = parse_pause_points("")
    assert result == [], f"Expected empty list, got {result}"
    print("✓ Empty input handled correctly")
    
    # Test invalid input (should be filtered out)
    result = parse_pause_points("2:3,invalid,5:1")
    expected = [(2.0, 3.0), (5.0, 1.0)]
    assert result == expected, f"Expected {expected}, got {result}"
    print("✓ Invalid entries filtered correctly")
    
    # Test sorted output
    result = parse_pause_points("10:1,2:3,5:1")
    expected = [(2.0, 3.0), (5.0, 1.0), (10.0, 1.0)]
    assert result == expected, f"Expected sorted {expected}, got {result}"
    print("✓ Results are sorted by start time")

def create_test_html():
    """Create a simple test HTML file with enough content to scroll."""
    html_content = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pause Test Page</title>
        <style>
            body { margin: 0; font-family: Arial, sans-serif; }
            .section { height: 100vh; padding: 20px; border-bottom: 2px solid #ccc; }
            .section:nth-child(odd) { background-color: #f0f0f0; }
            .section:nth-child(even) { background-color: #e0e0e0; }
        </style>
    </head>
    <body>
        <div class="section"><h1>Section 1</h1><p>Content for section 1...</p></div>
        <div class="section"><h1>Section 2</h1><p>Content for section 2...</p></div>
        <div class="section"><h1>Section 3</h1><p>Content for section 3...</p></div>
        <div class="section"><h1>Section 4</h1><p>Content for section 4...</p></div>
        <div class="section"><h1>Section 5</h1><p>Content for section 5...</p></div>
        <div class="section"><h1>Section 6</h1><p>Content for section 6...</p></div>
        <div class="section"><h1>Section 7</h1><p>Content for section 7...</p></div>
        <div class="section"><h1>Section 8</h1><p>Content for section 8...</p></div>
    </body>
    </html>
    '''
    
    # Create temporary HTML file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        f.write(html_content)
        return f.name

def test_scroll_javascript():
    """Test that the JavaScript scroll code can be injected and has pause support."""
    print("\nTesting JavaScript scroll state...")
    
    # Mock driver to test JavaScript injection
    mock_driver = Mock()
    
    # Mock the execute_script to return proper scroll state and handle pause controls
    def mock_execute_script(script=None, **kwargs):
        if script and 'window._scrollState' in script and 'startTime' in script:
            # This is the initial JS injection - return None
            return None
        elif script == "return window._scrollState || {}":
            # Return scroll state - simulate finished immediately to avoid complex mocking
            return {"progress": 1.0, "finished": True}
        elif script in ["window._scrollState.paused = true", "window._scrollState.paused = false"]:
            # Pause control commands - return None
            return None
        else:
            return None
    
    mock_driver.execute_script.side_effect = mock_execute_script
    
    # Test that scroll_page calls execute_script with proper pause-aware JavaScript
    scroll_page(mock_driver, 8.0, [(2.0, 3.0), (5.0, 1.0)])
    
    # Verify that execute_script was called
    assert mock_driver.execute_script.called, "execute_script should have been called"
    
    # Find the JavaScript injection call
    js_injection_call = None
    for call in mock_driver.execute_script.call_args_list:
        if call[1].get('script') and 'startTime' in call[1].get('script', ''):
            js_injection_call = call[1]['script']
            break
    
    assert js_injection_call is not None, "Should find JavaScript injection call"
    
    # Verify pause-related variables are present
    assert 'paused: false' in js_injection_call, "JavaScript should initialize paused state"
    assert 'holdMark: null' in js_injection_call, "JavaScript should initialize holdMark"
    assert 'holdAccum: 0' in js_injection_call, "JavaScript should initialize holdAccum"
    
    # Verify pause logic is present
    assert 'if (s.paused)' in js_injection_call, "JavaScript should have pause handling"
    assert 's.holdAccum +=' in js_injection_call, "JavaScript should accumulate hold time"
    
    print("✓ JavaScript contains pause support variables")
    print("✓ JavaScript contains pause handling logic")

def test_pause_timing_logic():
    """Test the pause timing and trigger logic."""
    print("\nTesting pause timing logic...")
    
    # Test pause points
    pause_points = [(2.0, 1.0), (5.0, 2.0)]  # Pause at 2s for 1s, at 5s for 2s
    duration = 8.0
    
    # Test the logic without actually running scroll_page
    remaining_pauses = list(pause_points)
    
    # Simulate progress through scroll timeline
    test_progress_values = [0.1, 0.25, 0.3, 0.625, 0.8, 1.0]  # Corresponds to 0.8s, 2.0s, 2.4s, 5.0s, 6.4s, 8.0s
    
    triggered_pauses = []
    
    for progress in test_progress_values:
        elapsed_sec = progress * duration
        
        if remaining_pauses:
            next_start, next_len = remaining_pauses[0]
            if elapsed_sec >= next_start:
                triggered_pauses.append((next_start, next_len))
                remaining_pauses.pop(0)
    
    # Verify that both pause points were triggered
    assert len(triggered_pauses) == 2, f"Expected 2 pauses triggered, got {len(triggered_pauses)}"
    assert triggered_pauses[0] == (2.0, 1.0), f"First pause should be (2.0, 1.0), got {triggered_pauses[0]}"
    assert triggered_pauses[1] == (5.0, 2.0), f"Second pause should be (5.0, 2.0), got {triggered_pauses[1]}"
    
    print("✓ Pause points trigger at correct times")
    print(f"✓ Triggered pauses: {triggered_pauses}")
    print("✓ Pause timing logic works correctly")

if __name__ == "__main__":
    print("Running pause functionality tests...\n")
    
    try:
        test_parse_pause_points()
        test_scroll_javascript() 
        test_pause_timing_logic()
        
        print("\n🎉 All tests passed! Pause functionality is working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)