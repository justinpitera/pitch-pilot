"""
GhostScroll - Auto-generate scroll-driven pitch videos from any URL — clean, smooth, and client-ready.

main.py - Main entry-point for GhostScroll tool.

Copyright (c) 2025 Vetra Ventures. All rights reserved.

This is proprietary software under active development.
Access is restricted under NDA.

No license is granted to use, modify, or distribute this software
without explicit written permission.
"""

# Standard
import sys
import os
import time
import json
import threading
import subprocess
from textwrap import dedent
from typing import IO, cast
from threading import Thread
from subprocess import Popen
from urllib.parse import ParseResult, urlparse

# Third-party
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.chrome.webdriver import WebDriver as ChromeDriver
from pyvirtualdisplay.display import Display


def log(event: str, level: str = "info", message: str = "", **extra: str | int | float | bool) -> None:
    """
    Emit a structured JSON log entry to stdout.

    Args:
        event: A short identifier for the type of event (e.g. "scroll_begin").
        level: Log level string (e.g. "info", "warning", "error"). Defaults to "info".
        message: Human-readable message describing the event. Defaults to "".
        **extra: Additional key-value metadata to include in the log entry.

    Example:
        log("scroll_progress", progress=50)

    Output:
        {
            "type": "log",
            "level": "info",
            "event": "scroll_progress",
            "message": "",
            "timestamp": 1721921830.123456,
            "progress": 50
        }
    """
    entry: dict[str, str | int | float | bool] = {
        "type": "log",
        "level": level,
        "event": event,
        "message": message,
        "timestamp": time.time(),
    }
    entry.update(extra)
    print(json.dumps(obj=entry), flush=True)

def safe_dir_from_url(url: str) -> str:
    """
    Convert a URL into a filesystem-safe directory name.

    Args:
        url: The URL to convert.

    Returns:
        A sanitized string suitable for use as a directory name.
    """
    parsed: ParseResult = urlparse(url)
    return f"{parsed.netloc}{parsed.path}".replace("/", "_").strip("_")

def record_screen(display_var: str, output_file: str, duration: float) -> subprocess.Popen[bytes]:
    """
    Start recording the X11 screen using FFmpeg with VAAPI hardware acceleration.

    Args:
        display_var: The DISPLAY environment variable (e.g. ":99").
        output_file: Path to the output video file.
        duration: Duration of the recording in seconds.

    Returns:
        A subprocess.Popen handle for the running FFmpeg process.
    """
    log(event="ffmpeg_start", message=f"Recording to {output_file}", duration=duration)
    return subprocess.Popen([
        "ffmpeg",
        "-loglevel", "error",
        "-init_hw_device", "vaapi=va:/dev/dri/renderD128",
        "-filter_hw_device", "va",
        "-video_size", "1920x1080",
        "-framerate", "60",
        "-f", "x11grab",
        "-draw_mouse", "0",
        "-i", display_var,
        "-t", f"{duration:.2f}",
        "-vf", "format=nv12,hwupload",
        "-c:v", "h264_vaapi",
        "-qp", "20",
        "-y",
        output_file
    ])

def scroll_page(driver: ChromeDriver, duration: float, pause_points: list[tuple[float, float]]) -> None:
    """
    Smoothly scroll the page from top to bottom over the given duration.

    Args:
        driver: A Selenium ChromeDriver instance.
        duration: Total scroll time in seconds.
    """
    log(event="scroll_begin", message="Starting smooth scroll", duration=duration)

    driver.execute_script(script=f"window._scrollState={{startTime:performance.now(),duration:{int(duration * 1000)},totalHeight:document.documentElement.scrollHeight-window.innerHeight,finished:false}};function easeInOutCubic(t){{return t<0.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2}};function step(){{const s=window._scrollState,n=performance.now(),e=n-s.startTime,p=Math.min(e/s.duration,1),q=easeInOutCubic(p),y=s.totalHeight*q;window.scrollTo(0,y);s.progress=p;if(p<1)requestAnimationFrame(step);else s.finished=true}};requestAnimationFrame(step);") # pyright: ignore[reportUnknownMemberType]
        
    last_percent: int = -1
    while True:
        scroll_state: dict[str, float | bool] = cast(dict[str, float | bool], driver.execute_script(script="return window._scrollState || {}")) # pyright: ignore[reportUnknownMemberType]
        remaining_pauses: list[tuple[float, float]] = list(pause_points)

        progress: float = float(scroll_state.get("progress", 0))
        finished: bool = bool(scroll_state.get("finished", False))
        percent: int = int(progress * 100)

        if percent != last_percent and percent % 5 == 0:
            log(event="scroll_progress", progress=percent)
            last_percent = percent
            
        # Handle configured pauses (absolute seconds along the scroll timeline)
        elapsed_sec: float = progress * duration
        if remaining_pauses:
            next_start, next_len = remaining_pauses[0]
            # Trigger pause once when we pass the start time
            if elapsed_sec >= next_start:
                log(event="scroll_pause", message=f"Pausing at {next_start:.2f}s", pause_at=next_start, pause_len=next_len)
                time.sleep(next_len)
                remaining_pauses.pop(0)
            
        if finished:
            break

        time.sleep(0.05)

    log(event="scroll_complete", message="Scroll finished")

def inject_css(driver: ChromeDriver) -> None:
    """
    Injects custom CSS to disable animations, hide scrollbars, and hide the cursor.

    Args:
        driver: A Selenium ChromeDriver instance.
    """
    log(event="inject_css", message="Injecting CSS")
    driver.execute_script(script="document.head.appendChild(Object.assign(document.createElement('style'), {innerHTML: '*{animation:none!important;transition:none!important;}::-webkit-scrollbar{display:none!important;}body{cursor:none!important;filter:none!important;}'}));") # pyright: ignore[reportUnknownMemberType]

# --- Cookie banner suppression -------------------------------------------------

def _preseed_cookie_consent_script() -> str:
    """
    Returns JS that runs before any page scripts to pre-seed common consent keys.
    This reduces (or prevents) most CMP banners from rendering at all.
    """
    # OneTrust, Cookiebot, Quantcast, TrustArc, IAB TCF v2 common keys
    return """
    try {
      const now = new Date().toISOString();
      const seeds = {
        'OptanonConsent': 'isIABGlobal=false&datestamp=' + now + '&version=6.33.0&hosts=&consentId=ghost-scroll&interactionCount=1&landingPath=/%2F',
        'OptanonAlertBoxClosed': now,
        'CookieConsent': '{"consent":true,"timestamp":"' + now + '"}',
        'cookieconsent_status': 'allow',
        'CookieConsentPreferences': '{"necessary":true,"analytics":true,"marketing":true}',
        'euconsent-v2': 'BOx0Y0AOx0Y0AAfAAAENAA==',
        'IABTCF_TCString': 'BOx0Y0AOx0Y0AAfAAAENAA==',
        'IABTCF_gdprApplies': '0',
        'IABGPP_HDR_GppString': 'DBAB',
        'IABGPP_GppSID': '2~3',
        'truste.eu.cookie.notice_preferences': '1:1,2:1,3:1',
        'truste.eu.cookie.notice_gdpr_prefs': '0,1,2',
        'notice_behavior': 'implied,eu',
        'notice_preferences': '2:1|3:1|4:1',
        'cb_user_accepted': 'true',
        'cb_user_preferences': '{"necessary":true,"preferences":true,"statistics":true,"marketing":true}'
      };
      for (const [k,v] of Object.entries(seeds)) {
        try { localStorage.setItem(k, String(v)); } catch {}
        try { document.cookie = k + '=' + encodeURIComponent(String(v)) + '; path=/; SameSite=Lax;'; } catch {}
      }
    } catch {}
    """

def _click_cookie_buttons(driver: ChromeDriver, accept: bool) -> bool:
    """
    Try to click common CMP buttons (accept or reject). Returns True if something was clicked.
    """
    label_targets: list[str] = (["accept all","agree","allow","got it","ok","i accept","yes","continue","accept"]
                                if accept else
                                ["reject all","decline","do not accept","reject","no thanks","only necessary","strictly necessary"])
    # Normalize to lowercase once for JS
    labels_js: str = json.dumps(label_targets)

    js: str = f"""
    (function() {{
      function visible(el) {{
        const r = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return r.width>1 && r.height>1 && style.visibility!=='hidden' && style.display!=='none' && style.opacity!=='0';
      }}
      const labelTargets = {labels_js};
      const candidates = Array.from(document.querySelectorAll('button, [role="button"], a, input[type="button"], input[type="submit"]'));
      // CMP-specific fast paths
      const fast = [
        '#onetrust-accept-btn-handler',
        '#onetrust-reject-all-handler',
        'button[aria-label*="Accept All" i]',
        '.truste_buttons button',
        '.qc-cmp2-summary-buttons button',
        '.cky-btn-accept',
        '.cky-btn-reject',
        '#CybotCookiebotDialogBodyLevelButtonAccept',
        '#CybotCookiebotDialogBodyButtonDecline'
      ];
      for (const sel of fast) {{
        const el = document.querySelector(sel);
        if (el && visible(el)) {{ el.click(); return true; }}
      }}
      for (const el of candidates) {{
        const txt = (el.textContent || el.getAttribute('aria-label') || '').trim().toLowerCase();
        if (!txt) continue;
        if (labelTargets.some(s => txt.includes(s)) && visible(el)) {{ el.click(); return true; }}
      }}
      return false;
    }})()
    """
    try:
        return bool(driver.execute_script(js))  # pyright: ignore[reportUnknownMemberType]
    except Exception:
        return False

def _hide_cookie_overlays(driver: ChromeDriver) -> None:
    """
    Last-resort CSS to hide common overlay containers if clicking didn't work.
    """
    css_rules: str = """
    #onetrust-banner-sdk,
    .onetrust-pc-dark-filter,
    .qc-cmp2-container,
    .qc-cmp2-summary,
    .truste_overlay,
    .truste_box_overlay,
    .cookie-consent,
    .cookie-banner,
    .cc-window,
    .cc-banner,
    #cookie-law-info-bar,
    #CybotCookiebotDialog,
    [aria-modal="true"][role="dialog"],
    [id*="cookie"][class*="banner"],
    [class*="cookie"][class*="banner"] { display: none !important; visibility: hidden !important; opacity: 0 !important; }
    html, body { overflow: auto !important; }
    """
    driver.execute_script(  # pyright: ignore[reportUnknownMemberType]
        "document.head.appendChild(Object.assign(document.createElement('style'), {innerHTML: arguments[0]}));",
        css_rules,
    )

def suppress_cookie_banners(driver: ChromeDriver, mode: str = "accept") -> None:
    """
    mode: 'accept' | 'reject' | 'hide'
    Attempts click, then falls back to CSS hide.
    """
    log(event="cookies", message="Attempting cookie banner suppression", mode=mode)
    clicked: bool = False
    if mode in {"accept","reject"}:
        # Try a couple retries as some CMPs mount late
        for _ in range(4):
            clicked = _click_cookie_buttons(driver, accept=(mode == "accept"))
            if clicked:
                break
            time.sleep(0.75)
    if not clicked:
        _hide_cookie_overlays(driver)
    log(event="cookies_done", message="Cookie suppression finished", clicked=clicked, mode=mode)

def preload_content(driver: ChromeDriver) -> None:
    """
    Scrolls to the bottom and back to top to trigger lazy loading of page content.

    Args:
        driver: A Selenium ChromeDriver instance.
    """
    driver.execute_script(script="window.scrollTo(0, document.body.scrollHeight);") # pyright: ignore[reportUnknownMemberType]
    time.sleep(2)
    driver.execute_script(script="window.scrollTo(0, 0);") # pyright: ignore[reportUnknownMemberType]
    time.sleep(1)

def stream_ffmpeg_progress(cmd: list[str]) -> None:
    """
    Run an FFmpeg command and stream its progress output to structured logs.

    Args:
        cmd: The FFmpeg command to execute, split into a list of arguments.

    Raises:
        RuntimeError: If the subprocess fails to initialize stdout correctly.
    """
    process: Popen[str] = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1
    )

    stdout: IO[str] | None = process.stdout
    if stdout is None:
        raise RuntimeError("process.stdout is None — did you forget stdout=subprocess.PIPE?")

    def parse_stream() -> None:
        progress_data: dict[str, str] = {}
        for line in stdout:
            line: str = line.strip()
            if "=" in line:
                key, value = line.split(sep="=", maxsplit=1)
                progress_data[key] = value
            if line == "progress=end":
                log(event="ffmpeg_progress", message="Progress complete", **progress_data)
                break
            if "frame" in progress_data:
                log(event="ffmpeg_frame", **progress_data)

    thread: Thread = threading.Thread(target=parse_stream)
    thread.start()
    _ = process.wait()
    thread.join()

def overlay_avatar(input_file: str, output_file: str, avatar_path: str) -> None:
    """
    Overlay a rounded avatar image or video in the bottom-right corner of the video.

    Args:
        input_file: Path to the input video.
        output_file: Path to the final video with avatar.
        avatar_path: Path to the avatar image or video (e.g., avatar.jpg or avatar.mp4).
    """
    log(event="overlay_avatar", message="Overlaying avatar", avatar=avatar_path)

    is_video: bool = avatar_path.lower().endswith((".mp4", ".webm", ".mov", ".mkv"))

    if is_video:
        filter_complex: str = dedent(text="""
            [1:v]scale=100:100:force_original_aspect_ratio=decrease,format=rgba,setsar=1[vav];
            [0:v][vav]overlay=W-w-30:H-h-30:shortest=1:format=auto
        """).strip().replace("\n", "")
    else:
        filter_complex = dedent(text="""
            [1:v]format=rgba,scale=100:100,geq='lum(X,Y)':128:128,split[base][mask];
            [mask]drawbox=0:0:100:100:black@0.0:t=fill,format=gray,
            geq='if(gt((X-50)*(X-50)+(Y-50)*(Y-50),2500),0,255)'[alpha];
            [base][alpha]alphamerge[avatar];
            [0:v][avatar]overlay=W-w-30:H-h-30:format=auto
        """).strip().replace("\n", "")

    cmd: list[str] = [
        "ffmpeg",
        "-loglevel", "error",
        "-y",
        "-stream_loop", "-1" if is_video else "0",
        "-i", input_file,
        "-i", avatar_path,
        "-filter_complex", filter_complex,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        output_file
    ]

    result: subprocess.CompletedProcess[bytes] = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        log(event="error", level="error", message="Failed to overlay avatar")
    else:
        log(event="overlay_complete", message="Avatar overlay finished")


def adjust_video_speed(input_file: str, output_file: str, actual_duration: float, target_duration: float, slow_zones: list[tuple[float, float]]) -> None:
    """
    Adjust the playback speed of a video using FFmpeg, with optional slow zones.

    Args:
        input_file: Path to the input video file.
        output_file: Path to the output video file.
        actual_duration: Original scroll recording duration in seconds.
        target_duration: Desired final video length in seconds.
        slow_zones: List of (start_time, duration) tuples to slow down specific segments.
    """
    rate: float = actual_duration / target_duration
    log(event="adjust_speed", message="Adjusting playback speed", base_rate=rate)

    filter_parts: list[str] = []
    for start, duration in slow_zones:
        end: float = start + duration
        part: str = f"between(t,{start:.2f},{end:.2f})"
        filter_parts.append(part)

    slowdown_expr: str = f"if({' + '.join(filter_parts)},2,{1 / rate:.5f})" if filter_parts else f"{1 / rate:.5f}"
    filter_chain: str = f"setpts={slowdown_expr}*PTS,fps=60"

    log(event="adjust_filter", message="Using setpts filter", expression=slowdown_expr)

    cmd: list[str] = [
        "ffmpeg",
        "-y",
        "-loglevel", "error",
        "-i", input_file,
        "-filter:v", filter_chain,
        "-an",
        "-progress", "pipe:1",
        "-nostats",
        output_file
    ]
    stream_ffmpeg_progress(cmd)


def parse_scroll_timings(scroll_at_arg: str, scroll_duration_arg: str) -> list[tuple[float, float]]:
    """
    Parse scroll-at and scroll-duration arguments into (start_time, duration) tuples.
    
    Args:
        scroll_at_arg: Comma-separated timestamps like "2,6,12"
        scroll_duration_arg: Comma-separated durations like "2,3,4" 
    
    Returns:
        List of (start_time, duration) tuples, sorted by start_time.
        If argument lengths don't match, uses minimum length.
    """
    scroll_times: list[float] = []
    scroll_durations: list[float] = []
    
    # Parse scroll times
    for time_str in scroll_at_arg.split(","):
        try:
            time_val = float(time_str.strip())
            if time_val >= 0:
                scroll_times.append(time_val)
        except ValueError:
            continue
    
    # Parse scroll durations
    for dur_str in scroll_duration_arg.split(","):
        try:
            dur_val = float(dur_str.strip())
            if dur_val > 0:
                scroll_durations.append(dur_val)
        except ValueError:
            continue
    
    # Pair up times and durations (use minimum length)
    min_len = min(len(scroll_times), len(scroll_durations))
    points = [(scroll_times[i], scroll_durations[i]) for i in range(min_len)]
    points.sort(key=lambda p: p[0])
    return points

def parse_pause_points(arg: str) -> list[tuple[float, float]]:
    """
    Parse a comma-separated list like "2:3,5:1" into [(2.0, 3.0), (5.0, 1.0)].
    Invalid entries are skipped silently.
    
    DEPRECATED: This function is kept for backward compatibility but will be removed.
    Use parse_scroll_timings() instead.
    """
    points: list[tuple[float, float]] = []
    for token in arg.split(sep=","):
        if ":" not in token:
            continue
        start_str, dur_str = token.split(sep=":", maxsplit=1)
        try:
            start: float = float(start_str)
            dur: float = float(dur_str)
            if start >= 0 and dur > 0:
                points.append((start, dur))
        except ValueError:
            continue
    points.sort(key=lambda p: p[0])
    return points

def main() -> None:
    """
    Orchestrates the full scroll recording workflow:
    - Parses CLI arguments for URL, scroll timings, and video length
    - Starts a virtual X11 display
    - Launches a headless Chrome session to load and prepare the page
    - Preloads lazy content and injects anti-animation CSS
    - Records a smooth scroll using FFmpeg with VAAPI acceleration
    - Applies playback speed adjustments to match desired video length
    - Overlays a rounded avatar image in the bottom-right corner (if present)
    - Writes out the final rendered video and logs the result
    """
    if len(sys.argv) < 2:
        log(
            event="error",
            level="error",
            message="Usage: main.py <url> [--scroll-at times] [--scroll-duration durations] [--video-length seconds] [--avatar path/to/avatar.jpg]"
        )
        sys.exit(1)

    url: str = sys.argv[1]

    # Parse new scroll timing arguments
    scroll_at_arg: str | None = None
    if "--scroll-at" in sys.argv:
        i = sys.argv.index("--scroll-at")
        if i + 1 < len(sys.argv):
            scroll_at_arg = sys.argv[i + 1]

    scroll_duration_arg: str | None = None
    if "--scroll-duration" in sys.argv:
        i = sys.argv.index("--scroll-duration")
        if i + 1 < len(sys.argv):
            scroll_duration_arg = sys.argv[i + 1]

    # Parse video length argument (replaces positional desired_duration)
    desired_duration: float = 6.0  # Default
    if "--video-length" in sys.argv:
        i = sys.argv.index("--video-length")
        if i + 1 < len(sys.argv):
            try:
                desired_duration = float(sys.argv[i + 1])
            except ValueError:
                log(event="error", level="error", message="Invalid video length specified")
                sys.exit(1)

    # Convert new scroll arguments to pause points format (backward compatibility)
    pause_points: list[tuple[float, float]] = []
    if scroll_at_arg and scroll_duration_arg:
        pause_points = parse_scroll_timings(scroll_at_arg, scroll_duration_arg)
    
    # Remove slow zones functionality - no longer supported
    slow_zones: list[tuple[float, float]] = []

    avatar_arg_index: int = sys.argv.index("--avatar") + 1 if "--avatar" in sys.argv else -1
    avatar_path: str = sys.argv[avatar_arg_index] if avatar_arg_index > 0 and avatar_arg_index < len(sys.argv) else "avatar.jpg"

    # Optional flag: --cookies accept|reject|hide  (default: accept)
    cookies_mode: str = "accept"
    if "--cookies" in sys.argv:
        i: int = sys.argv.index("--cookies")
        if i + 1 < len(sys.argv):
            val: str = sys.argv[i + 1].strip().lower()
            if val in {"accept", "reject", "hide"}:
                cookies_mode = val
                
    scroll_duration: float = min(max(desired_duration * 2.5, 6.0), 25.0)

    safe_dir: str = safe_dir_from_url(url)
    os.makedirs(name=safe_dir, exist_ok=True)

    raw_output: str = os.path.join(safe_dir, "scroll_raw.mp4")
    final_output: str = os.path.join(safe_dir, "scroll_final.mp4")
    avatar_output: str = os.path.join(safe_dir, "scroll_with_avatar.mp4")

    display: Display = Display(visible=False, size=(1920, 1080))
    _ = display.start()
    log(event="display_start", message="Virtual display started")

    chrome_options: Options = Options()
    chrome_options.add_argument(argument="--no-sandbox")
    chrome_options.add_argument(argument="--disable-gpu")
    chrome_options.add_argument(argument="--disable-dev-shm-usage")
    chrome_options.add_argument(argument="--disable-infobars")
    chrome_options.add_argument(argument="--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(argument="--window-size=1920,1080")
    chrome_options.add_argument(argument=f"--app={url}")
    chrome_options.add_experimental_option(name="excludeSwitches", value=["enable-automation"])  # pyright: ignore[reportUnknownMemberType]
    chrome_options.add_experimental_option(name="useAutomationExtension", value=False)          # pyright: ignore[reportUnknownMemberType]

    driver: WebDriver = webdriver.Chrome(options=chrome_options)
    driver.set_window_size(width=1920, height=1080)  # pyright: ignore[reportUnknownMemberType]
    driver.execute_cdp_cmd(  # pyright: ignore[reportUnknownMemberType]
        cmd="Page.addScriptToEvaluateOnNewDocument",
        cmd_args={
            "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
        }
    )
    # Pre-  seed consent/localStorage so many CMPs never render
    driver.execute_cdp_cmd(  # pyright: ignore[reportUnknownMemberType]
        cmd="Page.addScriptToEvaluateOnNewDocument",
        cmd_args={"source": _preseed_cookie_consent_script()},
    )

    log(event="navigate", message="Navigating to page", url=url)
    driver.get(url)
    time.sleep(5)
    preload_content(driver)
    inject_css(driver)
    suppress_cookie_banners(driver=driver, mode=cookies_mode)

    recorder: Popen[bytes] = record_screen(display_var=display.new_display_var, output_file=raw_output, duration=scroll_duration)
    
    # Only scroll when explicit scroll arguments are provided
    if scroll_at_arg and scroll_duration_arg:
        scroll_page(driver=driver, duration=scroll_duration, pause_points=pause_points)
    else:
        # Keep page static - just wait for recording to complete
        log(event="static_wait", message="Keeping page static", duration=scroll_duration)
        time.sleep(scroll_duration)
        log(event="static_complete", message="Static recording finished")
    
    _ = recorder.wait()

    driver.quit()
    _ = display.stop()
    log(event="display_stop", message="Virtual display and browser shut down")

    adjust_video_speed(
        input_file=raw_output,
        output_file=final_output,
        actual_duration=scroll_duration,
        target_duration=desired_duration,
        slow_zones=slow_zones  # Now always empty since slow zones are removed
    )

    if os.path.isfile(path=avatar_path):
        overlay_avatar(
            input_file=final_output,
            output_file=avatar_output,
            avatar_path=avatar_path
        )
    else:
        log(
            event="avatar_skipped",
            level="warning",
            message="Avatar file not found, skipping overlay",
            avatar=avatar_path
        )
        avatar_output = final_output

    result: dict[str, str | float] = {
        "type": "result",
        "url": url,
        "desired_duration_sec": round(number=desired_duration, ndigits=2),
        "raw_duration_sec": round(number=scroll_duration, ndigits=2),
        "output_path": avatar_output
    }

    print(json.dumps(obj=result), flush=True)

if __name__ == "__main__":
    """Main entry-point"""
    main()
