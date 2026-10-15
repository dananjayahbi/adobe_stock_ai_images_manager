"""Startup upgrade of filenames pinned under the old 30-character cap.

Adobe's console *lists* "Filename: 30 characters maximum", but that figure is
advisory guidance, not a portal limit: the uploader accepts longer names and
the enforced rule is that the CSV Filename matches the uploaded file exactly.
The cap has since been raised so the full title-derived name ships
(``ancient-flint-arrowhead-wisdom-of-prehistoric-hunters.jpg`` instead of
``ancient-flint-arrowhead-is.jpg``).

Every CSV download *pins* the batch-resolved names onto the records
(:func:`services.asset_naming.patch_download_names`), so records that already
took delivery once still carry the old truncated derivation as an explicit
``download_name`` — raising the cap alone would leave them shipping partial
names forever.

This pass upgrades exactly those pins: a stored name is replaced only when it
is byte-for-byte what the **same** derivation produced under the old cap and
differs from what it produces now. Hand-chosen renames, dedupe-marker names
(``...-2.jpg``) and already-full names never match that pattern, so operator
choices are untouched. The pass is self-limiting — after one run no record
matches — so later startups stay cheap. A commit happens only when something
changed, and any failure is logged without blocking startup.
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from models import ImageRecord
from services import asset_naming
from services.upload_table import build_download_name

logger = logging.getLogger(__name__)

#: The filename cap in force before it was raised (whole name, extension
#: included). Only pins this derivation would have clipped are upgraded.
OLD_FILENAME_CAP = 30


def _old_form(record: ImageRecord) -> str:
    """The name the pre-raise cap would have derived for this record.

    Reuses ``build_download_name`` with the old cap rather than re-implementing
    the truncation, so the comparison can never drift from the real derivation.
    """
    return build_download_name(record, max_length=OLD_FILENAME_CAP)


def upgrade_truncated_names(session_factory) -> int:
    """Rewrite explicit names that are the old cap's truncation of today's name.

    Args:
        session_factory: Callable returning a new Session.

    Returns:
        The number of records upgraded. Zero on the second and every later
        start, which is what makes this safe to run on every boot.
    """
    db: Session = session_factory()
    upgraded = 0
    try:
        candidates = (
            db.query(ImageRecord)
            .filter(ImageRecord.download_name.isnot(None))
            .all()
        )

        for record in candidates:
            stored = (record.download_name or "").strip()
            if not stored:
                continue

            full = asset_naming.derive_name(record)
            if stored == full:
                continue  # already the full name — nothing to do
            if stored != _old_form(record):
                continue  # hand-chosen (or dedupe-marked) — never touch

            logger.info(
                "Upgrading truncated filename for %s: %s -> %s",
                record.id,
                stored,
                full,
            )
            record.download_name = full
            upgraded += 1

        if upgraded:
            db.commit()
            logger.info("Upgraded %d truncated filename(s)", upgraded)
    except Exception:  # pragma: no cover - must never block startup
        db.rollback()
        logger.exception("Filename backfill failed; leaving records untouched")
        return 0
    finally:
        db.close()

    return upgraded


def run_filename_backfill(engine: Engine) -> int:
    """Entry point for startup, matching the other startup helpers.

    ``engine`` is accepted for signature consistency at the call site; the
    session factory is bound to the same engine by ``database``.
    """
    from database import SessionLocal

    return upgrade_truncated_names(SessionLocal)
