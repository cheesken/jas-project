from fastapi import APIRouter

from services.db import SQLiteDB


router = APIRouter()


@router.get("/status")
def get_status():
    db = SQLiteDB()
    return db.get_status_summary()
