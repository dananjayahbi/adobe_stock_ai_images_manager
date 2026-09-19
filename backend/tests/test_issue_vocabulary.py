"""Guard test: the frontend's issue vocabulary must match the backend's.

The UI derives its "auto-fixable" badge from a mirrored list in
``frontend/src/lib/acceptanceIssues.ts`` rather than from the report's cached
``refinable`` flag, because a persisted report is a snapshot taken before the
engine gained new capabilities.

That mirroring is only safe if the two lists cannot silently drift apart, which
is what this test enforces. It parses the TypeScript module and compares the
arrays to the Python frozensets.
"""

import re
from pathlib import Path

import pytest

from services.acceptance import types as issue_types

FRONTEND_MODULE = (
    Path(__file__).resolve().parent.parent.parent
    / "frontend"
    / "src"
    / "lib"
    / "acceptanceIssues.ts"
)


def _extract_ts_array(source: str, name: str) -> set[str]:
    """Pull the string literals out of an exported `const NAME = [...]` array."""
    match = re.search(
        rf"export const {name}\s*(?::[^=]+)?=\s*\[(.*?)\]\s*as const",
        source,
        re.DOTALL,
    )
    if not match:
        # Also accept a non-`as const` array (AUTOFIXABLE_CODES is a spread).
        match = re.search(
            rf"export const {name}\s*(?::[^=]+)?=\s*\[(.*?)\];",
            source,
            re.DOTALL,
        )
    assert match, f"could not find {name} in {FRONTEND_MODULE}"
    return set(re.findall(r'"([a-z_]+)"', match.group(1)))


@pytest.fixture(scope="module")
def frontend_source() -> str:
    if not FRONTEND_MODULE.is_file():
        pytest.skip(f"frontend module not found at {FRONTEND_MODULE}")
    return FRONTEND_MODULE.read_text(encoding="utf-8")


def test_frontend_lists_the_same_pixel_fixable_codes(frontend_source):
    assert _extract_ts_array(frontend_source, "PIXEL_FIXABLE_CODES") == set(
        issue_types.REFINABLE_CODES
    )


def test_frontend_lists_the_same_container_fixable_codes(frontend_source):
    assert _extract_ts_array(frontend_source, "CONTAINER_FIXABLE_CODES") == set(
        issue_types.CONTAINER_FIXABLE_CODES
    )


def test_frontend_lists_the_same_manual_only_codes(frontend_source):
    assert _extract_ts_array(frontend_source, "MANUAL_ONLY_CODES") == set(
        issue_types.MANUAL_ONLY_CODES
    )


def test_autofixable_is_the_union_of_pixel_and_container(frontend_source):
    pixel = _extract_ts_array(frontend_source, "PIXEL_FIXABLE_CODES")
    container = _extract_ts_array(frontend_source, "CONTAINER_FIXABLE_CODES")
    assert pixel | container == set(issue_types.AUTOFIXABLE_CODES)


def test_every_issue_code_has_a_frontend_label(frontend_source):
    """An unlabelled code would render as a raw identifier in the UI."""
    labels = set(
        re.findall(r'^\s*([a-z_]+):\s*"', frontend_source, re.MULTILINE)
    )
    missing = set(issue_types.ISSUE_CODES) - labels
    assert not missing, f"issue codes with no frontend label: {sorted(missing)}"
