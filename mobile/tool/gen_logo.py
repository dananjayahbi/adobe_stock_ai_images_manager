"""Generates the AI Stock Studio app icon set, palette-matched to tokens.dart.

Concept: one minimal mark — a rounded-square frame (the studio/picture)
holding a single brass spark (the AI), centered with generous negative space.

Outputs (mobile/assets/logo/):
  app_icon_1024.png     full-bleed icon (legacy mipmaps, favicon source)
  app_icon_fg_1024.png  transparent adaptive foreground (ink900 backdrop)
  favicon.ico           16/32/48 multi-size web icon

Run from repo root:
  backend/.venv/Scripts/python.exe mobile/tool/gen_logo.py
"""
import os

from PIL import Image, ImageDraw

SS = 2                      # supersample factor for antialiasing
SIZE = 1024
S = SIZE * SS

# tokens.dart palette
INK900 = (0x17, 0x11, 0x0A)
CREAM = (0xEE, 0xE3, 0xCC)      # ink800
BRASS = (0xCB, 0xA8, 0x57)      # brass400

# Composition (1024-space). Every extremity must stay inside the
# adaptive-icon safe zone: circle r=338 centered at (512, 512).
# Outer frame corner distance: sqrt(2)*(250-100)+100 = 312 < 338.
FRAME_H = 250                # frame outer half-size
FRAME_R = 100                # frame outer corner radius
FRAME_W = 46                 # frame stroke width
SPARK_R = 122                # spark tip distance from center
SPARK_WAIST = 0.32           # concave waist factor (chunkier = readable small)


def star(draw, cx, cy, size, fill, waist=0.17):
    """Concave 4-point sparkle."""
    k = int(size * waist)
    pts = [
        (cx, cy - size), (cx + k, cy - k),
        (cx + size, cy), (cx + k, cy + k),
        (cx, cy + size), (cx - k, cy + k),
        (cx - size, cy), (cx - k, cy - k),
    ]
    draw.polygon(pts, fill=fill)


def mark(draw, punch):
    """Rounded-square frame + one brass spark. `punch` = window color."""
    # Everything below is in supersampled pixels (composition is 1024-space).
    cx = cy = 512 * SS
    h = FRAME_H * SS
    r = FRAME_R * SS
    w = FRAME_W * SS
    # Frame: filled rounded square, then punch out the inner window.
    draw.rounded_rectangle([cx - h, cy - h, cx + h, cy + h], radius=r, fill=CREAM)
    ih = h - w
    ir = max(r - w, 1)
    draw.rounded_rectangle(
        [cx - ih, cy - ih, cx + ih, cy + ih], radius=ir, fill=punch
    )
    # Single centered AI spark.
    star(draw, cx, cy, SPARK_R * SS, BRASS, waist=SPARK_WAIST)


def compose(foreground):
    """One 1024 icon. foreground=True -> transparent bg (adaptive layer)."""
    if foreground:
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        punch = (0, 0, 0, 0)
    else:
        img = Image.new("RGBA", (S, S), INK900 + (255,))
        punch = INK900 + (255,)
    draw = ImageDraw.Draw(img)
    mark(draw, punch)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "logo")
    os.makedirs(out_dir, exist_ok=True)

    full = compose(foreground=False)
    full.save(os.path.join(out_dir, "app_icon_1024.png"))

    fg = compose(foreground=True)
    fg.save(os.path.join(out_dir, "app_icon_fg_1024.png"))

    favicon = full.resize((48, 48), Image.LANCZOS)
    favicon.save(
        os.path.join(out_dir, "favicon.ico"),
        sizes=[(16, 16), (32, 32), (48, 48)],
    )
    print("wrote app_icon_1024.png, app_icon_fg_1024.png, favicon.ico")


if __name__ == "__main__":
    main()
