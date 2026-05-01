# Personal Memory System (POC)

A privacy-preserving personal memory system with semantic retrieval over PDFs. Runs entirely on macOS — no data leaves the device.

Group: Ananya Makwana, Jahnavi Kedia, FNU Shamathmika · Mentor: Gopinath Vinodh.

## Running the project

**Prerequisites:** Docker Desktop, Ollama running natively with `llama3:8b` pulled.

```bash
ollama pull llama3:8b
docker compose up -d --build
```

The API will be available at `http://localhost:8000`.

## Running tests

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Unit tests — no Docker or Ollama required
pytest tests/ -m "not slow"

# Full integration test — requires Docker and Ollama
pytest tests/test_integration.py -v -s
```

`pyproject.toml` adds `backend/` to `sys.path`, so imports like `from services.db import SQLiteDB` resolve without any `PYTHONPATH` export.

## Modules

| Path | Owner | Notes |
|------|-------|-------|
| `backend/api/main.py` | Shamathmika | FastAPI app, router wiring, lifespan |
| `backend/api/ingest.py` | Ananya | `POST /ingest`, `GET /ingest/{job_id}` — *not yet implemented* |
| `backend/api/query.py` | Shamathmika | `GET /query` |
| `backend/api/status.py` | Jahnavi | `GET /status` |
| `backend/parsers/base.py` | Ananya | `Chunk`, `ParseError` |
| `backend/parsers/pdf.py` | Ananya | `parse_pdf()` — *not yet implemented* |
| `backend/services/embedding.py` | Ananya | `EmbeddingService` — *not yet implemented* |
| `backend/services/vector_store.py` | Jahnavi | ChromaDB adapter |
| `backend/services/db.py` | Jahnavi | SQLite adapter |
| `backend/services/query.py` | Jahnavi | `QueryService`, `Result`, `search()`, `count()` |
| `backend/services/ollama.py` | Shamathmika | `OllamaService`, error classes |
| `backend/worker/celery_app.py` | Jahnavi | Celery configuration |
| `backend/worker/tasks.py` | Jahnavi | `ingest_task` |
| `backend/scripts/init_db.py` | Shamathmika | Standalone DB initializer |
| `backend/Dockerfile` | Shamathmika | |
| `backend/requirements.txt` | Shamathmika | Pinned dependencies |
| `docker-compose.yml` | Shamathmika | redis, api, worker services |
| `.env.example` | Shamathmika | Environment variable reference |
| `pyproject.toml` | Jahnavi | pytest config, adds `backend/` to `sys.path` |
| `frontend/package.json` | Ananya | Electron + React + Vite |
| `frontend/electron/main.js`, `preload.js` | Ananya | Electron main process, IPC |
| `frontend/src/App.jsx`, `index.jsx` | Ananya | Screen state machine |
| `frontend/src/screens/HomeScreen.jsx` | Ananya | |
| `frontend/src/screens/SearchResultsScreen.jsx` | Ananya | |
| `frontend/src/components/ResultCard.jsx` | Jahnavi | Search result card |
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

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker |
| `CHROMA_PATH` | `/data/chroma` | ChromaDB persist directory |
| `SQLITE_PATH` | `/data/personal_memory.db` | SQLite file path |
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama endpoint |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence transformer model |

Copy `.env.example` to `.env` to override any of these locally.
