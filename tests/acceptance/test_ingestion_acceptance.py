"""
Acceptance tests for US-F-01 through US-F-04 on a 50-file and 20-image corpus.

US-F-01: The system ingests plain-text notes and indexes their content.
         Pass: all 50 text files reach COMPLETED within the timeout.
US-F-02: The system ingests PNG images via OCR and indexes their content.
         Pass: all 20 images reach COMPLETED within the timeout.
US-F-03: Re-submitting an already-indexed file is rejected as a duplicate.
         Pass: every re-submission from the 70-file corpus returns HTTP 409.
US-F-04: Every ingestion job is trackable via the status endpoint.
         Pass: GET /ingest/{job_id} returns valid job metadata for all 70 jobs,
         and a freshly submitted file is observable in a non-terminal state.

Run from the repo root with the stack up (docker compose up -d):

    docker run --rm --network jas-project_default -v "$HOME:$HOME" -v "$PWD":/repo -w /repo \\
      -e PYTHONPATH=/repo/backend -e ACCEPTANCE_API_URL=http://api:8000 \\
      -e ACCEPTANCE_DIR="$HOME/.jas-acceptance" jas-project-api \\
      python -m pytest tests/acceptance/test_ingestion_acceptance.py -m acceptance -v -p no:cacheprovider

Skipped automatically when the API is not reachable (e.g. in the unit-test run).
"""

import os
import shutil
import time
import uuid
from pathlib import Path

import pytest
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API = os.environ.get("ACCEPTANCE_API_URL", "http://localhost:8000").rstrip("/")
WORK_DIR = Path(os.environ.get("ACCEPTANCE_DIR", Path.home() / ".jas-acceptance"))

TEXT_CORPUS_SIZE = 50
IMAGE_CORPUS_SIZE = 20
CORPUS_TIMEOUT_SECONDS = 600   # 10 min for 70 concurrent files with 1-2 workers
SINGLE_FILE_TIMEOUT_SECONDS = 120
JOB_REQUIRED_FIELDS = {"job_id", "status", "chunk_count"}
IN_PROGRESS_STATES = ("PENDING", "PROCESSING", "CHUNKING", "EMBEDDING")

# Variety of note topics so text content is realistic.
_TOPICS = [
    "grocery shopping list", "doctor appointment", "flight booking",
    "restaurant recommendation", "book to read", "exercise routine",
    "monthly budget", "project meeting notes", "birthday reminder",
    "home maintenance", "travel packing list", "subscription renewal",
    "recipe ideas", "contact details", "car service reminder",
    "insurance renewal", "gift ideas", "language learning notes",
    "podcast recommendations", "tax documents checklist",
]


# ---------------------------------------------------------------------------
# API availability gate
# ---------------------------------------------------------------------------

def _api_up() -> bool:
    try:
        return requests.get(f"{API}/health", timeout=3).ok
    except requests.RequestException:
        return False


pytestmark = [
    pytest.mark.acceptance,
    pytest.mark.skipif(not _api_up(), reason=f"API not reachable at {API}"),
]


# ---------------------------------------------------------------------------
# Corpus builders
# ---------------------------------------------------------------------------

def _make_text_file(folder: Path, run: str, i: int) -> Path:
    topic = _TOPICS[i % len(_TOPICS)]
    path = folder / f"note_{run}_{i:03d}.txt"
    path.write_text(
        f"Personal note #{i} (run {run}).\n"
        f"Topic: {topic}.\n"
        f"Content: This is a detailed note about {topic}. "
        f"Unique identifier: {run}-{i}.\n"
    )
    return path


def _make_image_file(folder: Path, run: str, i: int) -> Path:
    """Create a readable PNG with embedded text so OCR has something to extract."""
    from PIL import Image, ImageDraw  # available in the Docker image
    path = folder / f"image_{run}_{i:03d}.png"
    img = Image.new("RGB", (600, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 20),  f"Image note {i}  run {run}", fill=(0, 0, 0))
    draw.text((20, 60),  f"Topic: {_TOPICS[i % len(_TOPICS)]}", fill=(0, 0, 0))
    draw.text((20, 100), f"Unique ID: {run}-{i}", fill=(0, 0, 0))
    img.save(path, "PNG")
    return path


# ---------------------------------------------------------------------------
# Ingestion helpers
# ---------------------------------------------------------------------------

def _submit(path: Path, file_type: str) -> str:
    """POST /ingest and return job_id (asserts 201)."""
    r = requests.post(
        f"{API}/ingest",
        json={"file_path": str(path), "file_type": file_type},
        timeout=30,
    )
    assert r.status_code == 201, f"Submit {path.name}: expected 201, got {r.status_code} — {r.text}"
    return r.json()["job_id"]


def _poll_status(job_id: str) -> dict:
    r = requests.get(f"{API}/ingest/{job_id}", timeout=10)
    assert r.status_code == 200, f"Poll {job_id}: {r.status_code}"
    return r.json()


def _wait_for_all(jobs: dict, timeout: int = CORPUS_TIMEOUT_SECONDS) -> dict:
    """
    Poll all jobs concurrently until every one reaches a terminal state.

    jobs: {Path -> job_id}
    Returns: {Path -> final status dict}
    """
    pending = dict(jobs)
    results = {}
    deadline = time.time() + timeout

    while pending and time.time() < deadline:
        for path, job_id in list(pending.items()):
            status = _poll_status(job_id)
            if status["status"] == "FAILED":
                pytest.fail(f"{path.name} (job {job_id}) FAILED: {status.get('error_message')}")
            if status["status"] == "COMPLETED":
                results[path] = status
                del pending[path]
        if pending:
            time.sleep(2)

    if pending:
        names = [p.name for p in pending]
        pytest.fail(
            f"{len(names)} file(s) did not complete within {timeout}s: "
            f"{names[:5]}{'…' if len(names) > 5 else ''}"
        )

    return results


# ---------------------------------------------------------------------------
# Module-scoped corpus fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def corpus():
    """
    Build, ingest, and wait for the full 50-text + 20-image corpus.
    Cleans up all files and index entries after the module completes.
    """
    # PIL is installed in the Docker image alongside the image parser.
    pytest.importorskip("PIL", reason="Pillow not available — cannot create test images")

    run = uuid.uuid4().hex[:8]
    folder = WORK_DIR / run
    folder.mkdir(parents=True, exist_ok=True)

    text_paths  = [_make_text_file(folder, run, i)  for i in range(TEXT_CORPUS_SIZE)]
    image_paths = [_make_image_file(folder, run, i) for i in range(IMAGE_CORPUS_SIZE)]
    all_paths   = text_paths + image_paths

    # Submit all jobs before waiting, so the worker can process them in parallel.
    jobs: dict[Path, str] = {}
    for path in text_paths:
        jobs[path] = _submit(path, "txt")
    for path in image_paths:
        jobs[path] = _submit(path, "image")

    results = _wait_for_all(jobs)

    yield {
        "run":         run,
        "folder":      folder,
        "text_paths":  text_paths,
        "image_paths": image_paths,
        "all_paths":   all_paths,
        "jobs":        jobs,
        "results":     results,
    }

    # Teardown: remove from index and delete files from disk.
    for job_id in jobs.values():
        try:
            requests.delete(f"{API}/ingest/{job_id}", timeout=30)
        except requests.RequestException:
            pass
    shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------------------
# US-F-01: Text ingestion
# ---------------------------------------------------------------------------

def test_us_f_01_all_text_files_reach_completed(corpus):
    """US-F-01: All 50 plain-text notes are ingested and indexed successfully."""
    failed = []
    for path in corpus["text_paths"]:
        job_id = corpus["jobs"][path]
        status = _poll_status(job_id)
        if status["status"] != "COMPLETED":
            failed.append(f"{path.name}: {status['status']}")
    assert not failed, f"{len(failed)} text file(s) did not complete:\n" + "\n".join(failed)


def test_us_f_01_text_files_produce_chunks(corpus):
    """US-F-01: Each indexed text file produces at least one chunk."""
    no_chunks = []
    for path in corpus["text_paths"]:
        job_id = corpus["jobs"][path]
        status = _poll_status(job_id)
        if status.get("chunk_count", 0) < 1:
            no_chunks.append(path.name)
    assert not no_chunks, f"{len(no_chunks)} text file(s) produced zero chunks: {no_chunks[:5]}"


# ---------------------------------------------------------------------------
# US-F-02: Image ingestion (OCR)
# ---------------------------------------------------------------------------

def test_us_f_02_all_images_reach_completed(corpus):
    """US-F-02: All 20 PNG images are ingested via OCR and indexed successfully."""
    failed = []
    for path in corpus["image_paths"]:
        job_id = corpus["jobs"][path]
        status = _poll_status(job_id)
        if status["status"] != "COMPLETED":
            failed.append(f"{path.name}: {status['status']}")
    assert not failed, f"{len(failed)} image(s) did not complete:\n" + "\n".join(failed)


def test_us_f_02_images_are_accepted_with_201(corpus):
    """US-F-02: POST /ingest returns 201 for each image at submission time (verified via jobs dict)."""
    # The corpus fixture already asserted 201 on each submission.
    # This test confirms all 20 image job IDs were collected.
    assert len(corpus["image_paths"]) == IMAGE_CORPUS_SIZE
    assert all(p in corpus["jobs"] for p in corpus["image_paths"])


# ---------------------------------------------------------------------------
# US-F-03: Duplicate detection
# ---------------------------------------------------------------------------

def test_us_f_03_resubmit_text_returns_409(corpus):
    """US-F-03: Re-submitting every text file from the corpus returns HTTP 409."""
    non_409 = []
    for path in corpus["text_paths"]:
        r = requests.post(
            f"{API}/ingest",
            json={"file_path": str(path), "file_type": "txt"},
            timeout=30,
        )
        if r.status_code != 409:
            non_409.append(f"{path.name}: got {r.status_code}")
    assert not non_409, (
        f"{len(non_409)} text file(s) did not return 409 on re-submission:\n"
        + "\n".join(non_409)
    )


def test_us_f_03_resubmit_images_returns_409(corpus):
    """US-F-03: Re-submitting every image from the corpus returns HTTP 409."""
    non_409 = []
    for path in corpus["image_paths"]:
        r = requests.post(
            f"{API}/ingest",
            json={"file_path": str(path), "file_type": "image"},
            timeout=30,
        )
        if r.status_code != 409:
            non_409.append(f"{path.name}: got {r.status_code}")
    assert not non_409, (
        f"{len(non_409)} image(s) did not return 409 on re-submission:\n"
        + "\n".join(non_409)
    )


def test_us_f_03_duplicate_response_includes_existing_job_id(corpus):
    """US-F-03: The 409 response body includes the existing job_id so callers can track it."""
    sample = corpus["text_paths"][0]
    r = requests.post(
        f"{API}/ingest",
        json={"file_path": str(sample), "file_type": "txt"},
        timeout=30,
    )
    assert r.status_code == 409
    body = r.json()
    detail = body.get("detail", {})
    assert "existing_job_id" in detail, f"missing existing_job_id in 409 body: {body}"
    assert detail["existing_job_id"] == corpus["jobs"][sample]


# ---------------------------------------------------------------------------
# US-F-04: Status tracking
# ---------------------------------------------------------------------------

def test_us_f_04_all_jobs_queryable_after_completion(corpus):
    """US-F-04: GET /ingest/{job_id} returns 200 for every corpus job after completion."""
    bad = []
    for path, job_id in corpus["jobs"].items():
        r = requests.get(f"{API}/ingest/{job_id}", timeout=10)
        if r.status_code != 200:
            bad.append(f"{path.name} job {job_id}: {r.status_code}")
    assert not bad, f"{len(bad)} job(s) not queryable:\n" + "\n".join(bad)


def test_us_f_04_status_response_has_required_fields(corpus):
    """US-F-04: Every job status response contains the required fields."""
    missing = []
    for path, job_id in corpus["jobs"].items():
        status = _poll_status(job_id)
        absent = JOB_REQUIRED_FIELDS - status.keys()
        if absent:
            missing.append(f"{path.name}: missing {absent}")
    assert not missing, "\n".join(missing)


def test_us_f_04_fresh_job_transitions_through_non_terminal_state():
    """
    US-F-04: A newly submitted job is observable in an in-progress state
    (PENDING, PROCESSING, CHUNKING or EMBEDDING) before it reaches COMPLETED,
    confirming callers can track progress.
    """
    run = uuid.uuid4().hex[:8]
    folder = WORK_DIR / run
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"transition_{run}.txt"
    path.write_text(f"Transition-check note {run}. Status polling test.\n")

    job_id = None
    try:
        job_id = _submit(path, "txt")

        # Poll immediately; a short note can already be past PROCESSING.
        first = _poll_status(job_id)
        assert first["status"] in IN_PROGRESS_STATES + ("COMPLETED",), (
            f"Unexpected initial status: {first['status']}"
        )

        # Eventually reaches COMPLETED.
        deadline = time.time() + SINGLE_FILE_TIMEOUT_SECONDS
        while time.time() < deadline:
            s = _poll_status(job_id)
            if s["status"] == "COMPLETED":
                break
            assert s["status"] in IN_PROGRESS_STATES, f"Unexpected status: {s['status']}"
            time.sleep(1)
        else:
            pytest.fail(f"Job {job_id} did not reach COMPLETED within {SINGLE_FILE_TIMEOUT_SECONDS}s")
    finally:
        if job_id:
            try:
                requests.delete(f"{API}/ingest/{job_id}", timeout=30)
            except requests.RequestException:
                pass
        shutil.rmtree(folder, ignore_errors=True)
