"""Build launcher icon assets from REFERENCES/as-logo.png.

The hand-drawn reference (transparent 500x500 RGBA) becomes:

* ``app_icon_ref_1024.png``      - legacy icon: logo framing kept, the
  transparent margin filled with the square's own dark color so the icon
  reads as one solid tile.
* ``app_icon_ref_fg_1024.png``   - adaptive foreground: alpha-cropped logo
  scaled into the 66% safe zone on a fully transparent 1024 canvas; the
  launcher paints ``adaptive_icon_background`` underneath.

Run from repo root:  backend\\.venv\\Scripts\\python.exe mobile\\tool\\gen_logo_from_ref.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "REFERENCES" / "as-logo.png"
OUT_DIR = ROOT / "mobile" / "assets" / "logo"

CANVAS = 1024
LEGACY_FRAME = 0.81  # content square / canvas — matches the reference framing
SAFE_ZONE = 0.66  # adaptive-icon inner safe zone (fraction of canvas)


def _sample_bg(content: Image.Image) -> tuple[int, int, int]:
    """Solid dark tone from inside the rounded square, away from the glyph."""
    px = content.load()
    x = int(content.width * 0.12)
    y = int(content.height * 0.5)
    r, g, b, _ = px[x, y]
    return r, g, b


def main() -> None:
    ref = Image.open(SRC).convert("RGBA")
    # Alpha bbox: the rounded square itself, without the transparent margin.
    bbox = ref.getbbox()
    if bbox is None:
        raise SystemExit("reference logo is empty")
    content = ref.crop(bbox)

    r, g, b = _sample_bg(content)
    bg = (r, g, b, 255)
    hex_color = f"#{r:02X}{g:02X}{b:02X}"

    # Legacy icon: original framing on the dark tile color.
    legacy = Image.new("RGBA", (CANVAS, CANVAS), bg)
    side = int(CANVAS * LEGACY_FRAME)
    legacy_content = content.resize((side, side), Image.LANCZOS)
    legacy.paste(legacy_content,
                 ((CANVAS - side) // 2, (CANVAS - side) // 2),
                 legacy_content.getchannel("A"))

    # Adaptive foreground: transparent canvas, content inside the safe zone.
    fg = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    safe = int(CANVAS * SAFE_ZONE)
    resized = content.resize((safe, safe), Image.LANCZOS)
    fg.paste(resized, ((CANVAS - safe) // 2, (CANVAS - safe) // 2), resized.getchannel("A"))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    legacy_path = OUT_DIR / "app_icon_ref_1024.png"
    fg_path = OUT_DIR / "app_icon_ref_fg_1024.png"
    legacy.save(legacy_path)
    fg.save(fg_path)
    print(f"bg {hex_color}")
    print(legacy_path)
    print(fg_path)


if __name__ == "__main__":
    main()
