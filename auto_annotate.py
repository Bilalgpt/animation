"""
Auto-annotate the Sheedi logo.
Row std-dev scan showed:
  y=88-96  : very low variance  = top solid-maroon ribbon edge
  y=104    : high variance      = gold "THE SHEEDI'S RESTAURANT" text
  y=112    : very low variance  = bottom solid-maroon ribbon edge
  y=128    : very low variance  = bottom decorative border

Banner occupies roughly y=80 -> y=134.
Top mandala  : y=0  -> y=88   (includes ribbon-top overlap for seamlessness)
Bottom mandala: y=118 -> y=214 (starts just inside bottom ribbon edge)
"""
import os, json
from PIL import Image, ImageStat

SRC = r"C:\Projects\animated-logo\SHEEDI RESTAURANT.jpeg"
OUT = r"C:\Projects\animated-logo\parts"
os.makedirs(OUT, exist_ok=True)

img  = Image.open(SRC).convert("RGB")
W, H = img.size
print(f"Image: {W} x {H} px")

# ── Full row-by-row std-dev to verify ────────────────────────────────────────
print("\nFull row std-dev:")
for y in range(H):
    row  = img.crop((0, y, W, y + 1))
    stat = ImageStat.Stat(row)
    std  = sum(stat.stddev) / 3
    bar  = "#" * int(std / 2)
    print(f"  y={y:3d}  {std:5.1f}  {bar}")

# ── Precise boundaries from scan analysis ────────────────────────────────────
# Low-variance "quiet" rows = solid ribbon surface:
#   Top ribbon quiet zone   : y=88 - y=97
#   Bottom ribbon quiet zone: y=112 - y=130
#
# We cut:
#   top-mandala    : y=0   -> y=91   (ends inside top ribbon = seamless overlap)
#   banner         : y=83  -> y=131  (full ribbon + small mandala petal overlap each side)
#   bottom-mandala : y=117 -> y=214  (starts inside bottom ribbon = seamless overlap)

TOP_END    = 91
BAN_TOP    = 83
BAN_BOTTOM = 131
BOT_START  = 117

print(f"\nCutting regions:")
print(f"  top-mandala    : y=0   -> y={TOP_END}")
print(f"  banner         : y={BAN_TOP} -> y={BAN_BOTTOM}")
print(f"  bottom-mandala : y={BOT_START} -> y={H}")

regions = [
    ("top-mandala",    (0, 0,          W, TOP_END   )),
    ("banner",         (0, BAN_TOP,    W, BAN_BOTTOM)),
    ("bottom-mandala", (0, BOT_START,  W, H         )),
]

parts_data = []
for name, box in regions:
    x1, y1, x2, y2 = box
    crop  = img.crop(box)
    fname = f"{name}.png"
    path  = os.path.join(OUT, fname)
    crop.save(path, "PNG")
    print(f"  saved  {path}  ({crop.width}x{crop.height}px)")

    parts_data.append({
        "name":  name,
        "type":  "rect",
        "file":  fname,
        "bbox":  {"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                  "width": x2-x1, "height": y2-y1},
        "points": [[x1,y1],[x2,y1],[x2,y2],[x1,y2]],
        "pct": {
            "left":   round(x1 / W * 100, 2),
            "top":    round(y1 / H * 100, 2),
            "right":  round(x2 / W * 100, 2),
            "bottom": round(y2 / H * 100, 2),
        },
        # CSS inset() for clip-path on the FULL original image
        "css_inset": (
            f"inset("
            f"{y1/H*100:.2f}% "
            f"{(W-x2)/W*100:.2f}% "
            f"{(H-y2)/H*100:.2f}% "
            f"{x1/W*100:.2f}%)"
        ),
    })

json_path = os.path.join(OUT, "annotations.json")
with open(json_path, "w") as f:
    json.dump({
        "source_image":  "SHEEDI RESTAURANT.jpeg",
        "source_width":  W,
        "source_height": H,
        "parts": parts_data,
    }, f, indent=2)
print(f"\n  saved  {json_path}")
print("\nDone. Open parts/ to verify the cropped images.")
