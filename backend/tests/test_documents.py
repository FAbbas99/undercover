"""The documents, split into the sections a handler looks up."""

import pytest
from fastapi.testclient import TestClient

from backend.db import DATA
from backend.documents import find, outline, read_document
from backend.main import HERE, app

client = TestClient(app)
MANUAL = (DATA / "claims_manual.md").read_text(encoding="utf-8")
WORDING = (DATA / "policy_wording.md").read_text(encoding="utf-8")


def test_the_manual_splits_into_its_sections():
    document = read_document(MANUAL)
    assert [s["section"] for s in document["sections"]] == [
        str(number) for number in range(1, 15)
    ]
    assert find(document, "6")["title"] == "Working out the payout"
    assert document["preamble"].startswith("# UnderCover Claims Handling Manual")


def test_the_wording_splits_into_its_sections():
    document = read_document(WORDING)
    assert len(document["sections"]) == 12
    assert find(document, "5")["title"] == "Baggage and Personal Effects"


def test_the_sections_rebuild_the_document():
    for text in (MANUAL, WORDING):
        document = read_document(text)
        parts = [document["preamble"], *[s["text"] for s in document["sections"]]]
        assert "\n\n".join(parts) + "\n" == text


def test_a_document_with_no_sections():
    document = read_document("Just a note.\n")
    assert document == {"preamble": "Just a note.", "sections": []}
    assert outline(document) == []


def test_an_unknown_section_raises():
    with pytest.raises(KeyError):
        find(read_document(MANUAL), "99")


def test_the_manual_endpoints():
    sections = client.get("/api/manual/sections").json()
    assert sections[0] == {"section": "1", "title": "Purpose and scope"}
    assert len(sections) == 14
    section = client.get("/api/manual/6").json()
    assert section["title"] == "Working out the payout"
    assert section["text"].startswith("## 6. Working out the payout")
    assert "Worked example 1" in section["text"]


def test_the_wording_endpoints():
    assert len(client.get("/api/policy-wording/sections").json()) == 12
    section = client.get("/api/policy-wording/5").json()
    assert section["title"] == "Baggage and Personal Effects"
    assert section["text"] in WORDING


def test_an_unknown_section_is_refused():
    assert client.get("/api/manual/99").status_code == 404
    assert client.get("/api/policy-wording/99").status_code == 404


def test_the_whole_documents_are_no_longer_served():
    assert client.get("/api/policy-wording").status_code == 404
    assert client.get("/api/instructions").status_code == 404


def test_the_instructions_come_from_the_files():
    assert client.get("/api/instructions/queue").json()["text"] == (
        HERE / "instructions_queue.md"
    ).read_text(encoding="utf-8")
    assert client.get("/api/instructions/claim").json()["text"] == (
        HERE / "instructions_claim.md"
    ).read_text(encoding="utf-8")


def test_the_instructions_are_written_from_the_documents():
    queue = client.get("/api/instructions/queue").json()["text"]
    claim = client.get("/api/instructions/claim").json()["text"]
    assert queue.startswith("# UnderCover Agent: running the queue")
    assert claim.startswith("# UnderCover Agent: working a claim")
    assert "claims manual" in claim
    assert "the manual holds what the wording leaves open" in claim.lower()
    assert "data/evals" not in queue
    assert "data/evals" not in claim
