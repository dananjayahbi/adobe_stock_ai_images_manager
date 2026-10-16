"""Generates the AI Stock Studio app icon set, palette-matched to tokens.dart.

Concept: a faceted studio aperture (iris) in cream on deep warm ink, with a
brass AI sparkle — the "studio" lens plus the "AI" glint.

Outputs (mobile/assets/logo/):
  app_icon_1024.png     full-bleed icon (legacy mipmaps, favicon source)
  app_icon_fg_1024.png  transparent adaptive foreground (ink900 backdrop)
  favicon.ico           16/32/48 multi-size web icon

Run from repo root:
  backend/.venv/Scripts/python.exe mobile/tool/gen_logo.py
"""
import math
import os

from PIL import Image, ImageDraw

SS = 2                      # supersample factor for antialiasing
SIZE = 1024
S = SIZE * SS

# tokens.dart palette
INK900 = (0x17, 0x11, 0x0A)
INK_CORE = (0x2B, 0x20, 0x13)   # vignette center (warm core)
CREAM = (0xEE, 0xE3, 0xCC)      # ink800
CREAM_DIM = (0xD8, 0xC9, 0xAE)  # ink200
BRASS = (0xCB, 0xA8, 0x57)      # brass400

# Composition (1024-space). Every extremity must stay inside the
# adaptive-icon safe zone: circle r=338 centered at (512, 512).
AP_X, AP_Y = 455, 560           # aperture center
AP_R = 230                      # blade disc radius
HOLE_R = 82                     # inner hexagon hole
RING_W = 20
BRASS_HEX = 46
STARS = [(685, 315, 85), (755, 440, 45)]  # (x, y, radius)
SEAM_W = 10


def polar(cx, cy, r, deg):
    a = math.radians(deg)
    return (cx + r * math.cos(a), cy + r * math.sin(a))


def star(draw, cx, cy, size, fill):
    """Concave 4-point sparkle."""
    k = int(size * 0.17)
    pts = [
        (cx, cy - size), (cx + k, cy - k),
        (cx + size, cy), (cx + k, cy + k),
        (cx, cy + size), (cx - k, cy + k),
        (cx - size, cy), (cx - k, cy - k),
    ]
    draw.polygon(pts, fill=fill)


def aperture(draw, punch):
    """Faceted 6-blade iris + barrel ring. `punch` = hole/seam color."""
    # Everything below is in supersampled pixels (composition is 1024-space).
    cx, cy = AP_X * SS, AP_Y * SS
    r = AP_R * SS
    hole_r = HOLE_R * SS
    box = [cx - r, cy - r, cx + r, cy + r]
    for k in range(6):
        draw.pieslice(
            box,
            start=-90 + k * 60,
            end=-90 + (k + 1) * 60,
            fill=CREAM if k % 2 == 0 else CREAM_DIM,
        )
    seam = SEAM_W * SS
    for k in range(6):
        ex, ey = polar(cx, cy, r, -90 + k * 60)
        draw.line([cx, cy, ex, ey], fill=punch, width=seam)
    hole = [polar(cx, cy, hole_r, k * 60) for k in range(6)]
    draw.polygon(hole, fill=punch)
    core = [polar(cx, cy, BRASS_HEX * SS, k * 60) for k in range(6)]
    draw.polygon(core, fill=BRASS)
    # Barrel ring overlaps the disc edge — no seam gap.
    rw = RING_W * SS
    r_out = r + int(rw * 0.75)
    draw.ellipse(
        [cx - r_out, cy - r_out, cx + r_out, cy + r_out],
        outline=CREAM,
        width=rw,
    )


def compose(foreground):
    """One 1024 icon. foreground=True -> transparent bg (adaptive layer)."""
    if foreground:
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    else:
        # Warm radial vignette: lighter core behind the mark.
        # radial_gradient is 0 at center / 255 at corners → swap args.
        grad = Image.radial_gradient("L").resize((S, S))
        core = Image.new("RGBA", (S, S), INK_CORE + (255,))
        edge = Image.new("RGBA", (S, S), INK900 + (255,))
        img = Image.composite(edge, core, grad)
    draw = ImageDraw.Draw(img)
    punch = INK900 if not foreground else (0, 0, 0, 0)
    aperture(draw, punch)
    for x, y, size in STARS:
        star(draw, x * SS, y * SS, size * SS, BRASS)
        star(draw, x * SS, y * SS, int(size * SS * 0.42), CREAM)
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
