from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.settings import router
from services.db import SQLiteDB


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "settings.db"))
    monkeypatch.setenv("HOST_HOME", str(tmp_path / "home"))
    (tmp_path / "home" / "Documents").mkdir(parents=True)
    (tmp_path / "home" / "Desktop").mkdir()
    return tmp_path / "home"


@pytest.fixture
def client(home):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_empty_list(client):
    assert client.get("/settings/watch").json() == {"paths": []}


def test_add_then_list(client, home):
    r = client.post("/settings/watch", json={"path": f"{home}/Documents/"})
    assert r.status_code == 200
    assert r.json() == {"success": True, "path": f"{home}/Documents"}
    client.post("/settings/watch", json={"path": f"{home}/Desktop"})
    assert client.get("/settings/watch").json()["paths"] == [f"{home}/Documents", f"{home}/Desktop"]


def test_adding_twice_keeps_one_entry(client, home):
    client.post("/settings/watch", json={"path": f"{home}/Documents"})
    assert client.post("/settings/watch", json={"path": f"{home}/Documents"}).status_code == 200
    assert client.get("/settings/watch").json()["paths"] == [f"{home}/Documents"]


@pytest.mark.parametrize("path", ["", "relative/dir", "/definitely/not/here"])
def test_rejects_bad_paths(client, path):
    assert client.post("/settings/watch", json={"path": path}).status_code == 400


def test_rejects_folder_outside_home(client, home):
    outside = home.parent / "elsewhere"
    outside.mkdir()
    r = client.post("/settings/watch", json={"path": str(outside)})
    assert r.status_code == 400
    assert "inside" in r.json()["detail"]


def test_rejects_sibling_with_home_prefix(client, home):
    sneaky = home.parent / (home.name + "-other")
    sneaky.mkdir()
    assert client.post("/settings/watch", json={"path": str(sneaky)}).status_code == 400


def test_remove_with_url_encoded_path(client, home):
    client.post("/settings/watch", json={"path": f"{home}/Documents"})
    r = client.delete(f"/settings/watch/{quote(f'{home}/Documents', safe='')}")
    assert r.status_code == 200
    assert r.json() == {"success": True, "path": f"{home}/Documents"}
    assert client.get("/settings/watch").json() == {"paths": []}


def test_remove_with_plain_path(client, home):
    client.post("/settings/watch", json={"path": f"{home}/Desktop"})
    assert client.delete(f"/settings/watch{home}/Desktop").status_code == 200


def test_remove_unknown_returns_404(client, home):
    assert client.delete(f"/settings/watch/{quote(f'{home}/Documents', safe='')}").status_code == 404


def test_watch_dirs_persist_in_sqlite(client, home, tmp_path):
    client.post("/settings/watch", json={"path": f"{home}/Documents"})
    assert SQLiteDB(db_path=str(tmp_path / "settings.db")).list_watch_dirs() == [f"{home}/Documents"]
