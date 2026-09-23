"""Tests for the Stage 1 Prompt Library.

The library is the *source* side of the Collector: prompts are written before
the images exist, then images are bound back to them. These tests pin the rules
that make that relationship trustworthy:

- a display title is derived when the operator leaves it blank,
- binding an image automatically marks the prompt used,
- deleting a prompt never deletes the images it produced,
- rebinding an image re-syncs the prompt it left.
"""

import pytest


@pytest.fixture()
def make_record(db_session_factory):
    """Insert an ImageRecord directly, since only the id is needed here."""

    def _make(filename: str = "img.jpg", prompt_id: str | None = None) -> str:
        from models import ImageRecord

        session = db_session_factory()
        record = ImageRecord(
            filename=filename,
            original_path=f"/tmp/{filename}",
            file_size_bytes=1024,
            prompt_id=prompt_id,
        )
        session.add(record)
        session.commit()
        record_id = record.id
        session.close()
        return record_id

    return _make


# --------------------------------------------------------------------------- #
# Creation
# --------------------------------------------------------------------------- #

def test_create_prompt_derives_title_from_body(client):
    """A prompt written without a title is still labelled in the library."""
    response = client.post(
        "/api/prompts",
        json={"body": "A serene ayurvedic herb arrangement. Soft morning light."},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "A serene ayurvedic herb arrangement"
    assert body["status"] == "DRAFT"
    assert body["bound_count"] == 0


def test_create_prompt_keeps_an_explicit_title(client):
    response = client.post(
        "/api/prompts",
        json={"title": "Herb still life", "body": "anything at all"},
    )

    assert response.status_code == 201
    assert response.json()["title"] == "Herb still life"


def test_create_prompt_rejects_an_empty_body(client):
    response = client.post("/api/prompts", json={"body": "   "})

    assert response.status_code == 400
    assert "body is required" in response.json()["detail"]


def test_create_prompt_normalises_tags(client):
    """Tags are trimmed and de-duplicated case-insensitively."""
    response = client.post(
        "/api/prompts",
        json={"body": "x", "tags": [" Herbs ", "herbs", "", "Still Life"]},
    )

    assert response.status_code == 201
    assert response.json()["tags"] == ["Herbs", "Still Life"]


def test_create_prompt_can_start_already_used(client):
    """An operator may record a prompt they know was consumed elsewhere."""
    response = client.post(
        "/api/prompts", json={"body": "x", "status": "USED"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "USED"
    assert body["used_at"] is not None


# --------------------------------------------------------------------------- #
# Listing and filtering
# --------------------------------------------------------------------------- #

def test_list_prompts_reports_used_and_unused_totals(client, make_record):
    first = client.post("/api/prompts", json={"body": "first prompt"}).json()
    client.post("/api/prompts", json={"body": "second prompt"})
    record_id = make_record()
    client.post(f"/api/prompts/{first['id']}/bind", json={"record_ids": [record_id]})

    body = client.get("/api/prompts").json()

    assert body["total"] == 2
    assert body["used"] == 1
    assert body["unused"] == 1


def test_list_prompts_used_filter_is_derived_from_bindings(client, make_record):
    """`used` means an image is bound — not merely that the status says USED."""
    bound = client.post("/api/prompts", json={"body": "bound prompt"}).json()
    client.post("/api/prompts", json={"body": "flagged but empty", "status": "USED"})
    record_id = make_record()
    client.post(f"/api/prompts/{bound['id']}/bind", json={"record_ids": [record_id]})

    used = client.get("/api/prompts", params={"status": "used"}).json()
    unused = client.get("/api/prompts", params={"status": "unused"}).json()

    assert [item["id"] for item in used["items"]] == [bound["id"]]
    assert len(unused["items"]) == 1
    assert unused["items"][0]["id"] != bound["id"]


def test_list_prompts_rejects_an_unknown_filter(client):
    response = client.get("/api/prompts", params={"status": "nonsense"})

    assert response.status_code == 400
    assert "Invalid status" in response.json()["detail"]


def test_get_prompt_404s_for_a_missing_id(client):
    response = client.get("/api/prompts/does-not-exist")

    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Binding — the core of the feature
# --------------------------------------------------------------------------- #

def test_binding_an_image_marks_the_prompt_used(client, make_record):
    """Binding is the whole point: one prompt, many images, auto-marked used."""
    prompt = client.post("/api/prompts", json={"body": "herbs"}).json()
    ids = [make_record(f"a{index}.jpg") for index in range(3)]

    response = client.post(
        f"/api/prompts/{prompt['id']}/bind", json={"record_ids": ids}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 3
    assert body["prompt"]["bound_count"] == 3
    assert body["prompt"]["status"] == "USED"
    assert body["prompt"]["used_at"] is not None


def test_binding_is_recorded_on_the_records(client, make_record):
    """The link must be visible from the image side, not only the prompt side."""
    prompt = client.post("/api/prompts", json={"body": "herbs"}).json()
    record_id = make_record()

    client.post(f"/api/prompts/{prompt['id']}/bind", json={"record_ids": [record_id]})

    listing = client.get("/api/records").json()
    assert listing["items"][0]["prompt_id"] == prompt["id"]


def test_records_can_be_filtered_by_prompt(client, make_record):
    prompt = client.post("/api/prompts", json={"body": "herbs"}).json()
    linked = make_record("linked.jpg")
    make_record("loose.jpg")
    client.post(f"/api/prompts/{prompt['id']}/bind", json={"record_ids": [linked]})

    linked_only = client.get("/api/records", params={"prompt_id": prompt["id"]}).json()
    unlinked = client.get("/api/records", params={"prompt_id": "none"}).json()

    assert [item["id"] for item in linked_only["items"]] == [linked]
    assert [item["filename"] for item in unlinked["items"]] == ["loose.jpg"]


def test_unbind_clears_the_link_but_keeps_the_prompt_used(client, make_record):
    """Unbinding is not an implicit "mark unused" — that stays a manual choice.

    The operator may have consumed the prompt elsewhere, and silently reverting
    an explicit "mark as used" would be worse than leaving it.
    """
    prompt = client.post("/api/prompts", json={"body": "herbs"}).json()
    record_id = make_record()
    client.post(f"/api/prompts/{prompt['id']}/bind", json={"record_ids": [record_id]})

    response = client.post(
        f"/api/prompts/{prompt['id']}/bind",
        json={"record_ids": [record_id], "unbind": True},
    )

    body = response.json()
    assert body["updated"] == 1
    assert body["prompt"]["bound_count"] == 0
    assert body["prompt"]["status"] == "USED"

    listing = client.get("/api/records").json()
    assert listing["items"][0]["prompt_id"] is None


def test_rebinding_an_image_moves_it_off_the_old_prompt(client, make_record):
    """One image belongs to one prompt, so a re-bind must not leave it in two."""
    first = client.post("/api/prompts", json={"body": "first"}).json()
    second = client.post("/api/prompts", json={"body": "second"}).json()
    record_id = make_record()
    client.post(f"/api/prompts/{first['id']}/bind", json={"record_ids": [record_id]})

    response = client.post(
        f"/api/prompts/{second['id']}/bind", json={"record_ids": [record_id]}
    )

    assert response.json()["rebound"] == [record_id]
    # The prompt that lost its only image must not keep claiming it.
    assert client.get(f"/api/prompts/{first['id']}").json()["bound_count"] == 0
    assert client.get(f"/api/prompts/{second['id']}").json()["bound_count"] == 1


def test_bind_reports_missing_records(client):
    prompt = client.post("/api/prompts", json={"body": "herbs"}).json()

    response = client.post(
        f"/api/prompts/{prompt['id']}/bind", json={"record_ids": ["ghost"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 0
    assert body["missing"] == ["ghost"]


def test_bind_rejects_an_empty_selection(client):
    prompt = client.post("/api/prompts", json={"body": "herbs"}).json()

    response = client.post(f"/api/prompts/{prompt['id']}/bind", json={"record_ids": []})

    assert response.status_code == 400


def test_bind_404s_for_a_missing_prompt(client):
    response = client.post("/api/prompts/nope/bind", json={"record_ids": ["a"]})

    assert response.status_code == 404


def test_bind_is_idempotent(client, make_record):
    """Re-binding the same image must not inflate the count."""
    prompt = client.post("/api/prompts", json={"body": "herbs"}).json()
    record_id = make_record()

    client.post(f"/api/prompts/{prompt['id']}/bind", json={"record_ids": [record_id]})
    client.post(f"/api/prompts/{prompt['id']}/bind", json={"record_ids": [record_id]})

    assert client.get(f"/api/prompts/{prompt['id']}").json()["bound_count"] == 1


# --------------------------------------------------------------------------- #
# Editing and status
# --------------------------------------------------------------------------- #

def test_patch_leaves_untouched_fields_alone(client):
    """A real PATCH: omitted fields must not be cleared."""
    prompt = client.post(
        "/api/prompts",
        json={"title": "Original", "body": "original body", "tags": ["keep"]},
    ).json()

    response = client.patch(f"/api/prompts/{prompt['id']}", json={"body": "new body"})

    body = response.json()
    assert body["body"] == "new body"
    assert body["title"] == "Original"
    assert body["tags"] == ["keep"]


def test_patch_blank_title_falls_back_to_the_derived_one(client):
    prompt = client.post("/api/prompts", json={"body": "first line here"}).json()

    response = client.patch(f"/api/prompts/{prompt['id']}", json={"title": "   "})

    assert response.json()["title"] == "first line here"


def test_patch_can_mark_a_prompt_used_by_hand(client):
    """Explicit marking is supported even with no image bound."""
    prompt = client.post("/api/prompts", json={"body": "herbs"}).json()

    response = client.patch(f"/api/prompts/{prompt['id']}", json={"status": "USED"})

    body = response.json()
    assert body["status"] == "USED"
    assert body["used_at"] is not None
    assert body["bound_count"] == 0


def test_marking_a_bound_prompt_draft_is_overridden(client, make_record):
    """Binding implies used, so a hand-set DRAFT cannot stick while bound."""
    prompt = client.post("/api/prompts", json={"body": "herbs"}).json()
    record_id = make_record()
    client.post(f"/api/prompts/{prompt['id']}/bind", json={"record_ids": [record_id]})

    response = client.patch(f"/api/prompts/{prompt['id']}", json={"status": "DRAFT"})

    assert response.json()["status"] == "USED"


def test_clearing_the_status_back_to_draft_clears_used_at(client):
    prompt = client.post(
        "/api/prompts", json={"body": "herbs", "status": "USED"}
    ).json()

    response = client.patch(f"/api/prompts/{prompt['id']}", json={"status": "DRAFT"})

    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["used_at"] is None


def test_patch_rejects_an_empty_body(client):
    prompt = client.post("/api/prompts", json={"body": "herbs"}).json()

    response = client.patch(f"/api/prompts/{prompt['id']}", json={"body": "  "})

    assert response.status_code == 400


# --------------------------------------------------------------------------- #
# Deletion
# --------------------------------------------------------------------------- #

def test_deleting_a_prompt_keeps_and_unbinds_its_images(client, make_record):
    """Deleting a prompt must never delete the assets it produced."""
    prompt = client.post("/api/prompts", json={"body": "herbs"}).json()
    record_id = make_record()
    client.post(f"/api/prompts/{prompt['id']}/bind", json={"record_ids": [record_id]})

    response = client.delete(f"/api/prompts/{prompt['id']}")

    assert response.status_code == 200
    assert response.json() == {"deleted": 1, "unbound": 1}

    listing = client.get("/api/records").json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == record_id
    assert listing["items"][0]["prompt_id"] is None


def test_deleting_a_prompt_404s_when_missing(client):
    assert client.delete("/api/prompts/ghost").status_code == 404


# --------------------------------------------------------------------------- #
# Title derivation (unit)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("", "Untitled prompt"),
        ("   \n  ", "Untitled prompt"),
        ("A serene arrangement", "A serene arrangement"),
        ("First sentence. Second sentence.", "First sentence"),
        ("\n\n  Leading blank lines  \nmore", "Leading blank lines"),
    ],
)
def test_derive_title_cases(body, expected):
    from services import prompt_library

    assert prompt_library.derive_title(body) == expected


def test_derive_title_truncates_a_very_long_line():
    from services import prompt_library

    title = prompt_library.derive_title("word " * 200)

    assert len(title) <= prompt_library.MAX_TITLE_LENGTH
    assert title.endswith("…")


def test_normalise_tags_returns_none_when_nothing_survives():
    from services import prompt_library

    assert prompt_library.normalise_tags(["", "  "]) is None
    assert prompt_library.normalise_tags(None) is None
