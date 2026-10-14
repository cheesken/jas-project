"""
Acceptance tests for US-F-08 and US-F-09 (workbook section 7.1), against the
running stack.

US-F-08: a natural-language query returns the top 10 most relevant results;
         pass = at least one relevant result, response within 180 seconds.
US-F-09: every result shows an excerpt, source file name, source type, date and
         relevance score.

The tests upload their own uniquely named notes, so they don't depend on (or
disturb) what's already indexed, and delete them afterwards. The API can only
read files under your home folder, so ACCEPTANCE_DIR must be inside it.

Run from the repo root with the stack up (docker compose up -d):

    docker run --rm --network jas-project_default -v "$HOME:$HOME" -v "$PWD":/repo -w /repo \\
      -e PYTHONPATH=/repo/backend -e ACCEPTANCE_API_URL=http://api:8000 \\
      -e ACCEPTANCE_DIR="$HOME/.jas-acceptance" jas-project-api \\
      python -m pytest tests/acceptance -m acceptance -v -p no:cacheprovider

Skipped automatically when the API isn't reachable (e.g. in the unit-test run).
"""
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import requests

API = os.environ.get("ACCEPTANCE_API_URL", "http://localhost:8000").rstrip("/")
WORK_DIR = Path(os.environ.get("ACCEPTANCE_DIR", Path.home() / ".jas-acceptance"))
QUERY_BUDGET_SECONDS = 180  # US-F-08 pass criterion
INGEST_TIMEOUT_SECONDS = 120
SOURCE_TYPES = {"Document", "Browser History", "Image"}


def _api_up() -> bool:
    try:
        return requests.get(f"{API}/health", timeout=3).ok
    except requests.RequestException:
        return False


pytestmark = [
    pytest.mark.acceptance,
    pytest.mark.skipif(not _api_up(), reason=f"API not reachable at {API}"),
]


def _ingest(path: Path) -> str:
    r = requests.post(f"{API}/ingest", json={"file_path": str(path), "file_type": "txt"}, timeout=30)
    assert r.status_code == 201, r.text
    job_id = r.json()["job_id"]
    deadline = time.time() + INGEST_TIMEOUT_SECONDS
    while time.time() < deadline:
        status = requests.get(f"{API}/ingest/{job_id}", timeout=10).json()
        if status["status"] == "COMPLETED":
            return job_id
        assert status["status"] != "FAILED", status
        time.sleep(1)
    pytest.fail(f"{path.name} not indexed within {INGEST_TIMEOUT_SECONDS} s")


@pytest.fixture(scope="module")
def indexed_notes():
    """Two notes with a run-unique reference, so each run indexes new files."""
    run = uuid.uuid4().hex[:8]
    folder = WORK_DIR / run
    folder.mkdir(parents=True, exist_ok=True)
    answer = folder / f"bistro_tip_{run}.txt"
    answer.write_text(
        "Ilsa Moreau recommended Blue Heron Bistro in Pacifica. She said the crab cakes are "
        f"excellent and the ocean view is worth the drive. Ref {run}.\n")
    other = folder / f"errands_{run}.txt"
    other.write_text(f"Errands: return the library tote, buy printer ink, renew the car registration. Ref {run}.\n")
    jobs = []
    try:
        for path in (answer, other):
            jobs.append(_ingest(path))
        yield {"answer": answer.name, "other": other.name}
    finally:
        for job_id in jobs:
            requests.delete(f"{API}/ingest/{job_id}", timeout=30)
        shutil.rmtree(folder, ignore_errors=True)


def _query(q: str):
    start = time.perf_counter()
    r = requests.get(f"{API}/query", params={"q": q, "top_k": 10}, timeout=QUERY_BUDGET_SECONDS + 30)
    return r, time.perf_counter() - start


def test_us_f_08_natural_language_query_returns_relevant_top_10(indexed_notes):
    r, elapsed = _query("Which restaurant did Ilsa Moreau recommend?")
    assert r.status_code == 200, r.text
    body = r.json()
    results = body["results"]
    assert elapsed <= QUERY_BUDGET_SECONDS, f"took {elapsed:.1f} s"
    assert 1 <= len(results) <= 10
    names = [res["file_name"] for res in results]
    assert indexed_notes["answer"] in names, names
    scores = [res["score"] for res in results]
    assert scores == sorted(scores, reverse=True), "results must be ranked by relevance"
    assert isinstance(body["response"], str) and body["response"]


def test_us_f_08_relevant_note_outranks_unrelated_note(indexed_notes):
    r, _ = _query("Where can I get good crab cakes near the ocean?")
    names = [res["file_name"] for res in r.json()["results"]]
    assert indexed_notes["answer"] in names
    if indexed_notes["other"] in names:
        assert names.index(indexed_notes["answer"]) < names.index(indexed_notes["other"])


def test_us_f_09_every_result_has_the_five_card_fields(indexed_notes):
    r, _ = _query("Which restaurant did Ilsa Moreau recommend?")
    results = r.json()["results"]
    assert results
    for res in results:
        assert isinstance(res["content"], str) and res["content"].strip(), res
        assert isinstance(res["file_name"], str) and res["file_name"].strip(), res
        assert res["source_type"] in SOURCE_TYPES, res
        datetime.fromisoformat(res["last_modified"])  # a real date, parseable by the card
        assert 0.0 <= res["score"] <= 1.0, res
        assert "source_path" not in res  # the card never needs, and must not leak, full paths


def test_us_f_09_card_fields_describe_the_uploaded_note(indexed_notes):
    r, _ = _query("Which restaurant did Ilsa Moreau recommend?")
    card = next(res for res in r.json()["results"] if res["file_name"] == indexed_notes["answer"])
    assert card["source_type"] == "Document"
    assert "Blue Heron Bistro" in card["content"]
    modified = datetime.fromisoformat(card["last_modified"])
    assert abs(time.time() - modified.timestamp()) < 24 * 3600  # file was written just now
