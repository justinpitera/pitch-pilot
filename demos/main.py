import sys
import threading
import os
import time
import json
import subprocess
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from pyvirtualdisplay.display import Display


def log(event: str, level: str = "info", message: str = "", **extra: str | int | float | bool) -> None:
    entry: dict[str, str | int | float | bool] = {
        "type": "log",
        "level": level,
        "event": event,
        "message": message,
        "timestamp": time.time(),
    }
    entry.update(extra)
    print(json.dumps(entry), flush=True)


def safe_dir_from_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.netloc}{parsed.path}".replace("/", "_").strip("_")


def record_screen(display_var: str, output_file: str, duration: float) -> subprocess.Popen[bytes]:
    log("ffmpeg_start", message=f"Recording to {output_file}", duration=duration)
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


def scroll_page(driver: WebDriver, duration: float) -> None:
    log("scroll_begin", message="Starting smooth scroll", duration=duration)
    driver.execute_script(f"""
        window._scrollState = {{
            startTime: performance.now(),
            duration: {int(duration * 1000)},
            totalHeight: document.documentElement.scrollHeight - window.innerHeight,
            finished: false
        }};

        function easeInOutCubic(t) {{
            return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        }}

        function step() {{
            const state = window._scrollState;
            const now = performance.now();
            const elapsed = now - state.startTime;
            const progress = Math.min(elapsed / state.duration, 1);
            const eased = easeInOutCubic(progress);
            const scrollY = state.totalHeight * eased;

            window.scrollTo(0, scrollY);
            state.progress = progress;

            if (progress < 1) {{
                requestAnimationFrame(step);
            }} else {{
                state.finished = true;
            }}
        }}

        requestAnimationFrame(step);
    """)

    last_percent: int = -1
    while True:
        scroll_state: dict[str, float | bool] = driver.execute_script("return window._scrollState || {}")
        progress: float = float(scroll_state.get("progress", 0))
        finished: bool = bool(scroll_state.get("finished", False))
        percent: int = int(progress * 100)

        if percent != last_percent and percent % 5 == 0:
            log("scroll_progress", progress=percent)
            last_percent = percent

        if finished:
            break

        time.sleep(0.05)

    log("scroll_complete", message="Scroll finished")


def inject_css(driver: WebDriver) -> None:
    log("inject_css", message="Injecting CSS")
    driver.execute_script("""
        const style = document.createElement('style');
        style.innerHTML = `
            * { animation: none !important; transition: none !important; }
            ::-webkit-scrollbar { display: none !important; }
            body { cursor: none !important; filter: none !important; }
        `;
        document.head.appendChild(style);
    """)


def preload_content(driver: WebDriver) -> None:
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)


def stream_ffmpeg_progress(cmd: list[str]) -> None:
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1
    )

    stdout = process.stdout
    if stdout is None:
        raise RuntimeError("process.stdout is None — did you forget stdout=subprocess.PIPE?")

    def parse_stream() -> None:
        progress_data: dict[str, str] = {}
        for line in stdout:
            line = line.strip()
            if "=" in line:
                key, value = line.split("=", 1)
                progress_data[key] = value
            if line == "progress=end":
                log("ffmpeg_progress", message="Progress complete", **progress_data)
                break
            if "frame" in progress_data:
                log("ffmpeg_frame", **progress_data)

    thread = threading.Thread(target=parse_stream)
    thread.start()
    process.wait()
    thread.join()


def adjust_video_speed(input_file: str, output_file: str, actual_duration: float, target_duration: float, slow_zones: list[tuple[float, float]]) -> None:
    rate: float = actual_duration / target_duration
    log("adjust_speed", message="Adjusting playback speed", base_rate=rate)

    filter_parts: list[str] = []
    for start, duration in slow_zones:
        end = start + duration
        part = f"between(t,{start:.2f},{end:.2f})"
        filter_parts.append(part)

    slowdown_expr = f"if({' + '.join(filter_parts)},2,{1 / rate:.5f})" if filter_parts else f"{1 / rate:.5f}"
    filter_chain: str = f"setpts={slowdown_expr}*PTS,fps=60"

    log("adjust_filter", message="Using setpts filter", expression=slowdown_expr)

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


def parse_slow_zones(arg: str) -> list[tuple[float, float]]:
    zones: list[tuple[float, float]] = []
    for pair in arg.split(","):
        if ":" not in pair:
            continue
        start_str, duration_str = pair.split(":")
        try:
            start = float(start_str)
            duration = float(duration_str)
            zones.append((start, duration))
        except ValueError:
            continue
    return zones


def main() -> None:
    if len(sys.argv) < 2:
        log("error", level="error", message="Usage: python scroll_capture.py <url> [desired_duration_seconds] [--slow start1:dur1,start2:dur2]")
        sys.exit(1)

    url: str = sys.argv[1]
    desired_duration: float = float(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else 6.0

    slow_arg = next((arg for arg in sys.argv if arg.startswith("--slow")), None)
    slow_zones: list[tuple[float, float]] = parse_slow_zones(slow_arg.replace("--slow", "").strip()) if slow_arg else []

    scroll_duration: float = min(max(desired_duration * 2.5, 6.0), 25.0)

    safe_dir: str = safe_dir_from_url(url)
    os.makedirs(safe_dir, exist_ok=True)

    raw_output: str = os.path.join(safe_dir, "scroll_raw.mp4")
    final_output: str = os.path.join(safe_dir, "scroll_final.mp4")

    display = Display(visible=False, size=(1920, 1080))
    display.start()
    log("display_start", message="Virtual display started")

    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(f"--app={url}")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=chrome_options)
    driver.set_window_size(1920, 1080)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
    })

    log("navigate", message="Navigating to page", url=url)
    driver.get(url)
    time.sleep(5)
    preload_content(driver)
    inject_css(driver)

    recorder = record_screen(display.new_display_var, raw_output, scroll_duration)
    scroll_page(driver, scroll_duration)
    recorder.wait()

    driver.quit()
    display.stop()
    log("display_stop", message="Virtual display and browser shut down")

    adjust_video_speed(raw_output, final_output, scroll_duration, desired_duration, slow_zones)

    result: dict[str, str | float] = {
        "type": "result",
        "url": url,
        "desired_duration_sec": round(desired_duration, 2),
        "raw_duration_sec": round(scroll_duration, 2),
        "output_path": final_output
    }

    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
