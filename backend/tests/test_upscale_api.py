"""API-level tests for the Stage 3 upscale configuration endpoints.

These cover the contract the panel depends on: a catalog the picker can render
from, defaults that already match the configured GPU/capacity, and an estimator
that answers before the user commits to a multi-minute run.
"""

import pytest

from services.upscale import catalog


@pytest.fixture(autouse=True)
def _clear_catalog_cache():
    catalog.clear_cache()
    yield
    catalog.clear_cache()


# --------------------------------------------------------------------------- #
# GET /api/upscale/catalog
# --------------------------------------------------------------------------- #


def test_catalog_endpoint_returns_the_picker_payload(client):
    response = client.get("/api/upscale/catalog")

    assert response.status_code == 200
    body = response.json()
    assert body["models"], "the real models must be discovered"
    assert body["default_model"]
    assert body["neural_available"] is True


def test_catalog_endpoint_lists_every_capacity_preset(client):
    body = client.get("/api/upscale/catalog").json()

    assert [preset["long_edge"] for preset in body["resolutions"]] == [
        2560,
        3840,
        5120,
        6144,
        7680,
    ]


def test_catalog_endpoint_marks_the_configured_capacity(client):
    body = client.get("/api/upscale/catalog").json()

    default = [p for p in body["resolutions"] if p["default"]]
    assert len(default) == 1
    assert default[0]["long_edge"] == 3840


def test_catalog_endpoint_defaults_to_gpu_zero(client):
    body = client.get("/api/upscale/catalog").json()

    # GPU 0 is the dedicated card on this machine; integrated adapters follow.
    assert body["defaults"]["gpu_id"] == 0
    assert body["defaults"]["target_long_edge"] == 3840
    assert body["defaults"]["tta"] is False


def test_catalog_endpoint_forces_jpeg(client):
    body = client.get("/api/upscale/catalog").json()

    assert body["presets"]["forced_format"] == "jpg"


def test_catalog_endpoint_reports_the_binary_it_will_use(client):
    body = client.get("/api/upscale/catalog").json()

    assert body["executable"]
    assert body["executable"].lower().endswith("upscayl-bin.exe")


def test_catalog_endpoint_accepts_a_refresh(client):
    assert client.get("/api/upscale/catalog?refresh=true").status_code == 200


def test_catalog_endpoint_serialises_models_for_the_ui(client):
    body = client.get("/api/upscale/catalog").json()

    first = body["models"][0]
    assert set(first) >= {"name", "label", "scale", "source", "recommended"}
    assert first["scale"] in (2, 3, 4)


def test_catalog_endpoint_groups_models_by_source(client):
    body = client.get("/api/upscale/catalog").json()

    sources = {model["source"] for model in body["models"]}
    assert sources <= {"bundled", "outsourced", "custom"}
    assert "bundled" in sources


# --------------------------------------------------------------------------- #
# GET /api/upscale/options
# --------------------------------------------------------------------------- #


def test_options_endpoint_returns_ready_to_use_options(client):
    body = client.get("/api/upscale/options").json()

    assert body["model"]
    assert body["model_scale"] in (2, 3, 4)
    assert body["target_long_edge"] == 3840
    assert body["format"] == "jpg"
    assert body["threads"] == [1, 2, 2]


# --------------------------------------------------------------------------- #
# POST /api/upscale/estimate
# --------------------------------------------------------------------------- #


def test_estimate_endpoint_projects_the_output_size(client):
    response = client.post(
        "/api/upscale/estimate",
        json={"width": 896, "height": 1200, "upscale": {"target_long_edge": 3840}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["will_upscale"] is True
    assert max(body["target_dimensions"]) == 3840
    assert body["estimated_megapixels"] > 0


def test_estimate_endpoint_uses_the_defaults_when_no_options_are_sent(client):
    response = client.post("/api/upscale/estimate", json={"width": 896, "height": 1200})

    assert response.status_code == 200
    assert response.json()["model_scale"] in (2, 3, 4)


def test_estimate_endpoint_warns_before_a_pointless_upscale(client):
    response = client.post(
        "/api/upscale/estimate",
        json={"width": 4000, "height": 5000, "upscale": {"target_long_edge": 3840}},
    )

    body = response.json()
    assert body["will_upscale"] is False
    assert body["warnings"], "the panel needs something to warn about"


def test_estimate_endpoint_rejects_a_request_without_dimensions(client):
    response = client.post("/api/upscale/estimate", json={})

    assert response.status_code == 400


def test_estimate_endpoint_measures_a_stored_record(client, sample_jpeg):
    source = sample_jpeg(640, 480, name="measured.jpg")

    upload = client.post(
        "/upload",
        files={"files": ("measured.jpg", source.read_bytes(), "image/jpeg")},
    )
    record_id = upload.json()["record_ids"][0]

    response = client.post(
        "/api/upscale/estimate", json={"record_id": record_id, "upscale": {}}
    )

    assert response.status_code == 200
    assert response.json()["source_dimensions"] == [640, 480]


def test_estimate_endpoint_404s_for_an_unknown_record(client):
    response = client.post("/api/upscale/estimate", json={"record_id": "nope"})

    assert response.status_code == 404


def test_estimate_endpoint_rejects_a_record_without_a_readable_file(client, sample_jpeg):
    source = sample_jpeg(320, 240, name="vanishing.jpg")
    upload = client.post(
        "/upload", files={"files": ("vanishing.jpg", source.read_bytes(), "image/jpeg")}
    )
    record_id = upload.json()["record_ids"][0]

    from config import settings

    # Uploads are stored under a generated name, so delete whatever landed.
    stored = next(settings.INBOX_DIR.iterdir())
    stored.unlink()

    response = client.post("/api/upscale/estimate", json={"record_id": record_id})

    # The panel must not be able to promise an output it cannot produce.
    assert response.status_code == 422


def test_estimate_endpoint_flags_an_over_ceiling_output(client):
    response = client.post(
        "/api/upscale/estimate",
        json={"width": 11000, "height": 10000, "upscale": {"target_long_edge": 12000}},
    )

    body = response.json()
    assert body["exceeds_megapixel_ceiling"] is True
