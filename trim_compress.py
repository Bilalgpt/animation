"""
trim_compress.py
- Reads bukhara-showcase-realtime.mp4
- Trims to the first 37s (good content, before loop)
- Resamples to fit exactly 13 seconds at 24fps
"""

import cv2
from pathlib import Path

INPUT  = Path(r"C:\Projects\animated-logo\bukhara-showcase-realtime.mp4")
OUTPUT = Path(r"C:\Projects\animated-logo\bukhara-final-13s.mp4")

FPS         = 24
TRIM_END_S  = 37        # keep only first 37 seconds
TARGET_S    = 13        # desired output duration

trim_frames   = TRIM_END_S  * FPS   # 888
target_frames = TARGET_S    * FPS   # 312
step          = trim_frames / target_frames   # ~2.846 → pick every Nth source frame

cap = cv2.VideoCapture(str(INPUT))
w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total_src = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

print(f"Source      : {total_src} frames ({total_src/FPS:.0f}s)")
print(f"Trim to     : first {TRIM_END_S}s  ({trim_frames} frames)")
print(f"Output      : {target_frames} frames -> {TARGET_S}s @ {FPS}fps")
print(f"Speed-up    : {step:.2f}x")
print()

# Pre-load trimmed source frames into a list (888 frames × ~2 MB = ~1.7 GB)
# To stay light on RAM, read on-demand by seeking instead.
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
writer = cv2.VideoWriter(str(OUTPUT), fourcc, FPS, (w, h))

last_read = -1   # last frame index actually read
frame_buf = None

def read_frame_at(cap, idx):
    """Read a specific frame index from the video."""
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ret, f = cap.read()
    return f if ret else None

for out_i in range(target_frames):
    src_idx = min(int(round(out_i * step)), trim_frames - 1)
    frame = read_frame_at(cap, src_idx)
    if frame is None:
        break
    writer.write(frame)

    if (out_i + 1) % FPS == 0:
        t = (out_i + 1) / FPS
        print(f"  [{t:5.1f}s / {TARGET_S}s]  out frame {out_i+1}/{target_frames}")

cap.release()
writer.release()

size_mb = OUTPUT.stat().st_size / 1_048_576
print(f"\nDone!  {OUTPUT}  ({size_mb:.1f} MB)")
