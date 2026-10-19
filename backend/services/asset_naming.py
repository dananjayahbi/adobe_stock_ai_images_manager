"""Asset naming - the single source of truth for *what an uploaded file is called*.

Adobe Stock matches a CSV row to an uploaded image **by filename**, so the name
carries real consequences:

* it must be a **filesystem-safe name** whose CSV value matches the uploaded
  file exactly (Adobe's "30 characters maximum" listing is advisory guidance —
  the uploader accepts longer names; the tool caps at
  ``settings.CSV_MAX_FILENAME_LENGTH`` so full descriptive titles survive),
* it must survive a filesystem round trip (ZIP, download, re-upload),
* and it must be **stable** - the name in the CSV has to be the name of the file
  the operator actually uploads.

Three call sites must agree exactly, which is why they all resolve their name
through :func:`effective_download_name`:

* ``services/csv_export.py`` (the Filename column),
* ``routers/gallery.py`` (single-asset download and the ZIP bundle),
* ``services/upload_table.py`` (the copy/paste table).

Historically the name was always *derived* from the generated title, which meant
the operator had no control over it and a truncated title silently produced an
unrecognisable or colliding name. ``ImageRecord.download_name`` now stores an
explicit operator-chosen name; the derived name remains the fallback so every
existing record keeps working without a backfill.
"""

from __future__ import annotations

import re
from pathlib import Path

from models import ImageRecord
from services.upload_table import (
    MAX_FILENAME_LENGTH,
    _slugify,
    build_download_name,
)

#: Longest stem the operator may type, before the extension is added.
MAX_STEM_LENGTH = MAX_FILENAME_LENGTH - len(".jpg")

#: Extensions Adobe accepts for photos. The portal takes JPEG only, and a name
#: promising anything else would not match the file we upload.
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg"})

#: Format markers that are recognised as extensions even though we cannot upload
#: them.
#:
#: The distinction matters: ``photo.PNG`` must become ``photo.jpg`` (the format is
#: replaced), whereas ``dots.and.dots`` has no extension at all and the interior
#: dot belongs to the name. Without this set, ``.png`` would be treated as part of
#: the stem and slugified into ``photo-png.jpg`` — which reads like a mistake.
KNOWN_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".jpe",
        ".png",
        ".webp",
        ".tif",
        ".tiff",
        ".bmp",
        ".gif",
        ".heic",
        ".heif",
        ".avif",
    }
)

#: Adobe's filename rule is stricter than "no path separators": the portal also
#: rejects spaces in practice and the name is used in URLs, so only a conservative
#: token set is allowed.
_VALID_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

#: Runs of dots inside a *stem*, which are not valid in an Adobe filename.
_STEM_DOTS = re.compile(r"\.+")


def _slugify_stem(value: str) -> str:
    """Slugify a filename *stem*, where a dot is not a legal character.

    ``upload_table._slugify`` deliberately permits ``.`` because a complete
    filename needs one before its extension. Applying it to a stem is what made
    ``photo.png`` normalise to ``photo.png.jpg`` and ``dots.and.dots`` keep an
    interior dot that Adobe's filename rule rejects - so stems turn dots into
    hyphens first.
    """
    return _slugify(_STEM_DOTS.sub("-", value))


def split_extension(name: str) -> tuple[str, str]:
    """Split a filename into ``(stem, extension)``, lower-casing the extension.

    Only a *recognised format* counts as an extension. ``Path.suffix`` would
    report ``.dots`` for ``dots.and.dots`` and leave the name with an interior
    dot, which Adobe's filename rule rejects — so an unrecognised suffix is
    treated as part of the stem and slugified away. A recognised but
    non-uploadable format (``.png``) is still an extension, so it can be
    *replaced* rather than absorbed into the name.
    """
    candidate = Path(name or "").suffix.lower()
    if candidate in KNOWN_EXTENSIONS:
        stem = (name or "")[: len(name) - len(candidate)]
        return stem, candidate
    return (name or ""), ""


def normalise_name(raw: str, *, fallback_suffix: str = ".jpg") -> str:
    """Turn operator input into an Adobe-safe filename.

    Slugifies the stem, forces a JPEG extension, and truncates the *stem* (never
    the extension) so the result always satisfies the filename cap. This is
    deliberately forgiving: the operator types a human name and the tool makes it
    compliant rather than rejecting the input outright.
    """
    stem, suffix = split_extension((raw or "").strip())
    if suffix not in ALLOWED_EXTENSIONS:
        # A name typed without an extension (the common case) gets the default;
        # a name with a *wrong* extension (e.g. ".png") is corrected rather than
        # kept, because we can only upload JPEG and the CSV must match.
        suffix = fallback_suffix

    slug = _slugify_stem(stem)
    budget = max(MAX_FILENAME_LENGTH - len(suffix), 1)
    if len(slug) > budget:
        slug = slug[:budget].rstrip("-")

    if not slug:
        slug = "asset"

    return f"{slug}{suffix}"


def validate_name(name: str) -> list[str]:
    """Return human-readable problems with a filename, or ``[]`` when valid.

    Returned rather than raised so the bulk-rename endpoint can report per-record
    results instead of failing the whole batch on one bad row.
    """
    raw = (name or "").strip()
    if not raw:
        return ["The name is empty."]

    problems: list[str] = []

    if len(raw) > MAX_FILENAME_LENGTH:
        problems.append(
            f"{len(raw)} characters — names are capped at {MAX_FILENAME_LENGTH} "
            "including the extension."
        )

    # The *reported* suffix is the literal one the operator typed, not the one
    # `split_extension` recognises — otherwise "photo.png" would be reported as
    # having no extension at all, which is not what they typed.
    reported = Path(raw).suffix.lower()
    stem, suffix = split_extension(raw)
    if suffix not in ALLOWED_EXTENSIONS:
        problems.append(
            f"Extension '{reported or '(none)'}' is not uploadable; use "
            f"{' or '.join(sorted(ALLOWED_EXTENSIONS))}."
        )
    if stem != _slugify_stem(stem) or not _VALID_NAME.match(stem):
        problems.append(
            "Use lower-case letters, digits and single hyphens only "
            "(no spaces, dots, or accents)."
        )

    return problems


def derive_name(record: ImageRecord, staged_path: Path | str | None = None) -> str:
    """The name a record would get with no operator override.

    Wraps :func:`services.upload_table.build_download_name` so the derivation
    rule (title → slug → cap) stays in one place and this module only owns the
    *override* behaviour.

    Deliberately **no identifier is mixed into the name**. The name is a
    deliverable the operator reads and uploads, so it is built from the title
    alone; batch uniqueness is applied separately, and only where a collision
    actually exists, by :func:`deduplicate`.
    """
    return build_download_name(record, staged_path)


def patch_download_names(records: list[ImageRecord], names: list[str]) -> None:
    """Set ``download_name`` on records in memory so every reader agrees.

    The CSV build resolves a name in two places - once to emit the row, once
    when the batch is de-duplicated. Those two must produce the same string, or
    the Filename column names a file the ZIP does not contain.

    Persisting the de-duplicated names instead would be wrong: uniqueness is a
    property of *this batch*, so two records that collide here will legitimately
    collide in a different export. The names are therefore pinned on the
    in-memory objects and the caller decides whether to commit (a delivery export
    flushes them; a read-only preview does not).
    """
    for record, name in zip(records, names):
        record.download_name = name


def effective_download_name(
    record: ImageRecord,
    staged_path: Path | str | None = None,
) -> str:
    """The filename this record will actually be uploaded under.

    An explicit ``download_name`` wins: it is what the operator asked for, and
    the CSV row, the download and the ZIP entry must all use it verbatim or
    Adobe will not find the match. Falls back to the derived name.
    """
    explicit = (getattr(record, "download_name", None) or "").strip()
    if explicit:
        return explicit
    return derive_name(record, staged_path)


def is_explicit(record: ImageRecord) -> bool:
    """True when the record's name was chosen by the operator, not derived."""
    return bool((getattr(record, "download_name", None) or "").strip())


def deduplicate(names: list[str]) -> list[str]:
    """Make a batch of filenames unique, preserving order.

    Long descriptive titles can collide across a batch, and two
    identically-named files in one ZIP or CSV would silently drop a row. Later
    duplicates gain a numeric suffix carved out of the stem, never the
    extension.
    """
    seen: dict[str, int] = {}
    result: list[str] = []

    for name in names:
        key = name.lower()
        if key not in seen:
            seen[key] = 1
            result.append(name)
            continue

        seen[key] += 1
        stem, suffix = split_extension(name)
        attempt = seen[key]
        while True:
            marker = f"-{attempt}"
            budget = max(MAX_FILENAME_LENGTH - len(suffix) - len(marker), 1)
            candidate = f"{stem[:budget].rstrip('-')}{marker}{suffix}"
            if candidate.lower() not in seen:
                seen[candidate.lower()] = 1
                result.append(candidate)
                break
            attempt += 1

    return result
