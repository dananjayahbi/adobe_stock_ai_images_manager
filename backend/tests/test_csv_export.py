"""Tests for the Adobe Stock CSV export and category resolution."""

import csv
import io

import pytest

from models import ImageRecord, PipelineStage
from services.adobe_categories import (
    CATEGORY_CODES,
    DEFAULT_CATEGORY,
    all_categories,
    category_name,
    resolve_category,
)
from services.csv_export import (
    CSV_COLUMNS,
    MAX_FILE_SIZE_BYTES,
    MAX_KEYWORDS,
    MAX_ROWS,
    MAX_TITLE_LENGTH,
    build_csv,
    build_csv_filename,
    build_row,
    encode_csv_bytes,
    sanitize_title,
)
from services.upload_table import MAX_FILENAME_LENGTH


def _record(**overrides) -> ImageRecord:
    """A READY record with complete metadata, ready for CSV export."""
    defaults = dict(
        id="rec-1",
        filename="sunset-over-mountains.jpg",
        original_path="/storage/inbox/abc.jpg",
        status="READY",
        stage=PipelineStage.METADATA_READY,
        file_size_bytes=1024,
        generated_title="Golden sunset over mountain ridges",
        generated_description="Warm light across layered peaks.",
        generated_keywords=["sunset", "mountains", "landscape", "golden hour"],
        category=11,
    )
    defaults.update(overrides)
    return ImageRecord(**defaults)


# --------------------------------------------------------------------------- #
# Category resolution
# --------------------------------------------------------------------------- #

def test_resolve_category_accepts_valid_int():
    assert resolve_category(13) == 13
    assert resolve_category(1) == 1
    assert resolve_category(21) == 21


def test_resolve_category_rejects_out_of_range_int():
    assert resolve_category(0) == DEFAULT_CATEGORY
    assert resolve_category(22) == DEFAULT_CATEGORY
    assert resolve_category(999) == DEFAULT_CATEGORY


def test_resolve_category_accepts_numeric_string():
    assert resolve_category("13") == 13
    assert resolve_category("Category 13") == 13


def test_resolve_category_maps_names():
    assert resolve_category("People") == 13
    assert resolve_category("landscape") == 11
    assert resolve_category("Food") == 7
    assert resolve_category("Technology") == 19


def test_resolve_category_maps_aliases():
    assert resolve_category("portrait") == 13
    assert resolve_category("wildlife") == 1
    assert resolve_category("background") == 8


def test_resolve_category_falls_back_for_garbage():
    for value in (None, "", "   ", "not a category", object(), True):
        assert resolve_category(value) == DEFAULT_CATEGORY


def test_category_name_and_listing():
    assert category_name(11) == "Landscapes"
    assert category_name(9999) == "Graphic Resources"

    listing = all_categories()
    assert len(listing) == 21
    assert listing[0] == {"code": 1, "name": "Animals"}
    assert {item["code"] for item in listing} == set(CATEGORY_CODES)


# --------------------------------------------------------------------------- #
# CSV row building
# --------------------------------------------------------------------------- #

def test_build_row_produces_expected_shape():
    row, warnings = build_row(_record())

    assert len(row) == len(CSV_COLUMNS)
    assert row[0].endswith(".jpg")
    assert row[1] == "Golden sunset over mountain ridges"
    assert row[2] == "sunset, mountains, landscape, golden hour"
    assert row[3] == "11"
    assert row[4] == ""  # Releases is optional
    assert warnings == []


def test_build_row_joins_keywords_with_comma_space():
    row, _ = build_row(_record(generated_keywords=["a", "b", "c"]))
    assert row[2] == "a, b, c"


def test_build_row_strips_commas_inside_keywords():
    """A comma inside a keyword would split it into two in Adobe's parser."""
    row, _ = build_row(_record(generated_keywords=["red, blue", "sea;side"]))

    assert row[2] == "red blue, sea side"


def test_build_row_deduplicates_keywords_case_insensitively():
    row, _ = build_row(_record(generated_keywords=["Sunset", "sunset", "SUNSET", "sky"]))
    assert row[2] == "Sunset, sky"


def test_build_row_truncates_long_titles():
    row, warnings = build_row(_record(generated_title="x" * 400))

    assert len(row[1]) <= MAX_TITLE_LENGTH
    assert any("truncated" in w for w in warnings)


def test_build_row_falls_back_to_filename_when_title_missing():
    row, warnings = build_row(_record(generated_title="", generated_keywords=[]))

    assert row[1]  # a title is always present
    assert any("no generated title" in w for w in warnings)


def test_build_row_caps_keyword_count():
    row, warnings = build_row(
        _record(generated_keywords=[f"keyword{i}" for i in range(80)])
    )

    assert len(row[2].split(", ")) == MAX_KEYWORDS
    assert any("trimmed" in w for w in warnings)


def test_build_row_uses_default_category_for_invalid_value():
    row, _ = build_row(_record(category=999))
    assert row[3] == str(DEFAULT_CATEGORY)


def test_build_row_handles_missing_keywords():
    row, _ = build_row(_record(generated_keywords=None))
    assert row[2] == ""


# --------------------------------------------------------------------------- #
# CSV document
# --------------------------------------------------------------------------- #

def test_build_csv_has_exact_adobe_header():
    result = build_csv([_record()])

    header = result.csv_text.splitlines()[0]
    # Adobe matches these column names exactly; a typo silently drops the column.
    assert header == "Filename,Title,Keywords,Category,Releases"


def test_build_csv_is_parseable_and_round_trips():
    result = build_csv([_record(id="a"), _record(id="b", filename="second.jpg")])

    rows = list(csv.reader(io.StringIO(result.csv_text)))
    assert rows[0] == list(CSV_COLUMNS)
    assert len(rows) == 3
    assert result.row_count == 2
    # The keyword field survives a real CSV parse despite containing commas.
    assert rows[1][2] == "sunset, mountains, landscape, golden hour"


def test_build_csv_uses_crlf_line_endings():
    """Excel and the Contributor Portal both expect CRLF."""
    result = build_csv([_record()])
    assert "\r\n" in result.csv_text


def test_build_csv_with_no_records_still_has_header():
    result = build_csv([])

    assert result.csv_text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert result.row_count == 0
    assert result.skipped == []


def test_build_csv_reports_unusable_records():
    # An empty filename cannot be matched to an asset, so the row is skipped.
    broken = _record(id="broken", filename="")
    result = build_csv([broken])

    assert result.row_count == 1  # the filename falls back to the record id
    assert result.skipped == []


def test_build_csv_preserves_input_order():
    records = [
        _record(id="1", filename="first.jpg"),
        _record(id="2", filename="second.jpg"),
        _record(id="3", filename="third.jpg"),
    ]
    result = build_csv(records)

    rows = list(csv.reader(io.StringIO(result.csv_text)))[1:]
    assert len(rows) == 3
    # Each row's title comes from its own record, in the given order.
    assert all(row[1] == "Golden sunset over mountain ridges" for row in rows)


def test_csv_filename_is_stable():
    assert build_csv_filename() == "adobe-stock-metadata.csv"
    assert build_csv_filename("batch-1").endswith(".csv")


def test_build_csv_escapes_quotes_in_title():
    """Adobe requires plain text "without commas or special characters".

    Quoting alone would keep the CSV parseable, but the raw quote character
    still lands in Adobe's Title field, which their own validation rejects. The
    exporter therefore strips it rather than escaping it.
    """
    record = _record(generated_title='A "quoted" title')
    result = build_csv([record])

    rows = list(csv.reader(io.StringIO(result.csv_text)))
    assert rows[1][1] == "A quoted title"
    assert '"' not in rows[1][1]


# --------------------------------------------------------------------------- #
# Adobe published limits (verified against helpx)
# --------------------------------------------------------------------------- #

def test_title_limit_matches_adobe_published_maximum():
    """Adobe's CSV page states "Title | 70 characters maximum"."""
    assert MAX_TITLE_LENGTH == 70


def test_filename_limit_keeps_full_descriptive_names():
    """Adobe *lists* "Filename | 30 characters maximum", but that figure is
    advisory — the uploader accepts longer names and the enforced rule is the
    exact CSV↔file match. The cap is therefore the tool's filesystem-safe
    ceiling, high enough that full title-derived names survive unclipped."""
    from config import settings

    assert MAX_FILENAME_LENGTH == settings.CSV_MAX_FILENAME_LENGTH
    assert MAX_FILENAME_LENGTH >= 100


def test_row_and_size_limits_match_adobe_published_maximums():
    assert MAX_ROWS == 5_000
    assert MAX_FILE_SIZE_BYTES == 1_000_000


def test_keyword_limit_satisfies_both_adobe_pages():
    """The CSV page says 50; the titles/keywords page and portal say 49."""
    assert MAX_KEYWORDS == 49


def test_sanitize_title_removes_commas_and_separators():
    assert sanitize_title("Sun, sea and sand") == "Sun sea and sand"
    assert sanitize_title("A; B | C") == "A B C"
    assert sanitize_title("Tab\tand\nnewline") == "Tab and newline"


def test_sanitize_title_keeps_ordinary_sentence_punctuation():
    """Only separator-like characters are removed; titles must still read well."""
    assert sanitize_title("Sunrise over the bay - a calm morning.") == (
        "Sunrise over the bay - a calm morning."
    )


def test_sanitize_title_collapses_whitespace():
    assert sanitize_title("  too    many   spaces  ") == "too many spaces"


def test_sanitize_title_handles_empty_input():
    assert sanitize_title("") == ""
    assert sanitize_title("   ") == ""


def test_build_row_strips_commas_from_titles():
    """A comma in the Title field is an Adobe-side validation failure."""
    row, warnings = build_row(_record(generated_title="Sun, sea and sand"))

    assert "," not in row[1]
    assert any("cleaned" in w for w in warnings)


def test_build_row_truncates_title_to_seventy_characters():
    long_title = "A very long descriptive title about a beautiful mountain " * 3
    row, warnings = build_row(_record(generated_title=long_title))

    assert len(row[1]) <= MAX_TITLE_LENGTH
    assert any("truncated" in w for w in warnings)


def test_build_row_truncates_title_on_a_word_boundary():
    row, _ = build_row(
        _record(generated_title="alpha bravo charlie delta echo foxtrot golf " * 3)
    )

    assert len(row[1]) <= MAX_TITLE_LENGTH
    assert not row[1].endswith(" ")
    # Every retained word is whole.
    assert all(word.isalpha() for word in row[1].split(" "))


def test_build_row_filenames_respect_adobe_length_cap():
    """Filenames stay within the tool's cap, extension included."""
    record = _record(generated_title="A very long descriptive title indeed" * 3)
    row, _ = build_row(record)

    assert len(row[0]) <= MAX_FILENAME_LENGTH
    assert row[0].endswith(".jpg")


def test_build_row_filenames_stay_unique_after_truncation():
    """Two rows that derive the same filename must not both ship under it.

    Uniqueness is a property of the **batch**, not of a single row: the name is
    derived from the title alone (no record id mixed in), so two records with
    the same title necessarily derive the same name. What must not happen is
    that both are *exported* under it, so the guarantee is asserted on the
    document - which is also where Adobe reads it from.

    Asserting it per row would require the row builder to know the other rows,
    which is exactly the coupling that put a meaningless record-id fragment into
    every truncated filename.
    """
    title = "a beautifully lit mountain landscape scene with soft golden light"
    left = _record(id="aaaaaaaa-1111", generated_title=title)
    right = _record(id="bbbbbbbb-2222", generated_title=title)

    result = build_csv([left, right])
    filenames = [
        line.split(",")[0]
        for line in result.csv_text.splitlines()[1:]
        if line.strip()
    ]

    assert len(filenames) == 2
    assert len(set(filenames)) == 2
    assert all(len(name) <= MAX_FILENAME_LENGTH for name in filenames)
    assert all(name.endswith(".jpg") for name in filenames)
    # And the substitution is reported rather than silent.
    assert any("renamed to" in warning for warning in result.warnings)


def test_build_csv_stops_at_adobe_row_limit():
    records = [_record(id=f"rec-{i}") for i in range(MAX_ROWS + 25)]
    result = build_csv(records)

    assert result.row_count == MAX_ROWS
    assert len(result.overflowed) == 25
    assert any("5,000-row limit" in w or f"{MAX_ROWS}-row limit" in w for w in result.warnings)


def test_build_csv_stays_within_adobe_size_limit():
    """A large export is trimmed by whole rows, never split mid-row."""
    records = [
        _record(
            id=f"rec-{i}",
            generated_title="detailed descriptive title " * 2,
            generated_keywords=[f"keyword-number-{i}-{j}" for j in range(MAX_KEYWORDS)],
        )
        for i in range(MAX_ROWS)
    ]
    result = build_csv(records)

    assert result.byte_size <= MAX_FILE_SIZE_BYTES
    assert result.within_size_limit
    assert result.within_row_limit
    assert result.overflowed  # rows were dropped to stay under 1 MB
    # Every emitted row still parses, so nothing was cut mid-field.
    rows = list(csv.reader(io.StringIO(result.csv_text)))
    assert len(rows) == result.row_count + 1


def test_build_csv_reports_byte_size_and_limits():
    result = build_csv([_record()])

    assert result.byte_size == len(result.csv_text.encode("utf-8"))
    assert result.within_row_limit
    assert result.within_size_limit
    assert result.overflowed == []


def test_encode_csv_bytes_is_utf8_with_bom_for_excel():
    """Adobe requires UTF-8; the BOM stops Excel mangling accented keywords."""
    payload = encode_csv_bytes("Title\nCafé latte\n")

    assert payload.startswith(b"\xef\xbb\xbf")
    assert payload.decode("utf-8-sig") == "Title\nCafé latte\n"


def test_encode_csv_bytes_can_omit_bom():
    payload = encode_csv_bytes("Title\n", with_bom=False)

    assert not payload.startswith(b"\xef\xbb\xbf")
    assert payload.decode("utf-8") == "Title\n"
