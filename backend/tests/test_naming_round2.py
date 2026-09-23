"""Naming round 2: the delivered filename must be readable and human-chosen.

Three defects are pinned here, all of them found by using the tool rather than by
running the suite:

1. **A code appeared in every name.** Truncated titles gained a slice of the
   record id (``futuristic-automat-b2d58dd.jpg``). The filename is a deliverable
   the operator reads and uploads, so it is built from the title alone.
2. **The metadata model already knows what the image shows.** It is now asked to
   propose a filename, and the proposal is stored *separately* from the name that
   is actually used — a model's output must never silently become the delivered
   filename.
3. **"Zip + CSV" was offered where it cannot work.** A bundle needs a staged
   file, and publishing is what stages one, so the control is now only offered
   where the bundle can succeed.
"""

import io
import zipfile

import pytest

from models import PipelineStage
from services.upload_table import MAX_FILENAME_LENGTH
from tests.test_stage_pipeline import pipeline_env  # noqa: F401  (shared fixture)


@pytest.fixture()
def make_record(db_session_factory):
    """Insert a record directly, since the naming layer only reads fields."""

    def _make(
        filename: str = "img.jpg",
        *,
        stage: PipelineStage = PipelineStage.METADATA_READY,
        title: str | None = None,
        download_name: str | None = None,
        suggested_filename: str | None = None,
    ) -> str:
        from models import ImageRecord

        session = db_session_factory()
        record = ImageRecord(
            filename=filename,
            original_path=f"/tmp/{filename}",
            file_size_bytes=1024,
            stage=stage,
            generated_title=title,
            download_name=download_name,
            suggested_filename=suggested_filename,
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


def _stage_file(tmp_path, monkeypatch, record_id, suffix=".jpg"):
    """Pin READY_DIR into tmp_path and create the record's staged file."""
    from config import settings

    ready_dir = tmp_path / "ready-naming"
    ready_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "READY_DIR", ready_dir)
    path = ready_dir / f"{record_id}{suffix}"
    path.write_bytes(b"JPEGDATA")
    return path


# --------------------------------------------------------------------------- #
# 1. No code in the name
# --------------------------------------------------------------------------- #

#: Long enough that the derived name is truncated, which is exactly the case that
#: used to grow an identifier suffix.
LONG_TITLE = "Futuristic automated warehouse with robotic sorting arms"


def test_derived_name_carries_no_identifier(make_record, db_session_factory):
    """The name is a deliverable, not an internal key."""
    from services import asset_naming

    record_id = make_record(title=LONG_TITLE)
    record = _reload(db_session_factory, record_id)

    name = asset_naming.derive_name(record)

    assert name == "futuristic-automated-wareh.jpg"
    assert len(name) <= MAX_FILENAME_LENGTH
    # The id, or any fragment of it, must not appear.
    assert record_id[:6] not in name
    assert record_id not in name


def test_truncation_never_appends_the_record_id(make_record, db_session_factory):
    """The regression, stated as an invariant rather than one example.

    The old derivation only appended a token *when the slug was shortened*, so a
    test on a short title would have passed while every long title was wrong.
    """
    from services import asset_naming

    ids = [
        make_record(f"{index}.jpg", title=LONG_TITLE)
        for index in range(4)
    ]

    for record_id in ids:
        record = _reload(db_session_factory, record_id)
        name = asset_naming.derive_name(record)
        assert record_id[:6] not in name, f"{name} still contains the record id"
        assert len(name) <= MAX_FILENAME_LENGTH


def test_a_name_that_fits_is_left_completely_alone(make_record, db_session_factory):
    """No suffix logic may touch a name that already fits the budget."""
    from services import asset_naming

    record_id = make_record(title="Conveyor Line")
    record = _reload(db_session_factory, record_id)

    assert asset_naming.derive_name(record) == "conveyor-line.jpg"


# --------------------------------------------------------------------------- #
# 2. Batch fitting keeps the title readable
# --------------------------------------------------------------------------- #

def test_colliding_names_are_made_unique_and_keep_their_opening_words(
    make_record, db_session_factory
):
    """Two rows must not ship under one name, and the marker must be readable.

    A hard 30-character cap with no identifier to disambiguate on means the
    marked name has to give up a word to make room. What matters is that the
    marker is a readable ``-2`` in the stem - not a hash - and that both names
    stay inside Adobe's cap with the extension intact.
    """
    from services import asset_naming

    first = make_record("a.jpg", title=LONG_TITLE)
    second = make_record("b.jpg", title=LONG_TITLE)
    records = [
        _reload(db_session_factory, record_id) for record_id in (first, second)
    ]

    names = asset_naming.deduplicate(
        [asset_naming.derive_name(record) for record in records]
    )

    assert len(set(names)) == 2
    assert all(len(name) <= MAX_FILENAME_LENGTH for name in names)
    assert all(name.endswith(".jpg") for name in names)
    # Both still open with the same words, and the second carries a plain marker.
    assert names[0] == "futuristic-automated-wareh.jpg"
    assert names[1].endswith("-2.jpg")
    assert names[1].startswith("futuristic-automated")


def test_deduplicate_leaves_unique_names_untouched(make_record, db_session_factory):
    from services import asset_naming

    ids = [
        make_record("a.jpg", title="Conveyor Line"),
        make_record("b.jpg", title="Robotic Arm"),
    ]
    records = [_reload(db_session_factory, record_id) for record_id in ids]
    derived = [asset_naming.derive_name(record) for record in records]

    assert asset_naming.deduplicate(derived) == derived


def test_csv_rows_agree_with_the_names_the_records_report(
    client, make_record, tmp_path, monkeypatch
):
    """The CSV row and the ZIP entry must be one string, not two derivations."""
    from config import settings

    ready_dir = tmp_path / "ready"
    ready_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "READY_DIR", ready_dir)

    first = make_record("a.jpg", title=LONG_TITLE)
    second = make_record("b.jpg", title=LONG_TITLE)
    for record_id in (first, second):
        (ready_dir / f"{record_id}.jpg").write_bytes(b"JPEGDATA")

    response = client.post(
        "/api/assets/bundle", json={"record_ids": [first, second], "only_ready": False}
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        csv_text = archive.read("adobe-stock-metadata.csv").decode("utf-8-sig")

    csv_names = [
        line.split(",")[0] for line in csv_text.splitlines()[1:] if line.strip()
    ]
    image_names = sorted(name for name in names if not name.endswith(".csv"))

    # The archive and its CSV describe the same two files, by name.
    assert sorted(csv_names) == image_names
    # And the API reports the same strings, so the UI cannot show a third name.
    for record_id in (first, second):
        record = client.get(f"/api/records/{record_id}").json()
        assert record["upload_filename"] in image_names


def test_csv_download_persists_the_batch_names_it_shipped(
    client, make_record, db_session_factory
):
    """A downloaded CSV must still describe the records afterwards.

    The names are fitted per batch, so the batch that was actually exported has
    to be the one recorded — otherwise the operator's next download silently
    renames the files the CSV they already sent to Adobe refers to.

    Compared as a *set*, not positionally: `created_at` is stored at microsecond
    resolution, so two records inserted in the same instant are ordered by the id
    tiebreak rather than by insertion, and pairing rows to records by index would
    assert something the database does not promise. The correspondence that
    matters is by record, and that is what this checks.
    """
    first = make_record("a.jpg", title=LONG_TITLE)
    second = make_record("b.jpg", title=LONG_TITLE)

    response = client.post(
        "/api/assets/csv", json={"record_ids": [first, second], "only_ready": True}
    )

    assert response.status_code == 200
    csv_names = [
        line.split(",")[0]
        for line in response.content.decode("utf-8-sig").splitlines()[1:]
        if line.strip()
    ]
    assert len(csv_names) == 2
    assert len(set(csv_names)) == 2

    stored = [
        _reload(db_session_factory, first).download_name,
        _reload(db_session_factory, second).download_name,
    ]
    # Every row that was shipped names a record, and vice versa.
    assert sorted(stored) == sorted(csv_names)
    # Both names survived as a coherent pair: one clean, one marked.
    assert sum(1 for name in stored if name.endswith("-2.jpg")) == 1


def test_csv_preview_does_not_write_names(client, make_record, db_session_factory):
    """Asking what a CSV *would* say must not change any record."""
    first = make_record("a.jpg", title=LONG_TITLE)
    second = make_record("b.jpg", title=LONG_TITLE)

    response = client.post(
        "/api/assets/csv/preview", json={"record_ids": [first, second]}
    )

    assert response.status_code == 200
    assert _reload(db_session_factory, first).download_name is None
    assert _reload(db_session_factory, second).download_name is None


# --------------------------------------------------------------------------- #
# 3. The model's own filename proposal
# --------------------------------------------------------------------------- #

def test_metadata_prompt_asks_for_a_filename():
    """A proposal the operator can apply has to be requested, not inferred."""
    from services import gemini_metadata

    assert '"filename"' in gemini_metadata.METADATA_PROMPT
    assert "extension" in gemini_metadata.METADATA_PROMPT


def test_metadata_prompt_formats_with_the_filename_target():
    from services import gemini_metadata

    rendered = gemini_metadata.METADATA_PROMPT.format(
        categories="1=Animals",
        title_target=gemini_metadata.TITLE_TARGET,
        filename_target=gemini_metadata.FILENAME_STEM_TARGET,
        max_keywords=49,
        high_impact=10,
    )
    assert str(gemini_metadata.FILENAME_STEM_TARGET) in rendered


def test_generate_metadata_normalises_the_model_filename(monkeypatch):
    """A proposal must arrive already compliant, never needing hand fixing."""
    from services import gemini_metadata

    monkeypatch.setattr(
        gemini_metadata,
        "chat_json",
        lambda path, prompt, temperature=0.2: {
            "title": "Robotic arm sorting parcels",
            "filename": "  Robotic Arm — Sorting Parcels!!  ",
            "description": "d",
            "keywords": ["robots"],
            "category": 8,
        },
    )

    result = gemini_metadata.generate_metadata("whatever.jpg")

    assert result["suggested_filename"] == "robotic-arm-sorting-parcel.jpg"
    assert len(result["suggested_filename"]) <= MAX_FILENAME_LENGTH


def test_generate_metadata_without_a_filename_proposes_nothing(monkeypatch):
    """An absent answer must stay absent.

    `normalise_name` falls back to ``asset.jpg`` for empty input. Offering that
    as a suggestion would apply one identical placeholder name to an entire
    batch — worse than having no suggestion at all.
    """
    from services import gemini_metadata

    monkeypatch.setattr(
        gemini_metadata,
        "chat_json",
        lambda path, prompt, temperature=0.2: {
            "title": "Robotic arm sorting parcels",
            "description": "d",
            "keywords": ["robots"],
            "category": 8,
        },
    )

    result = gemini_metadata.generate_metadata("whatever.jpg")

    assert result["suggested_filename"] is None


def test_generate_metadata_keeps_the_proposal_separate_from_the_title(monkeypatch):
    """The proposal is an extra field; it must not displace the title."""
    from services import gemini_metadata

    monkeypatch.setattr(
        gemini_metadata,
        "chat_json",
        lambda path, prompt, temperature=0.2: {
            "title": "Robotic arm sorting parcels in a depot",
            "filename": "robotic-arm-sorting-parcels",
            "description": "d",
            "keywords": ["robots"],
            "category": 8,
        },
    )

    result = gemini_metadata.generate_metadata("whatever.jpg")

    assert result["title"] == "Robotic arm sorting parcels in a depot"
    # `robotic-arm-sorting-parcels.jpg` would be 32 characters, so the stem is
    # clipped to fit Adobe's 30-character cap — the assertion is on the rules, not
    # on one exact string.
    assert result["suggested_filename"].startswith("robotic-arm-sorting-parcel")
    assert result["suggested_filename"].endswith(".jpg")
    assert len(result["suggested_filename"]) <= MAX_FILENAME_LENGTH


def test_metadata_stage_stores_the_proposal_without_applying_it(
    pipeline_env, monkeypatch
):
    """Generation proposes; it must not decide."""
    from services import gemini_metadata
    from tasks import stage_orchestrator
    from tests.test_stage_pipeline import _make_record

    monkeypatch.setattr(
        gemini_metadata,
        "generate_metadata",
        lambda path, api_key=None: {
            "title": "A Named Asset",
            "description": "d",
            "keywords": ["a"],
            "category": 8,
            "suggested_filename": "a-named-asset.jpg",
        },
    )

    record_id, _ = _make_record(
        pipeline_env["factory"],
        pipeline_env["tmp_path"],
        stage=PipelineStage.COMPATIBLE,
    )

    stage_orchestrator.run_metadata_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )

    record = _reload(pipeline_env["factory"], record_id)
    assert record.suggested_filename == "a-named-asset.jpg"
    # Crucially: the delivered name was NOT decided by the model.
    assert record.download_name is None


def test_apply_suggested_names_adopts_the_proposal(
    client, make_record, db_session_factory
):
    record_id = make_record(title="Ignored Title", suggested_filename="from-the-model.jpg")

    response = client.post(
        "/api/assets/apply-suggested-names",
        json={"items": [{"record_id": record_id, "name": ""}]},
    )

    assert response.status_code == 200
    assert response.json()["updated"] == 1
    assert _reload(db_session_factory, record_id).download_name == "from-the-model.jpg"


def test_apply_suggested_names_falls_back_to_the_title(client, make_record, db_session_factory):
    """A record the model never named must still get a usable name.

    Otherwise the button would appear to work while silently skipping part of the
    selection.
    """
    record_id = make_record(title="Robotic Arm Sorting Parcels")

    response = client.post(
        "/api/assets/apply-suggested-names",
        json={"items": [{"record_id": record_id, "name": ""}]},
    )

    assert response.status_code == 200
    name = _reload(db_session_factory, record_id).download_name
    assert name.startswith("robotic-arm-sorting-parcel")
    assert len(name) <= MAX_FILENAME_LENGTH
    assert name.endswith(".jpg")


def test_apply_suggested_names_keeps_a_batch_unique(client, make_record, db_session_factory):
    """The model can propose the same name twice; the batch cannot ship it."""
    first = make_record("a.jpg", suggested_filename="same-name.jpg")
    second = make_record("b.jpg", suggested_filename="same-name.jpg")

    response = client.post(
        "/api/assets/apply-suggested-names",
        json={
            "items": [
                {"record_id": first, "name": ""},
                {"record_id": second, "name": ""},
            ]
        },
    )

    names = [item["download_name"] for item in response.json()["items"]]
    assert len(set(names)) == 2
    assert all(len(name) <= MAX_FILENAME_LENGTH for name in names)


def test_the_proposal_reaches_the_record_response(client, make_record):
    """The UI has to be able to show what the model proposed."""
    record_id = make_record(title="A Title", suggested_filename="proposed.jpg")

    record = client.get(f"/api/records/{record_id}").json()

    assert record["suggested_filename"] == "proposed.jpg"
    # And it is still not the delivered name until it is applied.
    assert record["download_name"] is None
    assert record["upload_filename"] == "a-title.jpg"


# --------------------------------------------------------------------------- #
# 4. The bundle is only offered where it can work
# --------------------------------------------------------------------------- #

def test_bundle_refusal_explains_that_publishing_stages_the_file(
    client, make_record, tmp_path, monkeypatch
):
    """The 409 an operator actually hit must say what to do about it.

    The old message ("Publish them first.") never said that *publishing* is what
    creates the staged file, which is the whole reason the button failed.
    """
    from config import settings

    ready_dir = tmp_path / "ready-empty-naming"
    ready_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "READY_DIR", ready_dir)

    record_id = make_record("unstaged.jpg", title="Unstaged Asset")

    response = client.post("/api/assets/bundle", json={"record_ids": [record_id]})

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "Publishing" in detail
    # It must also point at the action that does work in this state.
    assert "CSV" in detail


def test_publishing_then_bundling_succeeds(
    client, make_record, tmp_path, monkeypatch
):
    """The end-to-end path the operator was trying to take."""
    from config import settings

    ready_dir = tmp_path / "ready-after-publish"
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
        assert any(name.endswith(".csv") for name in archive.namelist())
