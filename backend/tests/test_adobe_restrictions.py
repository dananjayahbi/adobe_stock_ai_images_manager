"""Tests for the Adobe known-restrictions blocklist.

The list is large and mostly proper nouns, so the risk here is not missing an
entry - it is *over*-matching. A blocklist that flags "police" or "currency"
would reject a large share of legitimate commercial content, so several of these
tests exist specifically to pin down what must NOT match.
"""

import pytest

from services.adobe_restrictions import (
    find_restricted_terms,
    restricted_count,
    scan_metadata,
)


# --------------------------------------------------------------------------- #
# Matching real restricted subjects
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "text,expected",
    [
        ("A red sneaker with a swoosh", None),  # no name given, so no match
        ("Nike running shoes on a track", "nike"),
        ("Disney castle at night", "disney"),
        ("A Lego brick tower", "lego"),
        ("The Eiffel Tower in spring", "eiffel tower"),
        ("Hollywood Sign on a hillside", "hollywood sign"),
        ("Burj Khalifa from below", "burj khalifa"),
        ("A Rubik's Cube on a desk", "rubik's cube"),
        ("Sydney Opera House at dusk", "sydney opera house"),
        ("Albert Einstein portrait", "albert einstein"),
        ("Statue of Liberty in the harbour", "statue of liberty"),
        ("An Olympic Symbols banner", "olympic symbols"),
        ("A Coca-Cola style red can", None),  # not in Adobe's published list
    ],
)
def test_known_restricted_subjects_are_detected(text, expected):
    found = find_restricted_terms(text)
    if expected is None:
        assert found == []
    else:
        assert expected in found


def test_matching_is_case_insensitive():
    """Restricted names are matched whatever their case.

    Only the short, genuinely ambiguous tokens (oscar, ups, peeps) require a
    capitalised form; distinctive names like Nike match in any case.
    """
    assert "nike" in find_restricted_terms("NIKE AIR MAX")
    assert "nike" in find_restricted_terms("nike air max")
    assert "disney" in find_restricted_terms("a disney-style castle")
    assert "lego" in find_restricted_terms("colourful lego bricks")


def test_longest_match_wins_for_overlapping_names():
    """'Burj Khalifa' must not be reported as the shorter 'burj' fragment."""
    found = find_restricted_terms("Burj Khalifa at sunset")
    assert "burj khalifa" in found


def test_multiple_restricted_subjects_in_one_string():
    found = find_restricted_terms("A Lego set beside a Disney poster")

    assert "lego" in found
    assert "disney" in found


def test_duplicate_mentions_are_reported_once():
    found = find_restricted_terms("Nike shoes and more Nike shoes")
    assert found.count("nike") == 1


# --------------------------------------------------------------------------- #
# Avoiding false positives - the important half
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "text",
    [
        "A group of friends at a cafe",
        "Groups of people walking",
        "A friendly golden retriever on a beach",
        "Police officers directing traffic",
        "Currency exchange rates on a screen",
        "Public transportation in a busy city",
        "A smiley face drawn in sand",
        "An abstract geometric background",
        "Mountains at sunrise",
        "Fresh vegetables on a wooden table",
    ],
)
def test_ordinary_commercial_content_is_not_flagged(text):
    """Generic words from Adobe's list must not trigger a match.

    Adobe's list contains entries such as "Currency", "Police Forces", and
    "Public transportation". Matching those literally would flag a large share of
    legitimate stock content, so they are excluded from the matcher.
    """
    assert find_restricted_terms(text) == []


def test_lowercase_ambiguous_tokens_are_ignored():
    """'ups' and 'oscar' are ordinary substrings far more often than brands."""
    assert find_restricted_terms("he quickly ups the pace") == []
    assert find_restricted_terms("she ups her game") == []


def test_capitalised_ambiguous_tokens_are_flagged():
    assert "ups" in find_restricted_terms("UPS delivery van")
    assert "oscar" in find_restricted_terms("Oscar statuette on a shelf")


def test_word_boundaries_prevent_partial_matches():
    """'Nike' inside a longer word must not match."""
    assert find_restricted_terms("snikeboard") == []


# --------------------------------------------------------------------------- #
# Aggregation helpers
# --------------------------------------------------------------------------- #

def test_scan_metadata_accepts_strings_and_lists():
    found = scan_metadata(
        "A sports scene",
        ["running", "Nike shoes", "outdoor"],
        "Shot beside the Eiffel Tower",
    )

    assert "nike" in found
    assert "eiffel tower" in found


def test_scan_metadata_ignores_none_and_empty():
    assert scan_metadata(None, "", [], []) == []


def test_scan_metadata_handles_non_string_values():
    assert scan_metadata(12345, ["ok"], None) == []


def test_restricted_count_is_substantial():
    """The list should cover the bulk of Adobe's published entries."""
    assert restricted_count() > 200
