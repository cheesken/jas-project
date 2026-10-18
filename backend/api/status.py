import os

import requests
from fastapi import APIRouter

from services.db import SQLiteDB
from services.query import count


router = APIRouter()


@router.get("/status")
def get_status():
    db = SQLiteDB()
    return db.get_status_summary()


@router.get("/status/services")
def get_services():
    try:
        count()
        vector_store = True
    except Exception:
        vector_store = False

    model = os.environ.get("OLLAMA_MODEL", "llama3:8b")
    try:
        r = requests.get(f"{os.environ.get('OLLAMA_URL', 'http://localhost:11434')}/api/tags", timeout=3)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
        ollama = True
        model_ready = any(n == model or n == f"{model}:latest" for n in names)
    except (requests.RequestException, ValueError):
        ollama = False
        model_ready = False

    return {
        "api": True,
        "vector_store": vector_store,
        "ollama": ollama,
        "ollama_model": model,
        "ollama_model_ready": model_ready,
    }
