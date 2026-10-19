"""Web favicon from REFERENCES/as-logo.png (same mark as the launcher).

Writes multi-size ``mobile/web/favicon.ico`` (16/32/48/64) plus
``mobile/assets/logo/favicon_from_ref.png`` for reuse.

Run from repo root:  backend\\.venv\\Scripts\\python.exe mobile\\tool\\gen_favicon_from_ref.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "REFERENCES" / "as-logo.png"
OUT_ICO = ROOT / "mobile" / "web" / "favicon.ico"
OUT_PNG = ROOT / "mobile" / "assets" / "logo" / "favicon_from_ref.png"


def main() -> None:
    ref = Image.open(SRC).convert("RGBA")
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64)]
    OUT_ICO.parent.mkdir(parents=True, exist_ok=True)
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    ref.save(OUT_PNG)
    ref.save(OUT_ICO, format="ICO", sizes=sizes)
    print(OUT_ICO)
    print(OUT_PNG)


if __name__ == "__main__":
    main()
