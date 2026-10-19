"""Tests for the source-folder browse APIs (``/api/fs``).

Root/list/thumb happy paths, the shared containment guards (400 unconfigured,
403 escape, 404 missing), and the response contracts: image-extension-only
listings sorted case-insensitively, JPEG thumbnails behind a private cache
header.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from tests.test_batch_pipeline import _jpg_bytes, _png_bytes


@pytest.fixture()
def fs_root(client, tmp_path):
    """A configured source folder: subdirs, images (incl. case oddities), decoy."""
    root = tmp_path / "source"
    (root / "Zebra").mkdir(parents=True)
    (root / "apple").mkdir()
    (root / "photo.jpg").write_bytes(_jpg_bytes((800, 600)))
    (root / "B.jpg").write_bytes(_jpg_bytes((64, 64)))
    (root / "a.jpg").write_bytes(_jpg_bytes((64, 64)))
    (root / "cut.PNG").write_bytes(_png_bytes())
    (root / "notes.txt").write_bytes(b"not an image")
    (root / "archive.zip").write_bytes(b"PK")
    (root / "sub").mkdir()
    (root / "sub" / "deep").mkdir()
    (root / "sub" / "deep" / "leaf.jpg").write_bytes(_jpg_bytes((64, 64)))

    response = client.put("/api/settings", json={"source_folder": str(root)})
    assert response.status_code == 200, response.text
    return root


# --------------------------------------------------------------------------- #
# GET /api/fs/root
# --------------------------------------------------------------------------- #

class TestFsRoot:
    def test_unconfigured_reports_false(self, client):
        assert client.get("/api/fs/root").json() == {
            "configured": False,
            "path": None,
            "exists": False,
        }

    def test_configured_and_existing(self, client, fs_root):
        body = client.get("/api/fs/root").json()
        assert body == {"configured": True, "path": str(fs_root), "exists": True}

    def test_configured_but_missing_directory(self, client, tmp_path):
        gone = tmp_path / "not-created"
        client.put("/api/settings", json={"source_folder": str(gone)})
        body = client.get("/api/fs/root").json()
        assert body == {"configured": True, "path": str(gone), "exists": False}


# --------------------------------------------------------------------------- #
# GET /api/fs/list
# --------------------------------------------------------------------------- #

class TestFsList:
    def test_root_lists_dirs_and_image_files_sorted(
        self, client, fs_root
    ):
        body = client.get("/api/fs/list").json()
        assert body["path"] == ""
        assert body["segments"] == []
        assert body["parent"] is None
        # Case-insensitive ascending: "apple" before "Zebra" (ASCII sort would
        # flip them), "a.jpg" before "B.jpg"; ".PNG" counts as an image too.
        assert [d["name"] for d in body["dirs"]] == ["apple", "sub", "Zebra"]
        assert [f["name"] for f in body["files"]] == [
            "a.jpg",
            "B.jpg",
            "cut.PNG",
            "photo.jpg",
        ]

    def test_non_image_files_are_filtered_out(self, client, fs_root):
        names = [f["name"] for f in client.get("/api/fs/list").json()["files"]]
        assert "notes.txt" not in names
        assert "archive.zip" not in names

    def test_file_entries_carry_size_and_mtime(self, client, fs_root):
        files = client.get("/api/fs/list").json()["files"]
        photo = next(f for f in files if f["name"] == "photo.jpg")
        assert set(photo) == {"name", "size", "mtime"}
        assert photo["size"] == (fs_root / "photo.jpg").stat().st_size
        assert photo["mtime"] == pytest.approx(
            (fs_root / "photo.jpg").stat().st_mtime
        )

    def test_subdirectory_path_segments_and_parent(self, client, fs_root):
        body = client.get("/api/fs/list", params={"path": "sub/deep"}).json()
        assert body["path"] == "sub/deep"
        assert body["parent"] == "sub"
        assert body["segments"] == [
            {"name": "sub", "path": "sub"},
            {"name": "deep", "path": "sub/deep"},
        ]
        assert [f["name"] for f in body["files"]] == ["leaf.jpg"]

    def test_immediate_child_parent_is_the_root(self, client, fs_root):
        body = client.get("/api/fs/list", params={"path": "sub"}).json()
        assert body["parent"] == ""  # "" is the root relative path, not null
        assert body["segments"] == [{"name": "sub", "path": "sub"}]

    def test_unconfigured_is_400(self, client):
        response = client.get("/api/fs/list")
        assert response.status_code == 400
        assert "source folder" in response.json()["detail"].lower()

    def test_escape_is_403(self, client, fs_root):
        response = client.get("/api/fs/list", params={"path": "../.."})
        assert response.status_code == 403
        assert "escape" in response.json()["detail"].lower()

    def test_missing_directory_is_404(self, client, fs_root):
        response = client.get("/api/fs/list", params={"path": "ghost"})
        assert response.status_code == 404

    def test_a_file_path_is_not_a_directory(self, client, fs_root):
        response = client.get("/api/fs/list", params={"path": "photo.jpg"})
        assert response.status_code == 400
        assert "directory" in response.json()["detail"].lower()


# --------------------------------------------------------------------------- #
# GET /api/fs/thumb
# --------------------------------------------------------------------------- #

class TestFsThumb:
    def test_returns_a_cached_jpeg(self, client, fs_root):
        response = client.get("/api/fs/thumb", params={"path": "photo.jpg"})
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("image/jpeg")
        assert "private, max-age=3600" in response.headers["cache-control"]
        assert response.content[:2] == b"\xff\xd8"  # JPEG magic

        with Image.open(io.BytesIO(response.content)) as img:
            assert img.format == "JPEG"
            # 800x600 source -> long edge capped at 512, aspect kept.
            assert max(img.size) == 512
            assert img.size == (512, 384)

    def test_png_thumb_is_served_as_jpeg(self, client, fs_root):
        response = client.get("/api/fs/thumb", params={"path": "cut.PNG"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/jpeg")

    def test_unconfigured_is_400(self, client):
        response = client.get("/api/fs/thumb", params={"path": "photo.jpg"})
        assert response.status_code == 400

    def test_escape_is_403(self, client, fs_root, tmp_path):
        (tmp_path / "secret.jpg").write_bytes(_jpg_bytes())
        response = client.get(
            "/api/fs/thumb", params={"path": "../secret.jpg"}
        )
        assert response.status_code == 403

    def test_missing_image_is_404(self, client, fs_root):
        response = client.get("/api/fs/thumb", params={"path": "ghost.jpg"})
        assert response.status_code == 404

    def test_non_image_extension_is_400_and_never_served(self, client, fs_root):
        response = client.get("/api/fs/thumb", params={"path": "notes.txt"})
        assert response.status_code == 400
        assert "extension" in response.json()["detail"].lower()
        assert "text" not in response.headers.get("content-type", "")


# --------------------------------------------------------------------------- #
# Auth — the global middleware covers /api/fs like every other API router
# --------------------------------------------------------------------------- #

def test_fs_endpoints_require_a_session_cookie(client, monkeypatch):
    from auth_config import auth_settings

    monkeypatch.setattr(auth_settings, "AUTH_ENABLED", True)
    for path in ("/api/fs/root", "/api/fs/list", "/api/fs/thumb?path=x.jpg"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json() == {"detail": "Not authenticated"}
