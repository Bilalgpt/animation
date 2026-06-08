"""
Logo Annotator
==============
Annotate regions of a logo image using rectangles OR freeform polygons.
Each region is saved as a separate PNG + an annotations.json.

Usage:
    python annotate.py "SHEEDI RESTAURANT.jpeg"
    python annotate.py               (opens file-picker dialog)

Requirements:
    pip install Pillow

Controls:
    RECTANGLE mode  — click and drag
    POLYGON mode    — click to add points, Enter to close, Esc to cancel

Output  →  parts/  folder next to the image:
    parts/<name>.png          cropped region (polygon areas have transparency)
    parts/annotations.json    pixel coords, bounding box, CSS clip-path values
"""

import sys
import os
import json
import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog

try:
    from PIL import Image, ImageTk, ImageDraw
except ImportError:
    print("\n[ERROR] Pillow is not installed.")
    print("Run:  pip install Pillow\n")
    sys.exit(1)


COLOURS = [
    '#ff4444', '#44dd44', '#4499ff', '#ffdd00',
    '#ff44ff', '#44ffee', '#ff8800', '#88ff00',
    '#ff8888', '#88ffbb',
]


# ─────────────────────────────────────────────────────────────────────────────
class LogoAnnotator:

    def __init__(self, root: tk.Tk, image_path: str):
        self.root       = root
        self.image_path = image_path
        self.annotations: list[dict] = []

        # ── Load image ──────────────────────────────────────────────────────
        self.orig   = Image.open(image_path).convert("RGBA")
        self.orig_w, self.orig_h = self.orig.size

        max_w, max_h = 920, 720
        scale        = min(max_w / self.orig_w, max_h / self.orig_h, 1.0)
        self.disp_w  = int(self.orig_w * scale)
        self.disp_h  = int(self.orig_h * scale)
        self.scale   = scale

        disp_img    = self.orig.resize((self.disp_w, self.disp_h), Image.LANCZOS)
        self.photo  = ImageTk.PhotoImage(disp_img)

        # ── Drawing state ───────────────────────────────────────────────────
        self.mode       = tk.StringVar(value="rect")   # "rect" | "polygon"

        # rect
        self._r_start   = (0, 0)
        self._r_id      = None          # canvas item id of live rect preview

        # polygon
        self._p_pts     = []            # display coords [(x,y), ...]
        self._p_dot_ids = []            # canvas circle ids for vertices
        self._p_seg_ids = []            # canvas line ids for edges
        self._p_prev_id = None          # rubber-band line id

        # ── Build UI ────────────────────────────────────────────────────────
        root.title(f"Logo Annotator  —  {os.path.basename(image_path)}")
        root.resizable(False, False)

        # Canvas
        self.canvas = tk.Canvas(root,
                                width=self.disp_w, height=self.disp_h,
                                cursor="crosshair", bg="#111",
                                highlightthickness=0)
        self.canvas.grid(row=0, column=0, padx=(8, 4), pady=8)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

        # Right panel
        panel = tk.Frame(root, padx=8, pady=8)
        panel.grid(row=0, column=1, sticky="n")

        # Mode selector
        mode_lf = tk.LabelFrame(panel, text="Draw mode", padx=6, pady=6)
        mode_lf.pack(fill="x", pady=(0, 8))
        tk.Radiobutton(mode_lf, text="■  Rectangle  (drag)",
                       variable=self.mode, value="rect",
                       command=self._cancel_polygon).pack(anchor="w")
        tk.Radiobutton(mode_lf, text="⬡  Polygon   (click points)",
                       variable=self.mode, value="polygon",
                       command=self._cancel_polygon).pack(anchor="w")

        # Annotations list
        tk.Label(panel, text="Annotated regions",
                 font=("Arial", 10, "bold")).pack(anchor="w")
        self.listbox = tk.Listbox(panel, width=34, height=16,
                                  font=("Consolas", 8), selectmode=tk.SINGLE)
        self.listbox.pack(pady=(2, 4))

        tk.Button(panel, text="✕  Delete selected  [Del]",
                  command=self.delete_selected, width=26).pack(pady=2)
        tk.Button(panel, text="↩  Load annotations.json",
                  command=self._load_json_dialog, width=26).pack(pady=2)
        tk.Button(panel, text="💾  Save all parts",
                  command=self.save_all,
                  bg="#1a6e1a", fg="white",
                  font=("Arial", 10, "bold"), width=26).pack(pady=(10, 4))

        # Image info
        info = tk.Frame(panel)
        info.pack(anchor="w", pady=(8, 0))
        tk.Label(info, text=f"Image:  {self.orig_w} × {self.orig_h} px",
                 font=("Consolas", 8), fg="#555").pack(anchor="w")
        tk.Label(info, text=f"Scale:  {scale:.3f}×",
                 font=("Consolas", 8), fg="#555").pack(anchor="w")

        # Status bar (bottom of window)
        self.status_var = tk.StringVar(value="Rectangle mode — click and drag to draw")
        status_bar = tk.Label(root, textvariable=self.status_var,
                              anchor="w", relief=tk.SUNKEN,
                              font=("Arial", 9), fg="#333", bg="#eee", padx=6)
        status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")

        self.mode.trace_add("write", self._update_status)
        self._update_status()

        # ── Bindings ─────────────────────────────────────────────────────────
        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",        self._on_drag)
        self.canvas.bind("<ButtonRelease-1>",  self._on_release)
        self.canvas.bind("<Motion>",           self._on_move)
        self.canvas.bind("<Double-Button-1>",  self._on_double_click)

        root.bind("<Return>",  self._close_polygon)
        root.bind("<Escape>",  lambda _: self._cancel_polygon())
        root.bind("<Delete>",  lambda _: self.delete_selected())
        root.bind("<r>",       lambda _: self.mode.set("rect"))
        root.bind("<p>",       lambda _: self.mode.set("polygon"))

        # Auto-load existing json
        auto = self._json_path()
        if os.path.exists(auto):
            if messagebox.askyesno("Existing annotations found",
                                   f"Load existing:\n{auto}?"):
                self._load_json_file(auto)

    # ── Status bar ───────────────────────────────────────────────────────────
    def _update_status(self, *_):
        if self.mode.get() == "rect":
            self.status_var.set(
                "RECTANGLE mode  —  click and drag to draw  |  R = rect  P = polygon")
        else:
            n = len(self._p_pts)
            if n == 0:
                self.status_var.set(
                    "POLYGON mode  —  click to add points  |  Enter = close  Esc = cancel")
            else:
                self.status_var.set(
                    f"POLYGON mode  —  {n} point(s) placed  |  "
                    "Enter / double-click = close  |  Esc = cancel")

    # ── Mouse events — RECT ──────────────────────────────────────────────────
    def _on_press(self, event):
        if self.mode.get() != "rect":
            return
        self._r_start = (event.x, event.y)
        self._r_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#ffffff", width=1, dash=(4, 3))

    def _on_drag(self, event):
        if self.mode.get() != "rect" or self._r_id is None:
            return
        self.canvas.coords(self._r_id, *self._r_start, event.x, event.y)

    def _on_release(self, event):
        if self.mode.get() != "rect" or self._r_id is None:
            return
        x0, y0 = self._r_start
        x1, y1 = event.x, event.y
        self.canvas.delete(self._r_id)
        self._r_id = None
        if abs(x1 - x0) < 6 or abs(y1 - y0) < 6:
            return
        self._finalise_rect(
            min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    # ── Mouse events — POLYGON ────────────────────────────────────────────────
    def _on_move(self, event):
        if self.mode.get() != "polygon" or not self._p_pts:
            return
        lx, ly = self._p_pts[-1]
        if self._p_prev_id:
            self.canvas.coords(self._p_prev_id, lx, ly, event.x, event.y)
        else:
            colour = COLOURS[len(self.annotations) % len(COLOURS)]
            self._p_prev_id = self.canvas.create_line(
                lx, ly, event.x, event.y,
                fill=colour, width=1, dash=(3, 3))

    def _on_double_click(self, event):
        if self.mode.get() == "polygon" and len(self._p_pts) >= 3:
            self._close_polygon()

    def _polygon_add_point(self, event):
        """Add one vertex in polygon mode."""
        colour = COLOURS[len(self.annotations) % len(COLOURS)]
        x, y   = event.x, event.y

        # Draw segment from previous point
        if self._p_pts:
            px, py = self._p_pts[-1]
            seg = self.canvas.create_line(px, py, x, y, fill=colour, width=2)
            self._p_seg_ids.append(seg)

        # Draw vertex dot
        dot = self.canvas.create_oval(
            x - 4, y - 4, x + 4, y + 4,
            fill=colour, outline="#fff", width=1)
        self._p_dot_ids.append(dot)
        self._p_pts.append((x, y))
        self._update_status()

    # Double-click fires Button-1 first, so we use _on_press gating:
    def _on_press(self, event):   # noqa: F811 — intentional redefinition
        if self.mode.get() == "rect":
            self._r_start = (event.x, event.y)
            self._r_id = self.canvas.create_rectangle(
                event.x, event.y, event.x, event.y,
                outline="#ffffff", width=1, dash=(4, 3))
        else:
            # Polygon: ignore if this click is part of a double-click
            # (we check _closing flag set by _close_polygon / _on_double_click)
            if getattr(self, "_closing", False):
                self._closing = False
                return
            self._polygon_add_point(event)

    def _close_polygon(self, event=None):
        if self.mode.get() != "polygon" or len(self._p_pts) < 3:
            return
        self._closing = True   # flag to suppress the Button-1 that fires with double-click

        colour = COLOURS[len(self.annotations) % len(COLOURS)]

        # Close the shape (last → first)
        lx, ly = self._p_pts[-1]
        fx, fy = self._p_pts[0]
        seg = self.canvas.create_line(lx, ly, fx, fy, fill=colour, width=2)
        self._p_seg_ids.append(seg)

        # Remove rubber-band line
        if self._p_prev_id:
            self.canvas.delete(self._p_prev_id)
            self._p_prev_id = None

        pts = list(self._p_pts)
        all_ids = self._p_dot_ids + self._p_seg_ids
        self._p_pts, self._p_dot_ids, self._p_seg_ids = [], [], []
        self._update_status()

        self._finalise_polygon(pts, all_ids)

    def _cancel_polygon(self):
        for cid in self._p_dot_ids + self._p_seg_ids:
            self.canvas.delete(cid)
        if self._p_prev_id:
            self.canvas.delete(self._p_prev_id)
        self._p_pts, self._p_dot_ids, self._p_seg_ids = [], [], []
        self._p_prev_id = None
        self._update_status()

    # ── Finalise helpers ─────────────────────────────────────────────────────
    def _ask_name(self) -> str | None:
        name = simpledialog.askstring(
            "Name this region",
            "Enter a name  (e.g.  top-mandala,  banner,  bottom-mandala):",
            parent=self.root)
        if not name or not name.strip():
            return None
        name = name.strip().lower().replace(" ", "-")
        # deduplicate
        taken = [a["name"] for a in self.annotations]
        base  = name
        i     = 2
        while name in taken:
            name = f"{base}-{i}"; i += 1
        return name

    def _colour_for_next(self) -> str:
        return COLOURS[len(self.annotations) % len(COLOURS)]

    def _add_annotation(self, ann: dict):
        self.annotations.append(ann)
        ox1, oy1 = ann["bbox"]["x1"], ann["bbox"]["y1"]
        ox2, oy2 = ann["bbox"]["x2"], ann["bbox"]["y2"]
        tag = "poly" if ann["type"] == "polygon" else "rect"
        self.listbox.insert(
            tk.END,
            f"[{len(self.annotations):02d}][{tag}] {ann['name']}  "
            f"{ox2-ox1}×{oy2-oy1}px")

    def _finalise_rect(self, sx1, sy1, sx2, sy2):
        name = self._ask_name()
        if not name:
            return
        colour = self._colour_for_next()

        # Permanent rect + label on canvas
        rid = self.canvas.create_rectangle(
            sx1, sy1, sx2, sy2, outline=colour, width=2)
        lid = self.canvas.create_text(
            sx1 + 4, sy1 + 4, anchor=tk.NW, text=name,
            fill=colour, font=("Arial", 10, "bold"))

        ox1 = max(0, int(sx1 / self.scale))
        oy1 = max(0, int(sy1 / self.scale))
        ox2 = min(self.orig_w, int(sx2 / self.scale))
        oy2 = min(self.orig_h, int(sy2 / self.scale))

        ann = dict(
            type     = "rect",
            name     = name,
            canvas_ids = [rid, lid],
            colour   = colour,
            bbox     = dict(x1=ox1, y1=oy1, x2=ox2, y2=oy2),
            points   = [[ox1, oy1], [ox2, oy1], [ox2, oy2], [ox1, oy2]],
        )
        self._add_annotation(ann)

    def _finalise_polygon(self, disp_pts: list, canvas_ids: list):
        name = self._ask_name()
        if not name:
            # Remove the drawn lines/dots if user cancels naming
            for cid in canvas_ids:
                self.canvas.delete(cid)
            return
        colour = self._colour_for_next()

        # Draw filled semi-transparent polygon overlay + label
        flat = [c for pt in disp_pts for c in pt]
        poly_id = self.canvas.create_polygon(
            *flat,
            outline=colour, fill=colour, stipple="gray25", width=2)
        xs = [p[0] for p in disp_pts]
        ys = [p[1] for p in disp_pts]
        lid = self.canvas.create_text(
            min(xs) + 4, min(ys) + 4, anchor=tk.NW, text=name,
            fill=colour, font=("Arial", 10, "bold"))

        # Convert display → original coords
        orig_pts = [
            [min(self.orig_w, max(0, int(px / self.scale))),
             min(self.orig_h, max(0, int(py / self.scale)))]
            for px, py in disp_pts
        ]
        oxs = [p[0] for p in orig_pts]
        oys = [p[1] for p in orig_pts]

        ann = dict(
            type       = "polygon",
            name       = name,
            canvas_ids = canvas_ids + [poly_id, lid],
            colour     = colour,
            bbox       = dict(x1=min(oxs), y1=min(oys),
                               x2=max(oxs), y2=max(oys)),
            points     = orig_pts,
        )
        self._add_annotation(ann)

    # ── Delete ───────────────────────────────────────────────────────────────
    def delete_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        ann = self.annotations[idx]
        for cid in ann.get("canvas_ids", []):
            self.canvas.delete(cid)
        self.annotations.pop(idx)
        self.listbox.delete(idx)
        # Refresh list labels
        self.listbox.delete(0, tk.END)
        for i, a in enumerate(self.annotations):
            b   = a["bbox"]
            tag = "poly" if a["type"] == "polygon" else "rect"
            self.listbox.insert(
                tk.END,
                f"[{i+1:02d}][{tag}] {a['name']}  "
                f"{b['x2']-b['x1']}×{b['y2']-b['y1']}px")

    # ── Save ─────────────────────────────────────────────────────────────────
    def save_all(self):
        if not self.annotations:
            messagebox.showinfo("Nothing to save", "Annotate some regions first.")
            return

        out_dir = os.path.join(
            os.path.dirname(os.path.abspath(self.image_path)), "parts")
        os.makedirs(out_dir, exist_ok=True)

        parts_data = []

        for ann in self.annotations:
            b    = ann["bbox"]
            bbox = (b["x1"], b["y1"], b["x2"], b["y2"])
            pts  = [(p[0], p[1]) for p in ann["points"]]

            if ann["type"] == "rect":
                crop = self.orig.crop(bbox)
            else:
                # Polygon: crop bounding box, then mask outside polygon
                crop    = self.orig.crop(bbox).convert("RGBA")
                mask    = Image.new("L", (b["x2"]-b["x1"], b["y2"]-b["y1"]), 0)
                draw    = ImageDraw.Draw(mask)
                local   = [(px - b["x1"], py - b["y1"]) for px, py in pts]
                draw.polygon(local, fill=255)
                crop.putalpha(mask)

            fname = f"{ann['name']}.png"
            fpath = os.path.join(out_dir, fname)
            crop.save(fpath, "PNG")
            print(f"  saved  {fpath}  ({crop.width}×{crop.height})")

            # CSS clip-path values (relative to full source image)
            css_polygon = "polygon(" + ", ".join(
                f"{px/self.orig_w*100:.2f}% {py/self.orig_h*100:.2f}%"
                for px, py in pts) + ")"
            css_inset = (
                f"inset({b['y1']/self.orig_h*100:.2f}% "
                f"{(self.orig_w-b['x2'])/self.orig_w*100:.2f}% "
                f"{(self.orig_h-b['y2'])/self.orig_h*100:.2f}% "
                f"{b['x1']/self.orig_w*100:.2f}%)"
            )

            parts_data.append({
                "name":   ann["name"],
                "type":   ann["type"],
                "file":   fname,
                "bbox":   {
                    "x1": b["x1"], "y1": b["y1"],
                    "x2": b["x2"], "y2": b["y2"],
                    "width":  b["x2"] - b["x1"],
                    "height": b["y2"] - b["y1"],
                },
                "points": ann["points"],
                "pct": {
                    "left":   round(b["x1"] / self.orig_w * 100, 2),
                    "top":    round(b["y1"] / self.orig_h * 100, 2),
                    "right":  round(b["x2"] / self.orig_w * 100, 2),
                    "bottom": round(b["y2"] / self.orig_h * 100, 2),
                },
                "css_inset":   css_inset,
                "css_polygon": css_polygon,
            })

        json_path = self._json_path(out_dir)
        with open(json_path, "w") as f:
            json.dump({
                "source_image":  os.path.basename(self.image_path),
                "source_width":  self.orig_w,
                "source_height": self.orig_h,
                "parts": parts_data,
            }, f, indent=2)
        print(f"  saved  {json_path}")

        messagebox.showinfo(
            "Saved!",
            f"Saved {len(parts_data)} region(s) to:\n{out_dir}\n\n"
            + "\n".join(p["file"] for p in parts_data)
            + "\nannotations.json")

    # ── Load ─────────────────────────────────────────────────────────────────
    def _load_json_dialog(self):
        path = filedialog.askopenfilename(
            title="Load annotations.json",
            filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if path:
            self._load_json_file(path)

    def _load_json_file(self, path: str):
        with open(path) as f:
            data = json.load(f)

        for part in data.get("parts", []):
            colour = COLOURS[len(self.annotations) % len(COLOURS)]
            pts    = part.get("points", [])
            b      = part["bbox"]

            if part.get("type") == "polygon":
                disp_pts = [(int(p[0]*self.scale), int(p[1]*self.scale))
                            for p in pts]
                flat   = [c for pt in disp_pts for c in pt]
                pid    = self.canvas.create_polygon(
                    *flat, outline=colour, fill=colour,
                    stipple="gray25", width=2)
                xs = [p[0] for p in disp_pts]
                ys = [p[1] for p in disp_pts]
                lid = self.canvas.create_text(
                    min(xs)+4, min(ys)+4, anchor=tk.NW,
                    text=part["name"], fill=colour,
                    font=("Arial", 10, "bold"))
                cids = [pid, lid]
            else:
                sx1 = int(b["x1"] * self.scale)
                sy1 = int(b["y1"] * self.scale)
                sx2 = int(b["x2"] * self.scale)
                sy2 = int(b["y2"] * self.scale)
                rid = self.canvas.create_rectangle(
                    sx1, sy1, sx2, sy2, outline=colour, width=2)
                lid = self.canvas.create_text(
                    sx1+4, sy1+4, anchor=tk.NW,
                    text=part["name"], fill=colour,
                    font=("Arial", 10, "bold"))
                cids = [rid, lid]

            ann = dict(
                type       = part.get("type", "rect"),
                name       = part["name"],
                canvas_ids = cids,
                colour     = colour,
                bbox       = b,
                points     = pts,
            )
            self._add_annotation(ann)

        print(f"Loaded {len(data.get('parts',[]))} annotation(s) from {path}")

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _json_path(self, directory: str | None = None) -> str:
        if directory is None:
            directory = os.path.join(
                os.path.dirname(os.path.abspath(self.image_path)), "parts")
        return os.path.join(directory, "annotations.json")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    root = tk.Tk()
    root.withdraw()

    image_path = sys.argv[1] if len(sys.argv) > 1 else filedialog.askopenfilename(
        title="Select logo image",
        filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.bmp"),
                   ("All files", "*.*")])

    if not image_path:
        root.destroy()
        return

    if not os.path.exists(image_path):
        messagebox.showerror("File not found", f"Cannot find:\n{image_path}")
        root.destroy()
        return

    root.deiconify()
    LogoAnnotator(root, image_path)
    root.mainloop()


if __name__ == "__main__":
    main()
