import sys

# Remove conftest stub so the real api.ingest module is imported
sys.modules.pop("api.ingest", None)

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter


@pytest.fixture
def sample_pdf(tmp_path):
    path = tmp_path / "sample.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, "Test document for ingestion.")
    c.save()
    return str(path)


@pytest.fixture
def mock_db():
    with patch("api.ingest.SQLiteDB") as MockDB:
        instance = MagicMock()
        MockDB.return_value = instance
        instance.get_job_by_hash.return_value = None
        instance.insert_job.return_value = None
        instance.get_job.return_value = None
        yield instance


@pytest.fixture
def mock_ingest_task():
    with patch("api.ingest.ingest_task") as mock_task:
        mock_task.delay = MagicMock()
        yield mock_task


@pytest.fixture
def client(mock_db, mock_ingest_task):
    from api.ingest import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# Test 1: POST /ingest with valid PDF returns 201
def test_ingest_valid_pdf(client, sample_pdf, mock_db, mock_ingest_task):
    response = client.post("/ingest", json={"file_path": sample_pdf, "file_type": "pdf"})
    assert response.status_code == 201
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "PENDING"
    mock_ingest_task.delay.assert_called_once_with(data["job_id"])


def test_ingest_valid_image(client, tmp_path, mock_db, mock_ingest_task):
    from PIL import Image

    path = tmp_path / "screenshot.png"
    Image.new("RGB", (50, 50), "white").save(path)
    response = client.post("/ingest", json={"file_path": str(path), "file_type": "image"})
    assert response.status_code == 201
    inserted = mock_db.insert_job.call_args.args[0]
    assert inserted["file_type"] == "image"
    assert inserted["file_name"] == "screenshot.png"


def test_ingest_valid_txt(client, tmp_path, mock_db, mock_ingest_task):
    path = tmp_path / "notes.txt"
    path.write_text("Tara recommended Noosh Noshery.")
    response = client.post("/ingest", json={"file_path": str(path), "file_type": "txt"})
    assert response.status_code == 201
    inserted = mock_db.insert_job.call_args.args[0]
    assert inserted["file_type"] == "txt"
    assert inserted["file_name"] == "notes.txt"
    mock_ingest_task.delay.assert_called_once_with(response.json()["job_id"])


def test_ingest_valid_browser_history(client, tmp_path, mock_db, mock_ingest_task):
    path = tmp_path / "History"
    path.write_bytes(b"SQLite format 3\x00")
    response = client.post("/ingest", json={"file_path": str(path), "file_type": "browser_history"})
    assert response.status_code == 201
    inserted = mock_db.insert_job.call_args.args[0]
    assert inserted["file_type"] == "browser_history"
    assert inserted["file_name"] == "History"


# Test 2: POST /ingest with non-existent file returns 400
def test_ingest_file_not_found(client):
    response = client.post("/ingest", json={"file_path": "/nonexistent/file.pdf", "file_type": "pdf"})
    assert response.status_code == 400


# Test 3: POST /ingest with invalid file_type returns 422
def test_ingest_invalid_file_type(client):
    response = client.post("/ingest", json={"file_path": "/some/file.docx", "file_type": "docx"})
    assert response.status_code == 422


# Test 4: POST /ingest with no body returns 422
def test_ingest_no_body(client):
    response = client.post("/ingest")
    assert response.status_code == 422


# Test 5: POST /ingest with duplicate hash returns 409
def test_ingest_duplicate_hash(client, sample_pdf, mock_db, mock_ingest_task):
    mock_db.get_job_by_hash.return_value = {
        "job_id": "existing-uuid-1234",
        "status": "COMPLETED",
    }
    response = client.post("/ingest", json={"file_path": sample_pdf, "file_type": "pdf"})
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["existing_job_id"] == "existing-uuid-1234"
    assert detail["message"] == "File already ingested"
    mock_ingest_task.delay.assert_not_called()


# Test 6: GET /ingest/{job_id} for known job returns 200
def test_get_job_status_found(client, mock_db):
    mock_db.get_job.return_value = {
        "job_id": "test-uuid",
        "status": "PROCESSING",
        "error_message": None,
        "chunk_count": 0,
    }
    response = client.get("/ingest/test-uuid")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "test-uuid"
    assert data["status"] == "PROCESSING"


# Test 7: GET /ingest/{job_id} for unknown job returns 404
def test_get_job_status_not_found(client, mock_db):
    mock_db.get_job.return_value = None
    response = client.get("/ingest/nonexistent-uuid")
    assert response.status_code == 404


def _existing_job(path, status="COMPLETED"):
    return {"job_id": "existing-1", "file_path": path, "status": status}


def test_force_reruns_existing_job_instead_of_409(client, sample_pdf, mock_db, mock_ingest_task):
    mock_db.get_job_by_hash.return_value = _existing_job(sample_pdf)
    response = client.post("/ingest", json={"file_path": sample_pdf, "file_type": "pdf", "force": True})
    assert response.status_code == 201
    assert response.json() == {"job_id": "existing-1", "status": "PENDING"}
    mock_db.insert_job.assert_not_called()
    mock_db.update_status.assert_called_once_with(
        "existing-1", "PENDING", retry_count=0, error_message=None, chunk_count=0, completed_at=None,
    )
    mock_ingest_task.delay.assert_called_once_with("existing-1")


def test_force_on_in_flight_job_returns_409(client, sample_pdf, mock_db, mock_ingest_task):
    mock_db.get_job_by_hash.return_value = _existing_job(sample_pdf, status="EMBEDDING")
    response = client.post("/ingest", json={"file_path": sample_pdf, "file_type": "pdf", "force": True})
    assert response.status_code == 409
    mock_ingest_task.delay.assert_not_called()


def test_force_with_same_content_at_another_path_still_409(client, sample_pdf, mock_db, mock_ingest_task):
    mock_db.get_job_by_hash.return_value = _existing_job("/elsewhere/copy.pdf")
    response = client.post("/ingest", json={"file_path": sample_pdf, "file_type": "pdf", "force": True})
    assert response.status_code == 409
    mock_ingest_task.delay.assert_not_called()


def test_reindex_queues_newest_job_per_existing_path(client, tmp_path, mock_db, mock_ingest_task):
    notes = tmp_path / "notes.txt"
    notes.write_text("hi")
    history = tmp_path / "History"
    history.write_text("db")
    mock_db.get_all_jobs.return_value = [  # newest first, as SQLiteDB returns them
        {"job_id": "hist-new", "file_path": str(history), "status": "COMPLETED"},
        {"job_id": "notes", "file_path": str(notes), "status": "FAILED"},
        {"job_id": "busy", "file_path": str(tmp_path / "busy.pdf"), "status": "PROCESSING"},
        {"job_id": "gone", "file_path": "/deleted/file.pdf", "status": "COMPLETED"},
        {"job_id": "hist-old", "file_path": str(history), "status": "COMPLETED"},
    ]
    response = client.post("/reindex")
    assert response.status_code == 202
    assert response.json() == {"queued": 2, "skipped": 2}
    queued = [c.args[0] for c in mock_ingest_task.delay.call_args_list]
    assert queued == ["hist-new", "notes"]
