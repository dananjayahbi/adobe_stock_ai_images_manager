"""Tests for near-duplicate detection.

Adobe names similar content as one of the top reasons it refuses submissions,
and calls out four distinct patterns. These tests exercise both signals:
perceptual-hash distance for the visual patterns, and metadata similarity for
the "different images, identical titles and keywords" pattern.
"""

import numpy as np
import pytest

from services.duplicate_detector import (
    METADATA_SIMILARITY_THRESHOLD,
    VISUAL_DUPLICATE_DISTANCE,
    DuplicateCandidate,
    dhash,
    find_duplicate_pairs,
    group_duplicates,
    hamming_distance,
    hash_image_file,
    metadata_similarity,
    tokenize_metadata,
    visual_similarity,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _gradient(seed: int = 0, shift: int = 0, invert: bool = False) -> np.ndarray:
    """A deterministic, structured BGR image.

    A smooth gradient alone hashes too uniformly to discriminate; the added
    block gives the hash real structure to lock onto. ``invert`` flips the
    gradient direction so two images can be structurally unrelated rather than
    merely noise-different.
    """
    rng = np.random.default_rng(seed)
    base = np.zeros((128, 128, 3), dtype=np.uint8)
    ramp = np.linspace(20, 235, 128, dtype=np.uint8)
    base[:, :, 0] = (255 - ramp)[None, :] if invert else ramp[None, :]
    base[:, :, 1] = np.linspace(30, 200, 128, dtype=np.uint8)[:, None]
    base[:, :, 2] = 90 if not invert else 200
    # A recognisable, shiftable feature.
    row = 40 + shift
    base[row : row + 24, 30:70] = 240 if not invert else 10
    # Low-amplitude noise keeps the hash from collapsing on flat regions.
    noise = rng.integers(-6, 7, base.shape, dtype=np.int16)
    return np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------- #
# Hashing
# --------------------------------------------------------------------------- #

def test_dhash_is_stable_for_the_same_image():
    image = _gradient(seed=3)
    assert dhash(image) == dhash(image.copy())


def test_dhash_is_a_64_bit_value():
    value = dhash(_gradient())
    assert 0 <= value < (1 << 64)


def test_dhash_differs_for_different_images():
    assert dhash(_gradient(seed=1)) != dhash(_gradient(seed=99, shift=40, invert=True))


def test_dhash_tolerates_small_perturbations():
    """Re-encoding or a tiny shift must not change the hash dramatically."""
    base = _gradient(seed=5)
    shifted = np.roll(base, 1, axis=1)

    distance = hamming_distance(dhash(base), dhash(shifted))
    assert distance <= VISUAL_DUPLICATE_DISTANCE


def test_dhash_handles_empty_input():
    assert dhash(np.zeros((0, 0, 3), dtype=np.uint8)) == 0


def test_hash_image_file_returns_zero_for_missing_file(tmp_path):
    assert hash_image_file(tmp_path / "nope.jpg") == 0


def test_hash_image_file_reads_a_real_file(tmp_path):
    import cv2

    path = tmp_path / "image.png"
    cv2.imwrite(str(path), _gradient())

    assert hash_image_file(path) != 0


# --------------------------------------------------------------------------- #
# Distance / similarity maths
# --------------------------------------------------------------------------- #

def test_hamming_distance_of_identical_hashes_is_zero():
    assert hamming_distance(12345, 12345) == 0


def test_hamming_distance_counts_differing_bits():
    assert hamming_distance(0b0000, 0b1010) == 2


def test_visual_similarity_is_one_for_identical_hashes():
    assert visual_similarity(999, 999) == 1.0


def test_visual_similarity_is_zero_for_opposite_hashes():
    assert visual_similarity(0, (1 << 64) - 1) == 0.0


# --------------------------------------------------------------------------- #
# Metadata similarity
# --------------------------------------------------------------------------- #

def test_tokenize_metadata_drops_stopwords_and_short_tokens():
    tokens = tokenize_metadata("A photo of the sea", ["the", "ocean", "a"])

    assert "sea" in tokens
    assert "ocean" in tokens
    # Stopwords and single characters carry no discriminating information.
    assert "the" not in tokens
    assert "a" not in tokens
    assert "photo" not in tokens


def test_tokenize_metadata_handles_missing_values():
    assert tokenize_metadata(None, None) == frozenset()
    assert tokenize_metadata("", []) == frozenset()


def test_metadata_similarity_is_one_for_identical_sets():
    tokens = tokenize_metadata("sunset over mountains", ["sunset", "mountains"])
    assert metadata_similarity(tokens, tokens) == 1.0


def test_metadata_similarity_is_zero_for_disjoint_sets():
    left = tokenize_metadata("sunset mountains", [])
    right = tokenize_metadata("office desk laptop", [])
    assert metadata_similarity(left, right) == 0.0


def test_metadata_similarity_is_zero_for_empty_input():
    assert metadata_similarity(frozenset(), frozenset({"a"})) == 0.0


# --------------------------------------------------------------------------- #
# Pair detection
# --------------------------------------------------------------------------- #

def _candidate(record_id: str, image: np.ndarray, title: str, keywords: list[str]):
    return DuplicateCandidate(
        record_id=record_id,
        hash_value=dhash(image),
        tokens=tokenize_metadata(title, keywords),
    )


def test_visually_identical_images_are_paired():
    image = _gradient(seed=11)
    candidates = [
        _candidate("a", image, "Mountain ridge at dawn", ["mountain", "dawn"]),
        _candidate("b", image.copy(), "Coastal cliffs at dusk", ["coast", "dusk"]),
    ]

    pairs = find_duplicate_pairs(candidates)

    assert len(pairs) == 1
    assert pairs[0].reason == "visual"
    assert pairs[0].visual_score == 1.0


def test_different_images_with_reused_metadata_are_paired():
    """Adobe lists this pattern explicitly: identical titles and keywords."""
    shared_title = "Modern office workspace with laptop and coffee"
    shared_keywords = ["office", "workspace", "laptop", "coffee", "business"]

    candidates = [
        _candidate("a", _gradient(seed=1), shared_title, shared_keywords),
        _candidate(
            "b",
            _gradient(seed=77, shift=50, invert=True),
            shared_title,
            shared_keywords,
        ),
    ]

    pairs = find_duplicate_pairs(candidates)

    assert len(pairs) == 1
    assert pairs[0].metadata_score >= METADATA_SIMILARITY_THRESHOLD
    assert pairs[0].reason in ("metadata", "both")


def test_genuinely_different_records_are_not_paired():
    candidates = [
        _candidate(
            "a",
            _gradient(seed=1),
            "Sunrise over a quiet mountain lake",
            ["sunrise", "mountain", "lake", "calm"],
        ),
        _candidate(
            "b",
            _gradient(seed=250, shift=60, invert=True),
            "Busy city intersection with yellow taxis",
            ["city", "traffic", "taxi", "urban"],
        ),
    ]

    assert find_duplicate_pairs(candidates) == []


def test_pairs_are_returned_strongest_first():
    image = _gradient(seed=21)
    candidates = [
        _candidate("a", image, "Shared title here", ["alpha", "beta"]),
        _candidate("b", image.copy(), "Shared title here", ["alpha", "beta"]),
        _candidate("c", _gradient(seed=200, shift=55), "Totally different", ["gamma"]),
    ]

    pairs = find_duplicate_pairs(candidates)

    scores = [(pair.visual_score + pair.metadata_score) / 2 for pair in pairs]
    assert scores == sorted(scores, reverse=True)


def test_single_candidate_yields_no_pairs():
    candidates = [_candidate("a", _gradient(), "Solo", ["one"])]
    assert find_duplicate_pairs(candidates) == []


def test_unreadable_images_are_not_treated_as_visual_duplicates():
    """A hash of 0 means "unreadable", not "identical".

    Two files that could not be decoded both hash to 0, so comparing them
    directly would report a perfect visual match between images that were never
    actually seen. Only the metadata signal may pair them.
    """
    left = DuplicateCandidate(record_id="a", hash_value=0, tokens=frozenset({"alpha"}))
    right = DuplicateCandidate(record_id="b", hash_value=0, tokens=frozenset({"beta"}))

    assert find_duplicate_pairs([left, right]) == []


def test_unreadable_images_can_still_pair_on_metadata():
    """When the pixels are unavailable, reused metadata is still a valid signal."""
    shared = frozenset({"office", "desk", "laptop"})
    left = DuplicateCandidate(record_id="a", hash_value=0, tokens=shared)
    right = DuplicateCandidate(record_id="b", hash_value=0, tokens=shared)

    pairs = find_duplicate_pairs([left, right])

    assert len(pairs) == 1
    assert pairs[0].reason == "metadata"
    assert pairs[0].visual_score == 0.0


def test_empty_candidate_list_is_safe():
    assert find_duplicate_pairs([]) == []


# --------------------------------------------------------------------------- #
# Grouping
# --------------------------------------------------------------------------- #

def test_group_duplicates_clusters_a_chain():
    """A-B and B-C similar must produce one group of three, not two pairs."""
    image = _gradient(seed=31)
    candidates = [
        _candidate("a", image, "Shared title", ["alpha", "beta", "gamma"]),
        _candidate("b", image.copy(), "Shared title", ["alpha", "beta", "gamma"]),
        _candidate("c", image.copy(), "Shared title", ["alpha", "beta", "gamma"]),
    ]

    groups = group_duplicates(find_duplicate_pairs(candidates))

    assert len(groups) == 1
    assert groups[0].record_ids == ["a", "b", "c"]


def test_group_duplicates_suggests_keeping_five():
    """Adobe advises submitting three to five per subject, angle, or pose."""
    image = _gradient(seed=41)
    candidates = [
        _candidate(f"rec-{i}", image.copy(), "Shared title", ["alpha", "beta"])
        for i in range(8)
    ]

    groups = group_duplicates(find_duplicate_pairs(candidates))

    assert len(groups) == 1
    assert len(groups[0].suggested_keep) == 5
    assert len(groups[0].suggested_drop) == 3
    assert set(groups[0].suggested_keep) | set(groups[0].suggested_drop) == set(
        groups[0].record_ids
    )


def test_group_duplicates_respects_custom_keep_count():
    image = _gradient(seed=51)
    candidates = [
        _candidate(f"rec-{i}", image.copy(), "Shared title", ["alpha", "beta"])
        for i in range(4)
    ]

    groups = group_duplicates(find_duplicate_pairs(candidates), keep_per_group=2)

    assert len(groups[0].suggested_keep) == 2


def test_group_duplicates_returns_nothing_for_no_pairs():
    assert group_duplicates([]) == []


def test_group_and_pair_dicts_are_json_ready():
    image = _gradient(seed=61)
    candidates = [
        _candidate("a", image, "Shared", ["alpha"]),
        _candidate("b", image.copy(), "Shared", ["alpha"]),
    ]
    pairs = find_duplicate_pairs(candidates)
    groups = group_duplicates(pairs)

    pair_dict = pairs[0].to_dict()
    assert set(pair_dict) == {
        "left_id",
        "right_id",
        "visual_score",
        "metadata_score",
        "reason",
    }
    assert isinstance(pair_dict["visual_score"], float)

    group_dict = groups[0].to_dict()
    assert set(group_dict) == {
        "record_ids",
        "reason",
        "suggested_keep",
        "suggested_drop",
    }
