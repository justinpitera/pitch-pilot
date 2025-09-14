# GhostScroll

Auto-generate scroll-driven pitch videos from any URL — clean, smooth, and client-ready.

## Usage

```bash
python -m ghostscroll.main <url> [options]
```

### Options

- `--scroll-at <times>`: Comma-separated timestamps when scrolling should occur (e.g., "2,6,12")
- `--scroll-duration <durations>`: Comma-separated durations for each scroll event (e.g., "2,3,4")
- `--video-length <seconds>`: **Optional.** Target video duration in seconds. If not provided, video will be recorded at full duration without speed adjustment.
- `--avatar <path>`: Path to avatar image or video file (default: "avatar.jpg")
- `--cookies <mode>`: Cookie banner handling mode - "accept", "reject", or "hide" (default: "accept")

### Video Duration Behavior

**New Default Behavior (v0.1.0+):**
- Videos are recorded at their **full, natural duration** by default
- No speed adjustment or compression is applied unless explicitly requested
- This preserves video fidelity and accurate timing

**Explicit Duration Control:**
- Use `--video-length <seconds>` to specify a target video duration
- Speed adjustment will be applied to match the target duration
- Example: `--video-length 10` creates a 10-second video

### Examples

```bash
# Record at full duration (default behavior)
python -m ghostscroll.main https://example.com

# Record with specific duration
python -m ghostscroll.main https://example.com --video-length 15

# Record with scroll events at natural duration
python -m ghostscroll.main https://example.com --scroll-at "3,8" --scroll-duration "2,3"

# Record with scroll events and specific duration
python -m ghostscroll.main https://example.com --scroll-at "3,8" --scroll-duration "2,3" --video-length 12
```
