"""Thumbnails must never be served with implicit (heuristic) caching.

The bg-removal step rewrites ``thumb_{id}.png`` under the *same* filename, so a
cached copy silently shows the pre-removal image until a manual reload.
"""


def test_thumbnails_response_requires_revalidation(client):
    """Any /thumbnails response must carry an explicit no-cache directive."""
    response = client.get("/thumbnails/thumb_does_not_exist.png")
    # 404 is fine — the contract under test is the *header*, not the body.
    assert response.headers.get("cache-control") == "no-cache"


def test_api_responses_do_not_inherit_thumbnail_header(client):
    """The middleware must be scoped to /thumbnails only."""
    response = client.get("/api/records?limit=1")
    assert "no-cache" not in (response.headers.get("cache-control") or "")
