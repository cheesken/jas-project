import os
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.db import SQLiteDB

router = APIRouter()


class WatchRequest(BaseModel):
    path: str


class WatchListResponse(BaseModel):
    paths: List[str]


class WatchResponse(BaseModel):
    success: bool
    path: str


def _normalize(path: str) -> str:
    return os.path.normpath(path.strip()) if path.strip() else ""


def _validate(path: str) -> str:
    normalized = _normalize(path)
    if not normalized or not os.path.isabs(normalized):
        raise HTTPException(status_code=400, detail="Folder path must be absolute")
    home = os.environ.get("HOST_HOME")
    if home and os.path.commonpath([normalized, os.path.normpath(home)]) != os.path.normpath(home):
        raise HTTPException(status_code=400, detail=f"Folder must be inside {home}")
    if not os.path.isdir(normalized):
        raise HTTPException(status_code=400, detail="Folder not found")
    return normalized


@router.get("/settings/watch", response_model=WatchListResponse)
def list_watched():
    return WatchListResponse(paths=SQLiteDB().list_watch_dirs())


@router.post("/settings/watch", response_model=WatchResponse)
def add_watched(req: WatchRequest):
    path = _validate(req.path)
    SQLiteDB().add_watch_dir(path)
    return WatchResponse(success=True, path=path)


@router.delete("/settings/watch/{path:path}", response_model=WatchResponse)
def remove_watched(path: str):
    normalized = _normalize(path if path.startswith("/") else "/" + path)
    if not SQLiteDB().remove_watch_dir(normalized):
        raise HTTPException(status_code=404, detail="Folder is not being watched")
    return WatchResponse(success=True, path=normalized)
