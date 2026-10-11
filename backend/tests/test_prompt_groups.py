"""Tests for prompt folders (grouping) in the library.

The defect this guards: prompts used as a batch have no way to be selected
together - a folder assignment that silently drops ids, clears on a PATCH, or
fails to filter the list would look exactly like working grouping until the
operator's batch selection goes missing.
"""

from __future__ import annotations

import pytest


def _create(client, body: str, **extra) -> dict:
    response = client.post("/api/prompts", json={"body": body, **extra})
    assert response.status_code == 201, response.text
    return response.json()


class TestGroupOnCreateAndUpdate:
    def test_create_with_group(self, client):
        prompt = _create(client, "misty forest", group_name="Nature batch")
        assert prompt["group_name"] == "Nature batch"

    def test_create_normalises_group_whitespace(self, client):
        prompt = _create(client, "cliffs", group_name="  Coast   batch  ")
        assert prompt["group_name"] == "Coast batch"

    def test_blank_group_stays_null(self, client):
        prompt = _create(client, "harbor", group_name="   ")
        assert prompt["group_name"] is None

    def test_patch_sets_and_clears_group(self, client):
        prompt = _create(client, "dunes")
        updated = client.patch(
            f"/api/prompts/{prompt['id']}", json={"group_name": "Desert set"}
        ).json()
        assert updated["group_name"] == "Desert set"

        cleared = client.patch(
            f"/api/prompts/{prompt['id']}", json={"group_name": ""}
        ).json()
        assert cleared["group_name"] is None

    def test_patch_without_group_key_leaves_it_alone(self, client):
        prompt = _create(client, "reef", group_name="Underwater")
        updated = client.patch(
            f"/api/prompts/{prompt['id']}", json={"title": "Coral reef"}
        ).json()
        assert updated["group_name"] == "Underwater"


class TestGroupFilterAndCounts:
    def test_group_filter_narrows_items_only(self, client):
        _create(client, "one", group_name="Batch A")
        _create(client, "two", group_name="Batch A")
        _create(client, "three", group_name="Batch B")
        _create(client, "four")  # ungrouped

        response = client.get("/api/prompts", params={"group": "Batch A"})
        data = response.json()
        assert len(data["items"]) == 2
        assert all(item["group_name"] == "Batch A" for item in data["items"])
        # Groups are served with the list so chips cannot drift from rows.
        groups = {g["name"]: g["count"] for g in data["groups"]}
        assert groups == {"Batch A": 2, "Batch B": 1}

    def test_empty_group_matches_everything(self, client):
        _create(client, "one", group_name="Batch A")
        _create(client, "two")
        data = client.get("/api/prompts").json()
        assert len(data["items"]) == 2

    def test_group_filter_combines_with_search(self, client):
        _create(client, "mountain sunrise", group_name="Skies")
        _create(client, "mountain lake", group_name="Water")
        data = client.get(
            "/api/prompts", params={"q": "mountain", "group": "Skies"}
        ).json()
        assert [i["title"] for i in data["items"]] == ["mountain sunrise"]


class TestBulkGroupAssign:
    def test_assign_moves_selection_in_one_round_trip(self, client):
        first = _create(client, "alpha")
        second = _create(client, "beta")
        third = _create(client, "gamma")

        response = client.post(
            "/api/prompts/group",
            json={"prompt_ids": [first["id"], second["id"]], "group_name": "Batch 1"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["updated"] == 2
        assert body["missing"] == []
        assert body["group_name"] == "Batch 1"

        listed = client.get("/api/prompts", params={"group": "Batch 1"}).json()
        assert len(listed["items"]) == 2
        # The third prompt was not part of the selection.
        assert third["id"] not in {i["id"] for i in listed["items"]}

    def test_empty_group_name_clears_the_folder(self, client):
        prompt = _create(client, "delta", group_name="Old batch")
        body = client.post(
            "/api/prompts/group",
            json={"prompt_ids": [prompt["id"]], "group_name": ""},
        ).json()
        assert body["group_name"] is None
        fetched = client.get(f"/api/prompts/{prompt['id']}").json()
        assert fetched["group_name"] is None

    def test_duplicate_ids_count_once(self, client):
        prompt = _create(client, "epsilon")
        body = client.post(
            "/api/prompts/group",
            json={
                "prompt_ids": [prompt["id"], prompt["id"], prompt["id"]],
                "group_name": "Batch 2",
            },
        ).json()
        assert body["updated"] == 1

    def test_unknown_ids_land_in_missing(self, client):
        prompt = _create(client, "zeta")
        body = client.post(
            "/api/prompts/group",
            json={"prompt_ids": [prompt["id"], "does-not-exist"], "group_name": "Batch 3"},
        ).json()
        assert body["updated"] == 1
        assert body["missing"] == ["does-not-exist"]

    def test_empty_selection_is_400(self, client):
        response = client.post(
            "/api/prompts/group", json={"prompt_ids": [], "group_name": "x"}
        )
        assert response.status_code == 400

    def test_oversized_selection_is_400(self, client):
        response = client.post(
            "/api/prompts/group",
            json={
                # Unique ids: the endpoint dedupes before applying the cap.
                "prompt_ids": [f"p{i}" for i in range(501)],
                "group_name": "huge",
            },
        )
        assert response.status_code == 400
        assert "500" in response.json()["detail"]
