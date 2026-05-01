# Personal Memory System (POC)

A privacy-preserving personal memory system with semantic retrieval over PDFs. Runs entirely on macOS — no data leaves the device.

Group: Ananya Makwana, Jahnavi Kedia, FNU Shamathmika · Mentor: Gopinath Vinodh.

## Status

Jahnavi's slice (data layer, worker, search service, status endpoint, ResultCard) is landed and green: 43 unit tests pass under `pytest tests/`.

Still to land:

- **Ananya's slice** — `backend/parsers/pdf.py` and `backend/services/embedding.py` are currently `NotImplementedError` stubs that exist only so Jahnavi's worker can import them. Ananya replaces them with real implementations and adds the ingest endpoint, Electron shell, and remaining frontend screens.
- **Shamathmika's slice** — `backend/api/main.py`, `backend/api/query.py`, `backend/services/ollama.py`, `backend/scripts/init_db.py`, `backend/Dockerfile`, `backend/requirements.txt`, `docker-compose.yml`, `.env.example`, and the integration test.

Until Ananya's stubs are replaced, the worker cannot run end-to-end. Jahnavi's tests cover the worker via mocks and don't depend on the stubs being real.

## Quick Start

```bash
# Once Shamathmika commits backend/requirements.txt:
pip install -r backend/requirements.txt

# Interim (Jahnavi's tests only need this subset):
pip install \
  fastapi==0.110.0 'uvicorn[standard]==0.27.1' pydantic==2.6.4 \
  celery==5.3.6 redis==5.0.3 chromadb==0.4.24 \
  pytest==8.1.1 pytest-asyncio==0.23.5 httpx==0.27.0

# Run the test suite from project root:
pytest tests/
```

`pyproject.toml` puts `backend/` on `sys.path`, so `from services.db import SQLiteDB` resolves without any `PYTHONPATH=` export.

## Modules and Owners

| Path | Owner | Notes |
|------|-------|-------|
| `backend/api/main.py` | Shamathmika | FastAPI app, router wiring, lifespan |
| `backend/api/ingest.py` | Ananya | `POST /ingest`, `GET /ingest/{job_id}` |
| `backend/api/query.py` | Shamathmika | `GET /query` |
| `backend/api/status.py` | Jahnavi | `GET /status` |
| `backend/parsers/base.py` | Ananya | `Chunk`, `ParseError` |
| `backend/parsers/pdf.py` | Ananya | **Stub** — `parse_pdf()` |
| `backend/services/embedding.py` | Ananya | **Stub** — `EmbeddingService` |
| `backend/services/vector_store.py` | Jahnavi | ChromaDB adapter |
| `backend/services/db.py` | Jahnavi | SQLite adapter |
| `backend/services/query.py` | Jahnavi | `QueryService`, `Result`, `search()`, `count()` |
| `backend/services/ollama.py` | Shamathmika | `OllamaService` + error classes |
| `backend/worker/celery_app.py` | Jahnavi | Celery configuration |
| `backend/worker/tasks.py` | Jahnavi | `ingest_task` |
| `backend/scripts/init_db.py` | Shamathmika | Standalone DB init |
| `backend/Dockerfile` | Shamathmika | |
| `backend/requirements.txt` | Shamathmika | |
| `docker-compose.yml` | Shamathmika | |
| `.env.example` | Shamathmika | |
| `pyproject.toml` | Jahnavi | pytest pythonpath = `backend` |
| `frontend/package.json` | Ananya | Electron + React + Vite |
| `frontend/electron/main.js`, `preload.js` | Ananya | Electron main + IPC |
| `frontend/src/App.jsx`, `index.jsx` | Ananya | Screen state machine |
| `frontend/src/screens/HomeScreen.jsx` | Ananya | |
| `frontend/src/screens/SearchResultsScreen.jsx` | Ananya | |
| `frontend/src/components/ResultCard.jsx` | Jahnavi | |
| `frontend/src/components/SearchBar.jsx` | Ananya | |
| `frontend/src/components/Toast.jsx` | Ananya | |
| `tests/test_parser.py` | Ananya | |
| `tests/test_embedding.py` | Ananya | |
| `tests/test_ingest_api.py` | Ananya | |
| `tests/test_vector_store.py` | Jahnavi | |
| `tests/test_db.py` | Jahnavi | |
| `tests/test_query.py` | Jahnavi | |
| `tests/test_worker.py` | Jahnavi | |
| `tests/test_status_api.py` | Jahnavi | |
| `tests/test_ollama.py` | Shamathmika | |
| `tests/test_query_api.py` | Shamathmika | |
| `tests/test_integration.py` | Shamathmika | |

## Contracts

The cross-slice import contracts (which symbols each teammate exposes and consumes) are listed in **Section 12 of `POC_Requirements.md`** — paths and signatures there are fixed. If you need to know what to import from another slice, read that section before grepping.
