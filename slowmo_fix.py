"""
slowmo_fix.py  –  Stretch bukhara-showcase.mp4 to correct real-time playback.
Each frame captured took ~250ms of wall clock, so the video plays ~6x too fast.
This script duplicates each frame 6x at 24fps → ~336s correct-speed output.
"""

import cv2
from pathlib import Path

INPUT  = Path(r"C:\Projects\animated-logo\bukhara-showcase.mp4")
OUTPUT = Path(r"C:\Projects\animated-logo\bukhara-showcase-realtime.mp4")

# How many times to repeat each source frame
# capture_wall=342s / animation_duration=56s ≈ 6.1 → use 6
REPEAT = 6
FPS    = 24

cap = cv2.VideoCapture(str(INPUT))
w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
src_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

fourcc = cv2.VideoWriter_fourcc(*"mp4v")
writer = cv2.VideoWriter(str(OUTPUT), fourcc, FPS, (w, h))

out_total = src_frames * REPEAT
print(f"Source : {src_frames} frames  ({src_frames/FPS:.1f}s @ {FPS}fps)")
print(f"Repeat : x{REPEAT}")
print(f"Output : {out_total} frames  ({out_total/FPS:.1f}s @ {FPS}fps)")
print(f"File   : {OUTPUT}")
print()

i = 0
while True:
    ret, frame = cap.read()
    if not ret:
        break
    for _ in range(REPEAT):
        writer.write(frame)
    i += 1
    if i % 100 == 0:
        pct = i / src_frames * 100
        print(f"  [{pct:5.1f}%]  source frame {i}/{src_frames}")

cap.release()
writer.release()

size_mb = OUTPUT.stat().st_size / 1_048_576
print(f"\nDone!  {OUTPUT}  ({size_mb:.1f} MB)")
