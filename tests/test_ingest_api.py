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


# Test 2: POST /ingest with non-existent file returns 400
def test_ingest_file_not_found(client):
    response = client.post("/ingest", json={"file_path": "/nonexistent/file.pdf", "file_type": "pdf"})
    assert response.status_code == 400


# Test 3: POST /ingest with invalid file_type returns 422
def test_ingest_invalid_file_type(client):
    response = client.post("/ingest", json={"file_path": "/some/file.txt", "file_type": "txt"})
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
