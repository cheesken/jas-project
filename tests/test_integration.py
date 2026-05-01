import os
import shutil
import datetime
import subprocess
import time

import pytest
import requests

API_BASE = "http://localhost:8000"
COMPOSE_TIMEOUT = 60
INGEST_TIMEOUT = 300
POLL_INTERVAL = 5


@pytest.fixture(scope="session")
def fixture_pdf():
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    # Must be under ${HOME} — that is the only host path mounted into the container
    # (${HOME}:${HOME}:ro per docker-compose.yml). pytest's tmp_path writes to
    # /private/var/folders/... on macOS, which is not visible inside the container.
    fixture_dir = os.path.join(os.path.expanduser("~"), ".personal_memory_test_fixtures")
    os.makedirs(fixture_dir, exist_ok=True)
    path = os.path.join(fixture_dir, "sample.pdf")

    # Unique per-run marker so the file hash differs across pytest invocations,
    # preventing 409 collisions from the previous run's hash still being in SQLite.
    run_id = datetime.datetime.now().isoformat()

    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(72, 720, "The capstone project is advised by Gopinath Vinodh in the Spring 2026 semester.")
    c.drawString(72, 690, "It is a privacy-preserving personal memory system built as a local desktop application.")
    c.drawString(72, 660, "The team includes graduate students at San Jose State University.")
    c.drawString(72, 50, f"Test run: {run_id}")
    c.showPage()
    c.drawString(72, 720, "Chapter 2 covers the system architecture.")
    c.drawString(72, 690, "All processing happens locally on the user's macOS device.")
    c.showPage()
    c.drawString(72, 720, "Chapter 3 describes the evaluation methodology and benchmarks.")
    c.save()

    yield path

    shutil.rmtree(fixture_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def docker_stack():
    subprocess.run(["docker", "compose", "up", "-d", "--build"], check=True)

    deadline = time.time() + COMPOSE_TIMEOUT
    while time.time() < deadline:
        try:
            r = requests.get(f"{API_BASE}/health", timeout=2)
            if r.status_code == 200:
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    else:
        subprocess.run(["docker", "compose", "logs"])
        subprocess.run(["docker", "compose", "down"])
        pytest.fail("API did not become healthy within timeout")

    yield

    subprocess.run(["docker", "compose", "down"])


@pytest.mark.slow
@pytest.mark.integration
def test_full_ingestion_and_query(docker_stack, fixture_pdf):
    r = requests.post(f"{API_BASE}/ingest", json={
        "file_path": fixture_pdf,
        "file_type": "pdf",
    })
    assert r.status_code == 201, f"Ingest failed: {r.status_code} {r.text}"
    job_id = r.json()["job_id"]

    deadline = time.time() + INGEST_TIMEOUT
    final_status = None
    while time.time() < deadline:
        r = requests.get(f"{API_BASE}/ingest/{job_id}")
        assert r.status_code == 200
        body = r.json()
        if body["status"] in ("COMPLETED", "FAILED"):
            final_status = body
            break
        time.sleep(POLL_INTERVAL)

    assert final_status is not None, "Ingestion timed out"
    assert final_status["status"] == "COMPLETED", \
        f"Ingestion failed: {final_status.get('error_message')}"
    assert final_status["chunk_count"] > 0

    r = requests.get(f"{API_BASE}/query", params={"q": "who is the project advisor", "top_k": 5})
    assert r.status_code == 200
    body = r.json()

    assert "results" in body and "response" in body
    assert len(body["results"]) > 0, "Query returned no results"
    for result in body["results"]:
        assert set(result.keys()) >= {"chunk_id", "content", "file_name", "source_type", "score", "last_modified"}
        assert "source_path" not in result, "source_path leaked into API response"
        assert isinstance(result["score"], float)
        assert 0.0 <= result["score"] <= 1.0
        assert result["source_type"] == "Document"
        assert result["file_name"] == "sample.pdf"

    assert any("Gopinath" in r["content"] for r in body["results"]), \
        "Expected at least one result to mention 'Gopinath'"

    assert isinstance(body["response"], str)
    assert len(body["response"]) > 0


@pytest.mark.slow
@pytest.mark.integration
def test_status_endpoint_after_ingest(docker_stack):
    r = requests.get(f"{API_BASE}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["total_docs"] >= 1
    assert body["last_updated"] is not None


@pytest.mark.slow
@pytest.mark.integration
def test_duplicate_ingest_rejected(docker_stack, fixture_pdf):
    r = requests.post(f"{API_BASE}/ingest", json={
        "file_path": fixture_pdf,
        "file_type": "pdf",
    })
    assert r.status_code == 409
