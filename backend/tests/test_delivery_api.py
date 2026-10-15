"""Tests for the Stage 6+ delivery layer: naming, forced acceptance, CSV/ZIP.

These pin the rules that make an Adobe Stock upload trustworthy:

- the filename in the CSV is the name of the file that actually gets uploaded,
- a name the operator chose is never silently replaced by a derived one,
- a forced acceptance records *why*, and never rewrites the measured score,
- metadata generation is allowed below the acceptance threshold,
- and a ZIP bundle contains the images *and* the CSV that names them.
"""

import io
import zipfile

import pytest

from models import PipelineStage
from tests.test_stage_pipeline import pipeline_env  # noqa: F401  (shared fixture)


@pytest.fixture()
def make_record(db_session_factory):
    """Insert a record directly, since the delivery layer only reads fields."""

    def _make(
        filename: str = "img.jpg",
        *,
        stage: PipelineStage = PipelineStage.METADATA_READY,
        title: str | None = None,
        score: float | None = None,
        working_path: str | None = None,
        download_name: str | None = None,
    ) -> str:
        from models import ImageRecord

        session = db_session_factory()
        record = ImageRecord(
            filename=filename,
            original_path=f"/tmp/{filename}",
            file_size_bytes=1024,
            stage=stage,
            generated_title=title,
            acceptance_score=score,
            working_path=working_path,
            download_name=download_name,
        )
        session.add(record)
        session.commit()
        record_id = record.id
        session.close()
        return record_id

    return _make


def _reload(db_session_factory, record_id):
    from models import ImageRecord

    session = db_session_factory()
    try:
        return session.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    finally:
        session.close()


def _pipeline_record(
    pipeline_env,
    *,
    name: str = "sample.jpg",
    stage: PipelineStage = PipelineStage.METADATA_READY,
    status: str = "PASSED",
    title: str | None = "A Title",
    original_path: str | None = None,
    working_path: str | None = None,
) -> str:
    """Insert a record against the pipeline fixture's isolated DB.

    ``pipeline_env`` exposes the session factory and the monkeypatched settings,
    so records must be created through it rather than through the shared client
    fixture's in-memory engine.
    """
    from models import ImageRecord, ImageStatus

    settings = pipeline_env["settings"]
    session = pipeline_env["factory"]()
    try:
        record = ImageRecord(
            filename=name,
            original_path=original_path or str(settings.INBOX_DIR / name),
            file_size_bytes=1024,
            status=ImageStatus(status),
            stage=stage,
            generated_title=title,
            working_path=working_path,
        )
        session.add(record)
        session.commit()
        return record.id
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# Naming (unit)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Stainless Steel Conveyor", "stainless-steel-conveyor.jpg"),
        ("already-good-name", "already-good-name.jpg"),
        ("Mixed   CASE  and spaces", "mixed-case-and-spaces.jpg"),
        # A run of separators collapses to one hyphen: Adobe counts characters,
        # so `trailing---hyphens` would waste budget and look careless.
        ("trailing---hyphens---", "trailing-hyphens.jpg"),
        # Only a recognised extension counts as one; an interior dot is unsafe in
        # Adobe's filename rule, so it is slugified away.
        ("dots.and.dots", "dots-and-dots.jpg"),
        ("photo.PNG", "photo.jpg"),
        ("", "asset.jpg"),
    ],
)
def test_normalise_name_makes_an_adobe_safe_filename(raw, expected):
    """The operator types a human name; the tool makes it compliant."""
    from services import asset_naming

    assert asset_naming.normalise_name(raw) == expected


def test_normalise_name_strips_non_ascii_to_the_ascii_remainder():
    """Accented characters are not uploadable, so they are dropped.

    Pinned separately from the parametrised cases because the expected value is
    the non-obvious consequence of the character-class rule (each non-ASCII
    character becomes a separator, which then collapses).
    """
    from services import asset_naming

    assert asset_naming.normalise_name("Ünïcödé Tïtlé") == "n-c-d-t-tl.jpg"


def test_normalise_name_respects_the_filename_cap():
    """The cap counts the whole filename, extension included."""
    from services import asset_naming
    from services.upload_table import MAX_FILENAME_LENGTH

    name = asset_naming.normalise_name("a very long descriptive title " * 4)

    assert len(name) <= MAX_FILENAME_LENGTH
    assert name.endswith(".jpg")


def test_validate_name_accepts_a_compliant_name():
    from services import asset_naming

    assert asset_naming.validate_name("conveyor-line-01.jpg") == []


def test_validate_name_reports_the_reason_a_name_is_rejected():
    """Problems are returned, not raised, so a batch can report per record."""
    from services import asset_naming
    from services.upload_table import MAX_FILENAME_LENGTH

    problems = asset_naming.validate_name("x" * (MAX_FILENAME_LENGTH + 4))
    assert any(str(MAX_FILENAME_LENGTH) in problem for problem in problems)

    problems = asset_naming.validate_name("photo.png")
    assert any("png" in problem for problem in problems)

    problems = asset_naming.validate_name("has spaces.jpg")
    assert any("hyphens" in problem for problem in problems)

    assert asset_naming.validate_name("   ") == ["The name is empty."]


def test_deduplicate_keeps_the_first_and_disambiguates_the_rest():
    """Two identical Filenames would make one CSV row unreachable.

    The assertion is on *uniqueness* and on the first entry surviving untouched;
    the exact suffix numbering is an implementation detail.
    """
    from services import asset_naming

    names = asset_naming.deduplicate(["a.jpg", "a.jpg", "b.jpg", "a.jpg"])

    assert names[0] == "a.jpg"
    assert names[2] == "b.jpg"
    assert len(set(names)) == 4
    assert all(len(name) <= 30 for name in names)
    # The extension must survive the disambiguation.
    assert all(name.endswith(".jpg") for name in names)


def test_effective_download_name_prefers_the_operator_choice(make_record, db_session_factory):
    from services import asset_naming

    record_id = make_record(title="Derived Title", download_name="chosen-name.jpg")
    record = _reload(db_session_factory, record_id)

    assert asset_naming.effective_download_name(record) == "chosen-name.jpg"
    assert asset_naming.is_explicit(record) is True


def test_effective_download_name_falls_back_to_the_derived_name(
    make_record, db_session_factory
):
    from services import asset_naming

    record_id = make_record(title="Stainless Steel Conveyor")
    record = _reload(db_session_factory, record_id)

    name = asset_naming.effective_download_name(record)
    assert name.startswith("stainless-steel-conveyor")
    assert asset_naming.is_explicit(record) is False


# --------------------------------------------------------------------------- #
# Naming (API)
# --------------------------------------------------------------------------- #

def test_rename_sets_a_normalised_name(client, make_record, db_session_factory):
    record_id = make_record(title="Some Title")

    response = client.post(
        "/api/assets/rename",
        json={"items": [{"record_id": record_id, "name": "My Chosen Name"}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 1
    assert body["items"][0]["download_name"] == "my-chosen-name.jpg"

    record = _reload(db_session_factory, record_id)
    assert record.download_name == "my-chosen-name.jpg"


def test_rename_with_a_blank_name_clears_the_override(
    client, make_record, db_session_factory
):
    """Blank is a legitimate action (back to the derived name), not an error."""
    record_id = make_record(title="Some Title", download_name="old-name.jpg")

    response = client.post(
        "/api/assets/rename",
        json={"items": [{"record_id": record_id, "name": "   "}]},
    )

    assert response.status_code == 200
    assert response.json()["failed"] == 0
    assert _reload(db_session_factory, record_id).download_name is None


def test_rename_reports_a_missing_record_without_failing_the_batch(
    client, make_record
):
    record_id = make_record(title="Real Record")

    response = client.post(
        "/api/assets/rename",
        json={
            "items": [
                {"record_id": record_id, "name": "good.jpg"},
                {"record_id": "ghost", "name": "bad.jpg"},
            ]
        },
    )

    body = response.json()
    assert body["updated"] == 1
    assert body["failed"] == 1
    assert "not found" in body["items"][1]["error"]


def test_rename_suggest_proposes_names_without_writing(client, make_record, db_session_factory):
    """The suggestion step is non-mutating, so a whole batch can be reviewed."""
    record_id = make_record(title="A Reviewable Title")

    response = client.post(
        "/api/assets/rename-suggest",
        json={"items": [{"record_id": record_id, "name": ""}]},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["download_name"].startswith("a-reviewable-title")
    # Nothing was persisted.
    assert _reload(db_session_factory, record_id).download_name is None


def test_rename_suggest_returns_unique_names(client, make_record):
    """Two records with the same title must not produce one filename."""
    first = make_record("a.jpg", title="Identical Title")
    second = make_record("b.jpg", title="Identical Title")

    response = client.post(
        "/api/assets/rename-suggest",
        json={
            "items": [
                {"record_id": first, "name": ""},
                {"record_id": second, "name": ""},
            ]
        },
    )

    names = [item["download_name"] for item in response.json()["items"]]
    assert len(set(names)) == 2


def test_chosen_name_reaches_the_csv(client, make_record):
    """The CSV Filename column must be the name of the uploaded file."""
    record_id = make_record(title="Ignored Title")
    client.post(
        "/api/assets/rename",
        json={"items": [{"record_id": record_id, "name": "portal-name.jpg"}]},
    )

    response = client.post("/api/assets/csv/preview", json={"record_ids": [record_id]})

    csv_text = response.json()["csv_text"]
    assert "portal-name.jpg" in csv_text
    assert "ignored-title" not in csv_text


def test_csv_deduplicates_filenames_across_rows(client, make_record):
    """Two rows naming the same file would leave one asset un-described."""
    first = make_record("a.jpg", title="Same Title")
    second = make_record("b.jpg", title="Same Title")
    for record_id in (first, second):
        client.post(
            "/api/assets/rename",
            json={"items": [{"record_id": record_id, "name": "duplicate.jpg"}]},
        )

    response = client.post(
        "/api/assets/csv/preview", json={"record_ids": [first, second]}
    )
    body = response.json()

    assert body["row_count"] == 2
    filenames = [
        line.split(",")[0]
        for line in body["csv_text"].splitlines()[1:]
        if line.strip()
    ]
    assert len(set(filenames)) == 2


# --------------------------------------------------------------------------- #
# Forced acceptance
# --------------------------------------------------------------------------- #

def test_force_accept_moves_a_flagged_record_forward(client, make_record, db_session_factory):
    record_id = make_record("flagged.jpg", stage=PipelineStage.INCOMPATIBLE, score=0.42)

    response = client.post(
        "/api/assets/force-accept",
        json={"record_ids": [record_id], "reason": "intentional soft focus"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] == 1
    assert body["items"][0]["new_stage"] == "COMPATIBLE"

    record = _reload(db_session_factory, record_id)
    assert record.stage == PipelineStage.COMPATIBLE


def test_force_accept_does_not_rewrite_the_measured_score(
    client, make_record, db_session_factory
):
    """The measurement stays honest; the override is recorded separately.

    Rewriting the score to look like a pass would destroy the signal the whole
    scoring pipeline exists to produce.
    """
    record_id = make_record("flagged.jpg", stage=PipelineStage.INCOMPATIBLE, score=0.42)

    client.post(
        "/api/assets/force-accept",
        json={"record_ids": [record_id], "reason": "operator judgement"},
    )

    record = _reload(db_session_factory, record_id)
    assert record.acceptance_score == pytest.approx(0.42)
    assert record.stage_details["forced"]["score"] == pytest.approx(0.42)
    assert record.stage_details["forced"]["reason"] == "operator judgement"


def test_force_accept_records_when_and_where_it_came_from(
    client, make_record, db_session_factory
):
    """An override that leaves no trace is indistinguishable from a gate bug."""
    record_id = make_record("flagged.jpg", stage=PipelineStage.INCOMPATIBLE)

    client.post("/api/assets/force-accept", json={"record_ids": [record_id]})

    forced = _reload(db_session_factory, record_id).stage_details["forced"]
    assert forced["from"] == "INCOMPATIBLE"
    assert forced["at"]


def test_force_accept_refuses_an_ocr_rejection(client, make_record, db_session_factory):
    """Embedded text is a content-policy violation, not a quality judgement."""
    record_id = make_record("text.jpg", stage=PipelineStage.OCR_REJECTED)

    response = client.post("/api/assets/force-accept", json={"record_ids": [record_id]})

    body = response.json()
    assert body["accepted"] == 0
    assert body["refused"] == 1
    assert "content-policy" in body["items"][0]["reason"]
    assert _reload(db_session_factory, record_id).stage == PipelineStage.OCR_REJECTED


def test_force_accept_refuses_an_already_published_record(client, make_record):
    record_id = make_record("done.jpg", stage=PipelineStage.PUBLISHED)

    body = client.post(
        "/api/assets/force-accept", json={"record_ids": [record_id]}
    ).json()

    assert body["refused"] == 1
    assert "published" in body["items"][0]["reason"].lower()


def test_force_accept_is_recorded_as_history_not_overwritten(
    client, make_record, db_session_factory
):
    """A second override must not erase the first one's audit trail."""
    record_id = make_record("flagged.jpg", stage=PipelineStage.INCOMPATIBLE)
    client.post(
        "/api/assets/force-accept",
        json={"record_ids": [record_id], "reason": "first"},
    )

    # Send it back and force it again.
    session = db_session_factory()
    from models import ImageRecord

    record = session.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    record.stage = PipelineStage.INCOMPATIBLE
    session.commit()
    session.close()

    client.post(
        "/api/assets/force-accept",
        json={"record_ids": [record_id], "reason": "second"},
    )

    details = _reload(db_session_factory, record_id).stage_details
    assert details["forced"]["reason"] == "second"
    assert len(details["forced_history"]) == 2
    assert details["forced_history"][0]["reason"] == "first"


def test_force_accepted_record_can_still_be_exported_to_csv(client, make_record):
    """A forced record is not METADATA_READY, so ready-only would drop it."""
    record_id = make_record(
        "flagged.jpg",
        stage=PipelineStage.INCOMPATIBLE,
        title="A Usable Title",
    )
    client.post("/api/assets/force-accept", json={"record_ids": [record_id]})

    ready_only = client.post(
        "/api/assets/csv/preview",
        json={"record_ids": [record_id], "only_ready": True},
    ).json()
    widened = client.post(
        "/api/assets/csv/preview",
        json={"record_ids": [record_id], "only_ready": False},
    ).json()

    assert ready_only["row_count"] == 0
    assert widened["row_count"] == 1


# --------------------------------------------------------------------------- #
# Metadata generation below the threshold
# --------------------------------------------------------------------------- #

def test_metadata_generation_is_allowed_below_the_threshold(pipeline_env, monkeypatch):
    """A below-threshold record is a judgement call, not a dead end.

    Refusing to even generate a title for it turned the acceptance gate into an
    absolute wall; only a content-policy rejection should block Stage 6.
    """
    from tasks import stage_orchestrator

    record_id = _pipeline_record(
        pipeline_env, stage=PipelineStage.INCOMPATIBLE, status="FLAGGED"
    )

    monkeypatch.setattr(
        stage_orchestrator.gemini_metadata,
        "generate_metadata",
        lambda *args, **kwargs: {
            "title": "Generated Below Threshold",
            "description": "d",
            "keywords": ["a", "b"],
            "category": 1,
        },
    )

    job_id = stage_orchestrator.run_metadata_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"], delay_seconds=0
    )
    job = stage_orchestrator.registry.get(job_id)

    assert job.items[0].status == "succeeded"
    record = _reload(pipeline_env["factory"], record_id)
    assert record.stage == PipelineStage.METADATA_READY
    assert record.generated_title == "Generated Below Threshold"


def test_metadata_generation_still_skips_an_ocr_rejection(pipeline_env, monkeypatch):
    """Embedded text stays blocked — it is a content-policy rejection."""
    from tasks import stage_orchestrator

    record_id = _pipeline_record(pipeline_env, stage=PipelineStage.OCR_REJECTED)

    monkeypatch.setattr(
        stage_orchestrator.gemini_metadata,
        "generate_metadata",
        lambda *args, **kwargs: pytest.fail("should not be called for OCR_REJECTED"),
    )

    job_id = stage_orchestrator.run_metadata_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"], delay_seconds=0
    )
    job = stage_orchestrator.registry.get(job_id)

    assert job.items[0].status == "skipped"
    assert "content-policy" in job.items[0].message


# --------------------------------------------------------------------------- #
# Publishing stages the pipeline's quality copy
# --------------------------------------------------------------------------- #

def test_publishing_stages_the_working_copy_not_the_inbox_original(
    pipeline_env, monkeypatch
):
    """The bug behind "publishing compresses my images".

    `process_approval` copied `original_path` — the raw generator output — so
    every stage's quality work (upscale, refine, JPEG conversion) was silently
    discarded at publish. The staged file must be `working_path`.
    """
    from pathlib import Path

    from tasks import audit_orchestrator

    factory = pipeline_env["factory"]
    settings = pipeline_env["settings"]

    # A small "original" and a deliberately larger "pipeline output".
    original = Path(settings.INBOX_DIR) / "original.jpg"
    working = Path(settings.INBOX_DIR) / "working.jpg"
    original.write_bytes(b"ORIGINAL-RAW-UPLOAD")
    working.write_bytes(b"PIPELINE-QUALITY-OUTPUT" * 10)

    record_id = _pipeline_record(
        pipeline_env,
        stage=PipelineStage.METADATA_READY,
        status="PASSED",
        original_path=str(original),
        working_path=str(working),
    )

    monkeypatch.setattr(audit_orchestrator.exiftool_embedder, "embed_metadata", lambda *a, **k: True)

    ok = audit_orchestrator.process_approval(
        db_session_factory=factory,
        record_id=record_id,
        settings=settings,
        override_metadata={"title": "T", "description": "D", "keywords": ["k"]},
    )

    assert ok is True
    staged = list(Path(settings.READY_DIR).glob(f"{record_id}.*"))
    assert len(staged) == 1
    # The staged bytes must be the pipeline output, not the raw upload.
    assert staged[0].read_bytes() == working.read_bytes()


def test_publishing_falls_back_to_the_original_when_no_working_copy(
    pipeline_env, monkeypatch
):
    """A record that never ran a stage must still be publishable."""
    from pathlib import Path

    from tasks import audit_orchestrator

    settings = pipeline_env["settings"]
    original = Path(settings.INBOX_DIR) / "only-original.jpg"
    original.write_bytes(b"ONLY-ORIGINAL")

    record_id = _pipeline_record(
        pipeline_env,
        stage=PipelineStage.METADATA_READY,
        status="PASSED",
        original_path=str(original),
        working_path=None,
    )

    monkeypatch.setattr(audit_orchestrator.exiftool_embedder, "embed_metadata", lambda *a, **k: True)

    ok = audit_orchestrator.process_approval(
        db_session_factory=pipeline_env["factory"],
        record_id=record_id,
        settings=settings,
        override_metadata={"title": "T", "description": "D", "keywords": ["k"]},
    )

    assert ok is True
    staged = list(Path(settings.READY_DIR).glob(f"{record_id}.*"))
    assert staged[0].read_bytes() == original.read_bytes()


# --------------------------------------------------------------------------- #
# ZIP bundle
# --------------------------------------------------------------------------- #

def test_bundle_contains_the_images_and_their_csv(client, make_record, tmp_path, monkeypatch):
    """Bundling is what keeps the CSV and the filenames in step."""
    from config import settings

    # The client fixture already created this directory; only its location needs
    # pinning so the record's staged file can be found.
    ready_dir = tmp_path / "ready"
    ready_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "READY_DIR", ready_dir)

    record_id = make_record("bundle.jpg", title="Bundle Title")
    staged = ready_dir / f"{record_id}.jpg"
    staged.write_bytes(b"JPEGDATA")

    response = client.post(
        "/api/assets/bundle", json={"record_ids": [record_id], "only_ready": False}
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()

    assert "adobe-stock-metadata.csv" in names
    # Exactly one image, named to match the CSV row.
    image_names = [name for name in names if name != "adobe-stock-metadata.csv"]
    assert len(image_names) == 1
    assert image_names[0].startswith("bundle-title")

    csv_text = zipfile.ZipFile(io.BytesIO(response.content)).read(
        "adobe-stock-metadata.csv"
    ).decode("utf-8-sig")
    assert image_names[0] in csv_text


def test_bundle_csv_lists_exactly_the_archived_images(
    client, make_record, tmp_path, monkeypatch
):
    """A CSV row naming a file that is not in the archive is a silent failure.

    Found live: a selection of two records, only one of which was staged, produced
    a bundle holding ONE image but a CSV with TWO rows. Adobe matches rows to
    files by name, so the orphan row is an asset that never receives its metadata.
    The archive and its CSV must describe the same set.
    """
    from config import settings

    ready_dir = tmp_path / "ready"
    ready_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "READY_DIR", ready_dir)

    staged_id = make_record("staged.jpg", title="Staged Asset")
    (ready_dir / f"{staged_id}.jpg").write_bytes(b"JPEGDATA")
    # Selected, but never published — so it has no staged file.
    unstaged_id = make_record("unstaged.jpg", title="Unstaged Asset")

    response = client.post(
        "/api/assets/bundle",
        json={"record_ids": [staged_id, unstaged_id], "only_ready": False},
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        csv_text = archive.read("adobe-stock-metadata.csv").decode("utf-8-sig")

    csv_names = [line.split(",")[0] for line in csv_text.splitlines()[1:] if line.strip()]
    image_names = [name for name in names if not name.endswith(".csv")]

    assert len(image_names) == 1
    # The invariant: every CSV row names a file that is actually in the archive.
    assert set(csv_names) == set(image_names)


def test_bundle_includes_a_published_record_even_though_it_is_not_metadata_ready(
    client, make_record, tmp_path, monkeypatch
):
    """The Gallery bundles *published* assets, which the ready filter excludes."""
    from config import settings

    ready_dir = tmp_path / "ready"
    ready_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "READY_DIR", ready_dir)

    record_id = make_record(
        "published.jpg", stage=PipelineStage.PUBLISHED, title="A Published Asset"
    )
    (ready_dir / f"{record_id}.jpg").write_bytes(b"JPEGDATA")

    response = client.post(
        "/api/assets/bundle", json={"record_ids": [record_id], "only_ready": False}
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        csv_text = archive.read("adobe-stock-metadata.csv").decode("utf-8-sig")

    assert any(not name.endswith(".csv") for name in names)
    assert "published" in csv_text


def test_bundle_requires_an_explicit_selection(client, make_record):
    """A bundle of "everything" is never what the operator means."""
    response = client.post("/api/assets/bundle", json={"record_ids": None})

    assert response.status_code == 400
    assert "explicit selection" in response.json()["detail"]


def test_bundle_falls_back_to_the_working_file_before_publishing(
    client, make_record, tmp_path, monkeypatch
):
    """The gallery's default "Ready to publish" selection has no staged copy.

    Publishing is what creates the staged file, so a bundle of METADATA_READY
    records must ship the working file — the exact bytes a later publish would
    stage — paired with a CSV row naming that same file.
    """
    from config import settings

    ready_dir = tmp_path / "ready-unused"
    ready_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "READY_DIR", ready_dir)

    working = tmp_path / "working.jpg"
    working.write_bytes(b"WORKING-QUALITY-COPY")
    record_id = make_record(
        "ready-but-unpublished.jpg",
        title="Ready But Unpublished",
        working_path=str(working),
    )

    response = client.post(
        "/api/assets/bundle",
        json={"record_ids": [record_id], "only_ready": False},
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        csv_text = archive.read("adobe-stock-metadata.csv").decode("utf-8-sig")
        image_names = [name for name in names if not name.endswith(".csv")]
        assert len(image_names) == 1
        assert archive.read(image_names[0]) == b"WORKING-QUALITY-COPY"

    csv_names = [line.split(",")[0] for line in csv_text.splitlines()[1:] if line.strip()]
    # The invariant, on the fallback path too: CSV row == archived file.
    assert set(csv_names) == set(image_names)


def test_bundle_reports_when_no_file_exists_anywhere(
    client, make_record, tmp_path, monkeypatch
):
    from config import settings

    ready_dir = tmp_path / "ready-empty"
    ready_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "READY_DIR", ready_dir)

    # original_path points at /tmp/... which does not exist in the test
    # environment — neither staged nor working nor original is on disk.
    record_id = make_record("unstaged.jpg", title="Unstaged")

    response = client.post("/api/assets/bundle", json={"record_ids": [record_id]})

    assert response.status_code == 409
    # The message must say *why* nothing can be bundled, and point at the
    # action that still works in this state.
    detail = response.json()["detail"]
    assert "file to bundle" in detail
    assert "CSV" in detail


# --------------------------------------------------------------------------- #
# CSV eligibility from the Gallery
# --------------------------------------------------------------------------- #

def test_record_exposes_the_same_filename_the_csv_will_use(client, make_record):
    """The UI and the CSV must read one value, not two derivations.

    Found live: the gallery's preview modal showed `record.filename` (the raw
    upload name) while the CSV carried the title-derived name. An operator
    checking the name by eye would have seen the wrong one — and the name is
    exactly what Adobe matches on.
    """
    record_id = make_record("raw upload name.jpeg", title="Derived Title Here")

    record = client.get(f"/api/records/{record_id}").json()
    csv_text = client.post(
        "/api/assets/csv/preview", json={"record_ids": [record_id]}
    ).json()["csv_text"]

    csv_filename = csv_text.splitlines()[1].split(",")[0]

    assert record["upload_filename"] == csv_filename
    # And it is deliberately not the raw upload name.
    assert record["upload_filename"] != record["filename"]


def test_upload_filename_follows_an_explicit_rename(client, make_record):
    record_id = make_record("raw.jpeg", title="Derived Title")
    client.post(
        "/api/assets/rename",
        json={"items": [{"record_id": record_id, "name": "chosen.jpg"}]},
    )

    record = client.get(f"/api/records/{record_id}").json()

    assert record["upload_filename"] == "chosen.jpg"


def test_published_records_are_exportable(client, make_record):
    """The gallery's "browse published" mode must still produce a CSV."""
    record_id = make_record(
        "published.jpg",
        stage=PipelineStage.PUBLISHED,
        title="A Published Asset",
    )

    response = client.post("/api/assets/csv/preview", json={"record_ids": [record_id]})

    assert response.status_code == 200
    assert response.json()["row_count"] == 1


def test_csv_export_404s_on_an_empty_selection_result(client, make_record):
    """A selection with nothing exportable must say so, not return a header-only file."""
    record_id = make_record("draft.jpg", stage=PipelineStage.COLLECTED)

    response = client.post(
        "/api/assets/csv",
        json={"record_ids": [record_id], "only_ready": True},
    )

    assert response.status_code == 409
    assert "No exportable rows" in response.json()["detail"]
