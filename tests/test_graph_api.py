import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.graph  # noqa: F401
from services.graph import KnowledgeGraph

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "kg_sample.json")


@pytest.fixture
def kg():
    graph = KnowledgeGraph(graph_path=FIXTURE)
    graph.load()
    return graph


@pytest.fixture
def client(kg):
    with patch("api.graph.get_graph", return_value=kg):
        from api.main import app
        yield TestClient(app, raise_server_exceptions=False)


def test_graph_returns_nodes_and_edges(client):
    r = client.get("/graph")
    assert r.status_code == 200
    body = r.json()
    assert len(body["nodes"]) == 9
    assert len(body["edges"]) == 12
    assert set(body["nodes"][0]) == {"entity_id", "name", "entity_type", "mention_count", "doc_count"}
    assert set(body["edges"][0]) == {"entity_a", "entity_b", "co_occurrence_count"}


def test_graph_never_exposes_paths(client):
    assert "/Users/test" not in client.get("/graph").text
    assert "/Users/test" not in client.get("/graph/PERSON:tara").text


def test_graph_filters(client):
    body = client.get("/graph", params={"entity_type": "gpe"}).json()
    assert {n["entity_type"] for n in body["nodes"]} == {"GPE"}
    body = client.get("/graph", params={"limit": 2}).json()
    assert len(body["nodes"]) == 2
    ids = {n["entity_id"] for n in body["nodes"]}
    assert all(e["entity_a"] in ids and e["entity_b"] in ids for e in body["edges"])


def test_graph_rejects_bad_params(client):
    assert client.get("/graph", params={"limit": 0}).status_code == 422
    assert client.get("/graph", params={"min_mentions": 0}).status_code == 422


def test_graph_empty_when_no_kg(tmp_path):
    empty = KnowledgeGraph(graph_path=str(tmp_path / "none.json"))
    empty.load()
    with patch("api.graph.get_graph", return_value=empty):
        from api.main import app
        r = TestClient(app).get("/graph")
    assert r.status_code == 200
    assert r.json() == {"nodes": [], "edges": []}


def test_entity_detail(client):
    r = client.get("/graph/PERSON:tara")
    assert r.status_code == 200
    body = r.json()
    assert body["entity"]["name"] == "Tara"
    assert body["entity"]["doc_count"] == 2
    assert body["docs"] == [{"file_name": "whatsapp_export.txt"}, {"file_name": "meeting_notes_q1.txt"}]
    first = body["neighbors"][0]
    assert first["entity_id"] == "GPE:mountain_view"
    assert first["co_occurrence_count"] == 2
    assert {d["file_name"] for d in first["shared_docs"]} == {"whatsapp_export.txt", "meeting_notes_q1.txt"}


def test_entity_detail_neighbor_limit(client):
    body = client.get("/graph/PERSON:tara", params={"neighbor_limit": 1}).json()
    assert len(body["neighbors"]) == 1


def test_entity_detail_unknown_returns_404(client):
    assert client.get("/graph/PERSON:nobody").status_code == 404


def test_search_route_not_shadowed_by_entity_route(client):
    r = client.get("/graph/search", params={"q": "park"})
    assert r.status_code == 200
    assert [e["entity_id"] for e in r.json()["results"]] == ["ORG:park_hyatt"]


def test_search_requires_query(client):
    assert client.get("/graph/search").status_code == 422
