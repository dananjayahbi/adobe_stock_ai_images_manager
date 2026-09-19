"""Stage 6 - Adobe Stock CSV export.

Produces the file the Contributor Portal accepts for batch metadata upload. The
column order, header spelling, and quoting rules mirror Adobe's own sample
(``REFERENCES/Sample_Adobe_Stock_CSV_upload.csv``) exactly:

``Filename,Title,Keywords,Category,Releases``

Three details matter for the portal to accept the file and match rows to assets:

* ``Filename`` must be the *exact* uploaded filename including extension, and is
  capped at **30 characters** by Adobe.
* ``Title`` is capped at **70 characters** and must be plain text *without commas
  or special characters* - a separate constraint from CSV quoting.
* ``Keywords`` is one comma-separated quoted field, so a keyword containing a
  comma would corrupt the row and such keywords are normalised.

Adobe also caps a CSV at **5,000 rows** and **1 MB**, and requires UTF-8. Those
are enforced here rather than left to the portal, so an operator never hands
Adobe a file that is silently rejected.

Only ``Filename`` is required by Adobe; the remaining columns are emitted even
when empty so the header shape stays constant.

Sources (helpx, verified 2026-09):
* manage-your-portfolio/csv-requirements-content.html
* manage-your-portfolio/create-csv-file.html
* content-policies-guidelines/metadata/tips-effective-titles-keywords.html
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass, field

from config import settings
from models import ImageRecord
from services.adobe_categories import DEFAULT_CATEGORY, resolve_category
from services.storage import resolve_ready_path
from services.upload_table import build_download_name

logger = logging.getLogger(__name__)

#: Adobe's exact header line, in Adobe's exact order.
CSV_COLUMNS: tuple[str, ...] = ("Filename", "Title", "Keywords", "Category", "Releases")

#: Adobe: "Title | 70 characters maximum".
MAX_TITLE_LENGTH = settings.CSV_MAX_TITLE_LENGTH
#: Adobe's CSV page says 50; the titles/keywords page and portal say 49. The
#: lower figure satisfies both.
MAX_KEYWORDS = settings.CSV_MAX_KEYWORDS
#: Adobe: "Maximum rows | 5,000 rows per file".
MAX_ROWS = settings.CSV_MAX_ROWS
#: Adobe: "Maximum file size | 1 MB".
MAX_FILE_SIZE_BYTES = settings.CSV_MAX_FILE_SIZE_BYTES

#: Excel only recognises UTF-8 when the file starts with a BOM. Adobe requires
#: UTF-8, so the BOM is a compatibility aid, not a deviation.
UTF8_BOM = "\ufeff"

#: Characters Adobe's "no special characters" rule targets, plus the ones that
#: would confuse a comma-separated parser. Ordinary sentence punctuation is kept
#: so titles still read naturally.
_TITLE_STRIP = re.compile(r"[,;|\\\"\u201c\u201d\u2018\u2019<>\[\]{}~^`]+")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass
class CsvBuildResult:
    """A generated CSV plus per-record problems worth surfacing."""

    csv_text: str
    row_count: int
    #: Record ids skipped because they lacked a usable filename or title.
    skipped: list[str]
    #: Non-fatal notes, e.g. a title that had to be truncated.
    warnings: list[str]
    #: Records dropped because a hard Adobe limit was hit.
    overflowed: list[str] = field(default_factory=list)

    @property
    def byte_size(self) -> int:
        """Size of the encoded document, in bytes."""
        return len(self.csv_text.encode("utf-8"))

    @property
    def within_row_limit(self) -> bool:
        """True when the document satisfies Adobe's 5,000-row cap."""
        return self.row_count <= MAX_ROWS

    @property
    def within_size_limit(self) -> bool:
        """True when the document satisfies Adobe's 1 MB cap."""
        return self.byte_size <= MAX_FILE_SIZE_BYTES


def sanitize_title(title: str) -> str:
    """Make a title safe for Adobe's plain-text Title field.

    Adobe specifies a "plain text description **without commas or special
    characters**". CSV quoting alone is not sufficient: a comma survives the
    round trip and then trips Adobe's own field validation, so commas and other
    separator-like characters are removed here and whitespace is collapsed.

    Args:
        title: The raw generated title.

    Returns:
        A single-line, comma-free title.
    """
    if not title:
        return ""

    cleaned = _CONTROL_CHARS.sub(" ", title)
    cleaned = _TITLE_STRIP.sub(" ", cleaned)
    # Collapse any whitespace the substitutions introduced, and force a single
    # line - a newline inside a quoted field is legal CSV but breaks Adobe's UI.
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


def _clean_keyword(keyword: str) -> str:
    """Normalise one keyword so it cannot break the comma-separated field."""
    # Adobe's parser splits on commas, so a comma inside a keyword would be
    # read as two keywords. Semicolons read as noise, so both become spaces.
    cleaned = keyword.replace(",", " ").replace(";", " ")
    return " ".join(cleaned.split()).strip()


def build_row(record: ImageRecord) -> tuple[list[str], list[str]]:
    """Build one CSV row for a record.

    Returns ``(row, warnings)``. The row is empty when the record cannot be
    represented, which the caller reports as a skip.
    """
    warnings: list[str] = []

    # The CSV must name the file exactly as the operator will upload it, so it
    # uses the same slugified name the ZIP/download endpoints produce - including
    # the staged file's extension, which may differ from the original upload.
    # The record id is passed as a disambiguator because Adobe's 30-character
    # cap can otherwise make two long titles collide.
    staged_path = resolve_ready_path(record)
    filename = build_download_name(record, staged_path, disambiguator=record.id)

    raw_title = (record.generated_title or "").strip()
    if not raw_title:
        # Adobe treats Title as optional, but a blank title wastes the row's
        # most valuable keyword real estate - fall back to the filename stem.
        raw_title = filename.rsplit(".", 1)[0].replace("-", " ").strip()
        warnings.append(
            f"{filename}: no generated title; used the filename as the title."
        )

    title = sanitize_title(raw_title)
    if not title:
        title = sanitize_title(filename.rsplit(".", 1)[0].replace("-", " "))
    if title != raw_title:
        warnings.append(
            f"{filename}: title cleaned of commas/special characters for Adobe."
        )

    if len(title) > MAX_TITLE_LENGTH:
        # Truncate on a word boundary so the result still reads like a phrase.
        clipped = title[:MAX_TITLE_LENGTH]
        if " " in clipped:
            clipped = clipped.rsplit(" ", 1)[0]
        title = clipped.rstrip(" ,;:-") or title[:MAX_TITLE_LENGTH].rstrip()
        warnings.append(f"{filename}: title truncated to {MAX_TITLE_LENGTH} characters.")

    raw_keywords = [str(keyword) for keyword in (record.generated_keywords or [])]
    keywords: list[str] = []
    seen: set[str] = set()
    for raw in raw_keywords:
        cleaned = _clean_keyword(raw)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            # Adobe: "Use each keyword once."
            continue
        seen.add(lowered)
        keywords.append(cleaned)

    if len(keywords) > MAX_KEYWORDS:
        # The generator is instructed to order keywords by importance, and
        # Adobe weights the first 10 most heavily, so trimming from the tail
        # preserves the terms that actually drive search ranking.
        keywords = keywords[:MAX_KEYWORDS]
        warnings.append(f"{filename}: keywords trimmed to Adobe's {MAX_KEYWORDS} limit.")

    category = resolve_category(record.category, DEFAULT_CATEGORY)

    row = [
        filename,
        title,
        ", ".join(keywords),
        str(category),
        "",  # Releases - only needed for assets depicting real people/property.
    ]
    return row, warnings


def _render(rows: list[list[str]]) -> str:
    """Serialize rows with Adobe-compatible quoting and line endings."""
    buffer = io.StringIO()
    # QUOTE_MINIMAL keeps the file compact while still quoting the keyword list,
    # which contains commas. Excel and the Contributor Portal both accept this.
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    writer.writerows(rows)
    return buffer.getvalue()


def build_csv(records: list[ImageRecord]) -> CsvBuildResult:
    """Render records into an Adobe Stock CSV document.

    Applies Adobe's hard limits: at most :data:`MAX_ROWS` rows, and the encoded
    document must stay under :data:`MAX_FILE_SIZE_BYTES`. Rows are dropped from
    the tail - never truncated mid-row - so every emitted row stays internally
    valid, and each dropped record is reported in ``overflowed``.

    Args:
        records: Records to include, in the order they should appear.

    Returns:
        A :class:`CsvBuildResult` with the CSV text and any warnings. The
        document always contains the header row, even when no record qualifies.
    """
    skipped: list[str] = []
    warnings: list[str] = []
    overflowed: list[str] = []
    rows: list[list[str]] = []
    row_ids: list[str] = []

    for index, record in enumerate(records):
        if len(rows) >= MAX_ROWS:
            overflowed.extend(item.id for item in records[index:])
            warnings.append(
                f"Stopped at Adobe's {MAX_ROWS}-row limit; "
                f"{len(records) - index} record(s) were left out. "
                "Split them into a second CSV."
            )
            break

        row, row_warnings = build_row(record)
        if not row or not row[0]:
            skipped.append(record.id)
            continue

        rows.append(row)
        row_ids.append(record.id)
        warnings.extend(row_warnings)

    # Enforce the 1 MB ceiling by dropping whole rows from the tail. Each probe
    # re-renders, which is cheap relative to the network round trip that a
    # rejected upload would cost.
    size_trimmed = False
    while rows and len(_render(rows).encode("utf-8")) > MAX_FILE_SIZE_BYTES:
        overflowed.append(row_ids.pop())
        rows.pop()
        size_trimmed = True

    if size_trimmed:
        warnings.append(
            "Trimmed rows to keep the CSV under Adobe's 1 MB file-size limit."
        )

    return CsvBuildResult(
        csv_text=_render(rows),
        row_count=len(rows),
        skipped=skipped,
        warnings=warnings,
        overflowed=overflowed,
    )


def encode_csv_bytes(csv_text: str, *, with_bom: bool = True) -> bytes:
    """Encode CSV text as UTF-8 for download.

    Adobe requires UTF-8. The optional BOM is what makes Excel interpret the
    file as UTF-8 instead of the local ANSI code page, which otherwise mangles
    accented keywords.

    Args:
        csv_text: The rendered CSV document.
        with_bom: Prepend a UTF-8 byte-order mark.

    Returns:
        The encoded document.
    """
    payload = f"{UTF8_BOM}{csv_text}" if with_bom else csv_text
    return payload.encode("utf-8")


def build_csv_filename(prefix: str = "adobe-stock-metadata") -> str:
    """Deterministic CSV filename for the download response."""
    return f"{prefix}.csv"
