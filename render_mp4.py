"""
render_mp4.py  –  Capture main.html animation → bukhara-showcase.mp4
Requires:  pip install playwright opencv-python numpy
           python -m playwright install chromium
"""

import asyncio
import time
import numpy as np
import cv2
from pathlib import Path
from playwright.async_api import async_playwright

# ── Config ─────────────────────────────────────────────────────────────────
HTML_FILE   = Path(r"C:\Projects\animated-logo\scenes\main.html")
OUTPUT_FILE = Path(r"C:\Projects\animated-logo\bukhara-showcase.mp4")
TARGET_FPS  = 24          # frames per second
W, H        = 820, 820    # must match .stage size in HTML

# Scene durations (ms) — must mirror JS DURATIONS array
SCENE_DURATIONS = [4000, 5000, 5000, 5000, 5000, 5000, 5000, 8000, 6000, 8000]
TOTAL_MS        = sum(SCENE_DURATIONS)          # 56 000 ms
TOTAL_FRAMES    = int(TOTAL_MS / 1000 * TARGET_FPS)   # 1 344

# ── Helpers ────────────────────────────────────────────────────────────────
def png_bytes_to_bgr(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)

# ── Main ───────────────────────────────────────────────────────────────────
async def capture():
    file_url = HTML_FILE.as_uri()

    print(f"Opening  : {HTML_FILE}")
    print(f"Output   : {OUTPUT_FILE}")
    print(f"Duration : {TOTAL_MS/1000:.1f}s  |  {TOTAL_FRAMES} frames @ {TARGET_FPS}fps")
    print()

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(OUTPUT_FILE), fourcc, TARGET_FPS, (W, H))

    if not writer.isOpened():
        raise RuntimeError("cv2.VideoWriter could not open output file.")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--autoplay-policy=no-user-gesture-required",
            ],
        )
        ctx = await browser.new_context(
            viewport={"width": W, "height": H},
            device_scale_factor=1,
        )
        page = await ctx.new_page()

        # Load the file; give fonts/images a moment to arrive
        await page.goto(file_url, wait_until="load")
        await page.wait_for_timeout(600)   # 0.6s settle

        frame_ms   = 1000.0 / TARGET_FPS   # ~41.67 ms
        written    = 0
        t_start    = time.perf_counter()

        for i in range(TOTAL_FRAMES):
            # Wall-clock target for this frame
            target_wall = t_start + i * frame_ms / 1000.0
            now = time.perf_counter()
            if now < target_wall:
                await asyncio.sleep(target_wall - now)

            data  = await page.screenshot(type="png",
                                           clip={"x": 0, "y": 0,
                                                 "width": W, "height": H})
            frame = png_bytes_to_bgr(data)
            writer.write(frame)
            written += 1

            # Progress every second
            if written % TARGET_FPS == 0:
                elapsed = time.perf_counter() - t_start
                scene_t = written / TARGET_FPS
                pct     = scene_t / (TOTAL_MS / 1000) * 100
                print(f"  [{pct:5.1f}%]  frame {written:4d}/{TOTAL_FRAMES}"
                      f"  anim={scene_t:.1f}s  wall={elapsed:.1f}s")

        await browser.close()

    writer.release()
    size_mb = OUTPUT_FILE.stat().st_size / 1_048_576
    print(f"\nDone!  {OUTPUT_FILE}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    asyncio.run(capture())
