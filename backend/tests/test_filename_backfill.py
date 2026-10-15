"""Startup backfill: names pinned under the old 30-char cap become full names.

A CSV download pins the batch-resolved ``download_name`` on every exported
record. When the filename cap was raised, those pins kept shipping the old
truncated form (``futuristic-automated-wareh.jpg``) even though the title
behind them is far longer. The backfill rewrites *only* pins that are
byte-for-byte the old cap's truncation of today's derivation — hand-chosen
renames, dedupe-marked names and already-full names are never touched, and the
pass stops finding work after one run.
"""

from services.filename_backfill import OLD_FILENAME_CAP, upgrade_truncated_names
from services.upload_table import build_download_name

LONG_TITLE = "Futuristic automated warehouse with robotic sorting arms"


def _make_record(db_session_factory, *, title, download_name):
    """Insert a record with an explicit pin, the field the backfill reads."""
    from models import ImageRecord, PipelineStage

    session = db_session_factory()
    record = ImageRecord(
        filename="img.jpg",
        original_path="/tmp/img.jpg",
        file_size_bytes=1024,
        stage=PipelineStage.METADATA_READY,
        generated_title=title,
        download_name=download_name,
    )
    session.add(record)
    session.commit()
    record_id = record.id
    session.close()
    return record_id


def _reload(db_session_factory, record_id):
    from models import ImageRecord

    session = db_session_factory()
    try:
        return session.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    finally:
        session.close()


def _old_pin(db_session_factory, record_id):
    """The exact string the pre-raise cap would have pinned for this record."""
    record = _reload(db_session_factory, record_id)
    return build_download_name(record, max_length=OLD_FILENAME_CAP)


def test_truncated_pin_is_upgraded_to_the_full_name(db_session_factory):
    record_id = _make_record(db_session_factory, title=LONG_TITLE, download_name=None)
    old_pin = _old_pin(db_session_factory, record_id)
    assert old_pin == "futuristic-automated-wareh.jpg"  # the defect, pinned

    # Simulate the pin a past CSV download wrote.
    session = db_session_factory()
    from models import ImageRecord

    record = session.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    record.download_name = old_pin
    session.commit()
    session.close()

    upgraded = upgrade_truncated_names(db_session_factory)

    assert upgraded == 1
    record = _reload(db_session_factory, record_id)
    assert record.download_name == (
        "futuristic-automated-warehouse-with-robotic-sorting-arms.jpg"
    )
    assert len(record.download_name) <= 100


def test_hand_chosen_name_is_never_touched(db_session_factory):
    record_id = _make_record(
        db_session_factory,
        title=LONG_TITLE,
        download_name="my-carefully-picked-name.jpg",
    )

    upgraded = upgrade_truncated_names(db_session_factory)

    assert upgraded == 0
    record = _reload(db_session_factory, record_id)
    assert record.download_name == "my-carefully-picked-name.jpg"


def test_already_full_name_and_missing_pin_are_left_alone(db_session_factory):
    full = "futuristic-automated-warehouse-with-robotic-sorting-arms.jpg"
    pinned_full = _make_record(db_session_factory, title=LONG_TITLE, download_name=full)
    unpinned = _make_record(db_session_factory, title=LONG_TITLE, download_name=None)

    upgraded = upgrade_truncated_names(db_session_factory)

    assert upgraded == 0
    assert _reload(db_session_factory, pinned_full).download_name == full
    assert _reload(db_session_factory, unpinned).download_name is None


def test_dedupe_marker_form_is_left_alone(db_session_factory):
    """A ``-2`` pin came from a batch collision — its stem is clipped *and*
    marked, so it is not the plain old truncation and must survive."""
    marker = "futuristic-automated-ware-2.jpg"
    record_id = _make_record(
        db_session_factory, title=LONG_TITLE, download_name=marker
    )

    upgraded = upgrade_truncated_names(db_session_factory)

    assert upgraded == 0
    assert _reload(db_session_factory, record_id).download_name == marker


def test_second_run_finds_no_work(db_session_factory):
    """Self-limiting: upgrades once, then startup cost drops to a scan."""
    record_id = _make_record(db_session_factory, title=LONG_TITLE, download_name=None)

    from models import ImageRecord

    session = db_session_factory()
    record = session.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    record.download_name = build_download_name(record, max_length=OLD_FILENAME_CAP)
    session.commit()
    session.close()

    assert upgrade_truncated_names(db_session_factory) == 1
    assert upgrade_truncated_names(db_session_factory) == 0
