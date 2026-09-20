"""API tests for the auto-fix endpoint.

The endpoint is what the inspection modal's "Auto-fix & re-check" button calls,
so these tests pin the response contract the UI renders: the two score/verdict
pairs, the refreshed record, and the three issue buckets.
"""

import numpy as np
import pytest
from PIL import Image

from models import ImageRecord, ImageStatus, PipelineStage


@pytest.fixture()
def saturated_record(db_session_factory, tmp_path):
    """Persist a record whose file is saturated, untagged, and below threshold."""
    source = tmp_path / "saturated.jpg"
    image = np.zeros((200, 300, 3), dtype="uint8")
    image[:, :150] = (255, 0, 0)
    image[:, 150:] = (0, 255, 0)
    Image.fromarray(image).save(str(source), "JPEG", quality=95)

    session = db_session_factory()
    record = ImageRecord(
        filename="saturated.jpg",
        original_path=str(source),
        status=ImageStatus.FLAGGED,
        stage=PipelineStage.INCOMPATIBLE,
        file_size_bytes=source.stat().st_size,
    )
    session.add(record)
    session.commit()
    record_id = record.id
    session.close()
    return record_id


def test_autofix_returns_the_full_contract(client, saturated_record):
    response = client.post(f"/api/records/{saturated_record}/autofix")

    assert response.status_code == 200, response.text
    body = response.json()

    for field in (
        "record_id",
        "fixed",
        "remaining_fixable",
        "manual",
        "passes",
        "initial_score",
        "final_score",
        "improved",
        "initial_passed",
        "final_passed",
        "srgb_embedded",
        "history",
        "summary",
        "record",
    ):
        assert field in body, f"missing {field}"

    assert body["record_id"] == saturated_record
    assert body["record"]["id"] == saturated_record
    assert body["summary"]


def test_autofix_embeds_an_srgb_profile(client, saturated_record):
    """The corrected file must be verifiably tagged, not merely claimed."""
    body = client.post(f"/api/records/{saturated_record}/autofix").json()

    assert body["srgb_embedded"] is True
    # NOT_SRGB is a container fix, so it must be reported as fixable - it used to
    # be classed manual-only, which hid the very fix this endpoint performs.
    assert "not_srgb" not in body["manual"]


def test_autofix_persists_the_new_score_and_report(client, saturated_record):
    body = client.post(f"/api/records/{saturated_record}/autofix").json()

    listed = client.get("/api/records").json()["items"]
    record = next(item for item in listed if item["id"] == saturated_record)

    # The persisted score column keeps 4 decimals, so compare at that precision
    # rather than to the full float the response carries.
    assert record["acceptance_score"] == pytest.approx(body["final_score"], abs=1e-4)
    assert record["acceptance_report"] is not None
    assert record["working_path"]
    assert record["stage_details"]["autofix"]["final_score"] == pytest.approx(
        body["final_score"], abs=1e-4
    )


def test_autofix_rejects_an_unknown_variant(client, saturated_record):
    response = client.post(
        f"/api/records/{saturated_record}/autofix", params={"variant": "nope"}
    )
    assert response.status_code == 400
    assert "variant" in response.json()["detail"].lower()


def test_autofix_unknown_record_returns_404(client):
    response = client.post("/api/records/does-not-exist/autofix")
    assert response.status_code == 404


def test_autofix_does_not_move_the_record_between_stages(client, saturated_record):
    """An auto-fix is a correction attempt, not a pipeline transition.

    Moving the record would silently promote an image the operator has not
    reviewed, and would make the "re-run the compatibility check" decision for
    them. Checked for both modes.
    """
    for mode in ("single", "adaptive"):
        before = client.get("/api/records").json()["items"]
        record_before = next(r for r in before if r["id"] == saturated_record)

        response = client.post(
            f"/api/records/{saturated_record}/autofix", params={"mode": mode}
        )
        assert response.status_code == 200, response.text

        after = client.get("/api/records").json()["items"]
        record_after = next(r for r in after if r["id"] == saturated_record)

        assert record_after["stage"] == record_before["stage"], (
            f"{mode} mode changed the stage"
        )
        assert record_after["queued_stage"] == record_before["queued_stage"], (
            f"{mode} mode changed the queue"
        )


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #

def test_single_mode_is_the_default(client, saturated_record):
    body = client.post(f"/api/records/{saturated_record}/autofix").json()
    assert body["mode"] == "single"
    # Single mode has no loop, so no target and no log.
    assert body["log"] == []
    assert body["target"] is None
    assert body["stop_reason"] == ""


def test_adaptive_mode_returns_the_log_and_target(client, saturated_record):
    response = client.post(
        f"/api/records/{saturated_record}/autofix",
        params={"mode": "adaptive", "target": 0.8},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["mode"] == "adaptive"
    assert body["target"] == pytest.approx(0.8)
    assert body["log"], "adaptive mode must always return a decision log"
    assert body["stop_reason"], "adaptive mode must explain why it stopped"
    assert body["progress_before"] is not None
    assert body["progress_after"] is not None
    assert body["progress_after"]["dimensions"]

    for entry in body["log"]:
        assert set(entry) == {"level", "message", "pass", "score"}


def test_adaptive_target_is_clamped_server_side(client, saturated_record):
    body = client.post(
        f"/api/records/{saturated_record}/autofix",
        params={"mode": "adaptive", "target": 0.01},
    ).json()
    assert body["target"] == pytest.approx(0.6)


def test_adaptive_never_reports_a_worse_score(client, saturated_record):
    body = client.post(
        f"/api/records/{saturated_record}/autofix",
        params={"mode": "adaptive", "target": 0.95},
    ).json()
    assert body["final_score"] >= body["initial_score"]


def test_autofix_rejects_an_unknown_mode(client, saturated_record):
    response = client.post(
        f"/api/records/{saturated_record}/autofix", params={"mode": "turbo"}
    )
    assert response.status_code == 400
    assert "mode" in response.json()["detail"].lower()
