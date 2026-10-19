"""Platform catalogue API + per-platform storage/DB isolation.

HTTP assertions use the shared ``client`` fixture (auth disabled).  The
storage/DB isolation tests patch ``platforms.paths.PLATFORMS_ROOT`` — the
module-level binding ``platforms.paths`` actually reads (the module does
``from config import PLATFORMS_ROOT`` at import time), so nothing here ever
touches the real ``storage`` tree.

Engine-caching note: ``database._PLATFORM_ENGINES`` is module-level and lives
for the whole pytest run, so exactly ONE test here ever asks for the
freepik/vecteezy engines (and it pops them from the cache on teardown);
every other assertion uses stateless path helpers or the adobe default.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect as sqlalchemy_inspect

import database
import platforms.paths as paths
from platforms.paths import (
    STANDARD_SUBDIRS,
    get_platform_paths,
    platform_db_path,
    platform_root,
)

#: The contract table: (id, route, status) in display order.
EXPECTED_CATALOGUE = [
    ("adobe_stock", "/adobe-stock", "available"),
    ("freepik", "/freepik", "coming_soon"),
    ("vecteezy", "/vecteezy", "coming_soon"),
    ("dreamstime", "/dreamstime", "coming_soon"),
    ("123rf", "/123rf", "coming_soon"),
    ("wirestock", "/wirestock", "coming_soon"),
]

ENTRY_KEYS = {"id", "name", "tagline", "status", "route"}


# ---------------------------------------------------------------------------
# HTTP: the catalogue endpoints
# ---------------------------------------------------------------------------


def test_list_platforms_returns_full_catalogue(client):
    """GET /api/platforms -> 200 with exactly the 6 catalogued platforms."""
    response = client.get("/api/platforms")
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 6
    for entry, (pid, route, status) in zip(entries, EXPECTED_CATALOGUE):
        assert set(entry) == ENTRY_KEYS
        assert entry["id"] == pid
        assert entry["route"] == route
        assert entry["status"] == status
        assert entry["name"]
        assert entry["tagline"]


def test_list_platforms_answers_without_trailing_slash(client):
    """GET /api/platforms without the trailing slash serves directly (B2)."""
    response = client.get("/api/platforms", follow_redirects=False)
    assert response.status_code == 200
    assert "location" not in response.headers
    assert response.json() == client.get("/api/platforms/").json()


def test_get_single_platform_adobe_and_freepik(client):
    """Detail endpoint mirrors the list entry; freepik is coming_soon."""
    listing = client.get("/api/platforms")
    assert listing.status_code == 200

    adobe = client.get("/api/platforms/adobe_stock")
    assert adobe.status_code == 200
    entry = adobe.json()
    assert set(entry) == ENTRY_KEYS
    assert entry == listing.json()[0]

    freepik = client.get("/api/platforms/freepik")
    assert freepik.status_code == 200
    assert freepik.json()["status"] == "coming_soon"
    assert freepik.json()["route"] == "/freepik"


def test_unknown_platform_is_404(client):
    response = client.get("/api/platforms/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown platform"}


# ---------------------------------------------------------------------------
# Storage isolation (unit level, all on tmp_path)
# ---------------------------------------------------------------------------


def test_platform_roots_are_isolated(tmp_path, monkeypatch):
    """Each platform resolves its own root under the patched PLATFORMS_ROOT."""
    monkeypatch.setattr(paths, "PLATFORMS_ROOT", tmp_path)

    freepik_root = platform_root("freepik")
    vecteezy_root = platform_root("vecteezy")
    assert freepik_root != vecteezy_root
    assert freepik_root == tmp_path / "freepik"
    assert vecteezy_root == tmp_path / "vecteezy"
    assert freepik_root.is_relative_to(tmp_path)
    assert vecteezy_root.is_relative_to(tmp_path)
    assert platform_db_path("freepik") == freepik_root / "freepik.db"
    assert platform_db_path("freepik") != platform_db_path("vecteezy")


def test_get_platform_paths_creates_standard_layout(tmp_path, monkeypatch):
    """create=True builds every STANDARD_SUBDIR with distinct dir fields."""
    monkeypatch.setattr(paths, "PLATFORMS_ROOT", tmp_path)

    freepik = get_platform_paths("freepik", create=True)
    assert freepik.root == tmp_path / "freepik"
    for name in STANDARD_SUBDIRS:
        assert (freepik.root / name).is_dir()

    dir_fields = [
        freepik.inbox_dir,
        freepik.thumbnails_dir,
        freepik.ready_dir,
        freepik.refined_dir,
        freepik.upscaled_dir,
        freepik.converted_dir,
        freepik.removed_dir,
        freepik.white_dir,
        freepik.srgb_dir,
        freepik.quarantine_dir,
    ]
    assert len(dir_fields) == len(set(dir_fields)) == len(STANDARD_SUBDIRS)
    assert {d.name for d in dir_fields} == set(STANDARD_SUBDIRS)
    assert freepik.db_path == tmp_path / "freepik" / "freepik.db"
    # Path construction never creates the database file itself.
    assert not freepik.db_path.exists()

    # A second platform gets its own tree; freepik's create=True left no trace.
    vecteezy = get_platform_paths("vecteezy", create=False)
    assert vecteezy.root == tmp_path / "vecteezy"
    assert not vecteezy.inbox_dir.exists()
    assert vecteezy.db_path == tmp_path / "vecteezy" / "vecteezy.db"


def test_adobe_root_follows_adobe_stock_binding(tmp_path, monkeypatch):
    """adobe_stock resolves through ADOBE_STOCK_ROOT; others via PLATFORMS_ROOT.

    Both bindings are patched to tmp so the assertion documents the contract
    (root ends with platforms/adobe_stock) without touching real storage.
    """
    monkeypatch.setattr(paths, "PLATFORMS_ROOT", tmp_path / "platforms")
    monkeypatch.setattr(
        paths, "ADOBE_STOCK_ROOT", tmp_path / "platforms" / "adobe_stock"
    )

    adobe = get_platform_paths("adobe_stock", create=False)
    assert adobe.root == tmp_path / "platforms" / "adobe_stock"
    assert str(adobe.root).endswith(str(Path("platforms") / "adobe_stock"))
    assert adobe.db_path == tmp_path / "platforms" / "adobe_stock" / "adobe_stock.db"

    other = get_platform_paths("wirestock", create=False)
    assert other.root == tmp_path / "platforms" / "wirestock"
    assert other.root != adobe.root


# ---------------------------------------------------------------------------
# DB isolation (same tmp patch, engine cache aware)
# ---------------------------------------------------------------------------


def test_platform_engines_and_tables_are_isolated(tmp_path, monkeypatch):
    """Distinct engines/files per platform; adobe is the default engine."""
    monkeypatch.setattr(paths, "PLATFORMS_ROOT", tmp_path)
    # The engine assumes the platform root already exists (the documented
    # flow: get_platform_paths(create=True) first — routers/tasks/adapters
    # write immediately without a separate mkdir pass).
    get_platform_paths("freepik", create=True)
    get_platform_paths("vecteezy", create=True)

    try:
        freepik_engine = database.get_platform_engine("freepik")
        vecteezy_engine = database.get_platform_engine("vecteezy")

        assert freepik_engine is not vecteezy_engine
        # Same id -> same cached engine (cache semantics).
        assert database.get_platform_engine("freepik") is freepik_engine

        freepik_db = Path(freepik_engine.url.database)
        vecteezy_db = Path(vecteezy_engine.url.database)
        assert freepik_db != vecteezy_db
        assert freepik_db == tmp_path / "freepik" / "freepik.db"
        assert vecteezy_db == tmp_path / "vecteezy" / "vecteezy.db"
        assert str(freepik_db).startswith(str(tmp_path))
        assert str(vecteezy_db).startswith(str(tmp_path))

        database.init_platform_tables("freepik")
        assert freepik_db.is_file()
        # vecteezy was never initialized — no file, no tables.
        assert not vecteezy_db.exists()
        assert sqlalchemy_inspect(freepik_engine).has_table("image_records")
        assert not sqlalchemy_inspect(vecteezy_engine).has_table("image_records")

        # Adobe always resolves to the module-level default engine.
        assert database.get_platform_engine("adobe_stock") is database.engine
    finally:
        # Drop the cached engines so the module-level cache does not outlive
        # this test's tmp_path (and so no file handles pin the temp dirs).
        for platform_id in ("freepik", "vecteezy"):
            engine = database._PLATFORM_ENGINES.pop(platform_id, None)
            if engine is not None:
                engine.dispose()
