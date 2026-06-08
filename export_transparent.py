"""
export_transparent.py
---------------------
Renders an HTML animation to a transparent WebM (VP9 + alpha) using
Playwright for frame capture and FFmpeg for encoding.

Usage:
    python export_transparent.py --html trust-dmc-v3/main.html --width 820 --height 820 --duration 8 --out exports/trust-dmc-v3-transparent.webm
    python export_transparent.py --html trust-dmc-v4/main.html --width 820 --height 820 --duration 8 --out exports/trust-dmc-v4-transparent.webm
    python export_transparent.py --html trust-dmc-v5/main.html --width 1080 --height 1920 --duration 8 --out exports/trust-dmc-v5-transparent.webm

Or run without arguments to export all three at once.
"""

import argparse, os, shutil, subprocess, sys, time, tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

FFMPEG = r"C:\Users\bilal\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"
FPS    = 30
BASE   = Path(__file__).parent

PRESETS = [
    {"html": "trust-dmc-v3/main.html", "width": 820,  "height": 820,  "duration": 8, "out": "exports/trust-dmc-v3-transparent.mov"},
    {"html": "trust-dmc-v4/main.html", "width": 820,  "height": 820,  "duration": 8, "out": "exports/trust-dmc-v4-transparent.mov"},
    {"html": "trust-dmc-v5/main.html", "width": 1080, "height": 1920, "duration": 8, "out": "exports/trust-dmc-v5-transparent.mov"},
]


def render(html_path: str, width: int, height: int, duration: float, out_path: str, fps: int = FPS):
    html_abs  = (BASE / html_path).resolve()
    out_abs   = (BASE / out_path).resolve()
    out_abs.parent.mkdir(parents=True, exist_ok=True)

    frames_dir = Path(tempfile.mkdtemp(prefix="logo_frames_"))
    total_frames = int(duration * fps)
    frame_ms     = 1000 / fps          # ms per frame

    print(f"\n{'='*60}")
    print(f"  Source  : {html_abs}")
    print(f"  Output  : {out_abs}")
    print(f"  Size    : {width}x{height}  |  {duration}s @ {fps}fps  |  {total_frames} frames")
    print(f"  Frames  : {frames_dir}")
    print(f"{'='*60}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=[
                "--disable-web-security",
                "--allow-file-access-from-files",
                "--disable-gpu",
                "--enable-transparent-visuals",
            ]
        )
        ctx = browser.new_context(
            viewport={"width": width, "height": height},
        )
        page = ctx.new_page()

        # Open the file
        page.goto(html_abs.as_uri())

        # Force transparent background
        page.evaluate("""() => {
            document.documentElement.style.background = 'transparent';
            document.body.style.background = 'transparent';
        }""")

        # Wait for fonts + images
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(0.5)

        print(f"  Capturing {total_frames} frames...")
        t0 = time.time()

        for i in range(total_frames):
            frame_path = frames_dir / f"frame_{i:05d}.png"
            page.screenshot(
                path=str(frame_path),
                omit_background=True,   # RGBA PNG — real transparency
                clip={"x": 0, "y": 0, "width": width, "height": height},
            )

            # Real-time pacing so animations advance naturally
            target_t = t0 + (i + 1) / fps
            sleep_s  = target_t - time.time()
            if sleep_s > 0:
                time.sleep(sleep_s)

            if (i + 1) % 30 == 0 or i == total_frames - 1:
                pct = (i + 1) / total_frames * 100
                print(f"    frame {i+1:4d}/{total_frames}  ({pct:.0f}%)")

        browser.close()

    print(f"\n  Encoding transparent MOV (PNG codec + RGBA)...")
    cmd = [
        FFMPEG, "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%05d.png"),
        "-c:v", "png",        # PNG codec inside MOV — full RGBA, lossless alpha
        "-pix_fmt", "rgba",   # preserve alpha channel
        str(out_abs),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFmpeg error:\n", result.stderr[-2000:])
        sys.exit(1)

    shutil.rmtree(frames_dir)

    size_mb = out_abs.stat().st_size / 1024 / 1024
    print(f"\n  Done! {out_abs.name}  ({size_mb:.1f} MB)")


def main():
    parser = argparse.ArgumentParser(description="Export HTML animation as transparent WebM")
    parser.add_argument("--html",     help="Path to HTML file (relative to script)")
    parser.add_argument("--width",    type=int, help="Viewport width in px")
    parser.add_argument("--height",   type=int, help="Viewport height in px")
    parser.add_argument("--duration", type=float, default=8, help="Duration in seconds (default: 8)")
    parser.add_argument("--fps",      type=int,   default=FPS, help="Frames per second (default: 30)")
    parser.add_argument("--out",      help="Output path (relative to script)")
    args = parser.parse_args()

    if args.html:
        # Single export
        if not args.width or not args.height or not args.out:
            parser.error("--width, --height and --out are required with --html")
        render(args.html, args.width, args.height, args.duration, args.out, args.fps)
    else:
        # Export all presets
        print(f"Exporting all {len(PRESETS)} presets...\n")
        for p in PRESETS:
            render(p["html"], p["width"], p["height"], p["duration"], p["out"])
        print("\nAll exports complete!")
        print(f"Files saved to: {(BASE / 'exports').resolve()}")


if __name__ == "__main__":
    main()
