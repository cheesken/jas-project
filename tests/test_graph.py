import json
import os
import shutil

import pytest

import services.graph as graph_module
from services.graph import KnowledgeGraph, make_entity_id, normalize_name

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "kg_sample.json")


@pytest.fixture
def kg_path(tmp_path):
    path = tmp_path / "kg.json"
    shutil.copy(FIXTURE, path)
    return str(path)


@pytest.fixture
def kg(kg_path):
    graph = KnowledgeGraph(graph_path=kg_path)
    graph.load()
    return graph


@pytest.fixture(autouse=True)
def reset_singleton():
    graph_module._graph = None
    yield
    graph_module._graph = None


def test_normalize_name_lowercases_and_strips_punctuation():
    assert normalize_name("Tara's") == "tara"
    assert normalize_name("  Noosh-Noshery!! ") == "noosh noshery"
    assert normalize_name("Castro St.") == "castro st"


def test_make_entity_id_is_type_prefixed_and_url_safe():
    assert make_entity_id("Noosh Noshery", "org") == "ORG:noosh_noshery"
    assert make_entity_id("Tara", "PERSON") == "PERSON:tara"


def test_load_missing_file_gives_empty_graph(tmp_path):
    graph = KnowledgeGraph(graph_path=str(tmp_path / "absent.json"))
    graph.load()
    assert graph.node_count() == 0
    assert graph.find_entities("Tara") == []


def test_load_fixture(kg):
    assert kg.node_count() == 9
    assert kg.graph.number_of_edges() == 12


def test_corrupt_file_keeps_previous_graph(kg, kg_path):
    with open(kg_path, "w") as f:
        f.write("{not json")
    os.utime(kg_path, (1, 1))
    kg.reload_if_changed()
    assert kg.node_count() == 9


def test_get_entity_returns_schema_fields(kg):
    e = kg.get_entity("PERSON:tara")
    assert e == {
        "entity_id": "PERSON:tara",
        "name": "Tara",
        "entity_type": "PERSON",
        "mention_count": 2,
        "source_docs": [
            "/Users/test/notes/whatsapp_export.txt",
            "/Users/test/notes/meeting_notes_q1.txt",
        ],
    }


def test_get_entity_unknown_returns_none(kg):
    assert kg.get_entity("PERSON:nobody") is None


def test_get_neighbors_sorted_by_co_occurrence(kg):
    neighbors = kg.get_neighbors("PERSON:tara")
    ids = [n["entity_id"] for n, _ in neighbors]
    assert ids[0] == "GPE:mountain_view"
    assert set(ids) == {"GPE:mountain_view", "GPE:castro_st", "ORG:noosh_noshery"}
    assert neighbors[0][1]["co_occurrence_count"] == 2


def test_get_neighbors_limit_and_unknown(kg):
    assert len(kg.get_neighbors("PERSON:tara", limit=1)) == 1
    assert kg.get_neighbors("PERSON:nobody") == []


def test_find_entities_in_natural_language_query(kg):
    assert kg.find_entities("What was the restaurant Tara's friend suggested?") == ["PERSON:tara"]


def test_find_entities_prefers_longest_multiword_match(kg):
    found = kg.find_entities("hotels near park hyatt in tokyo")
    assert found == ["ORG:park_hyatt", "GPE:tokyo"]


def test_find_entities_ignores_partial_words(kg):
    assert kg.find_entities("tarantula sightings") == []


def test_find_entities_skips_names_shorter_than_minimum(tmp_path):
    graph = KnowledgeGraph(graph_path=str(tmp_path / "kg.json"))
    graph.graph.add_node("ORG:x", name="X", entity_type="ORG", mention_count=1, source_docs=["/a"])
    graph._rebuild_index()
    assert graph.find_entities("x marks the spot") == []


def test_search_entities_substring_sorted_by_mentions(kg):
    hits = kg.search_entities("a")
    assert hits[0]["mention_count"] >= hits[-1]["mention_count"]
    assert [h["entity_id"] for h in kg.search_entities("noosh")] == ["ORG:noosh_noshery"]
    assert kg.search_entities("   ") == []


def test_subgraph_filters_and_keeps_only_internal_edges(kg):
    nodes, edges = kg.subgraph(entity_type="GPE")
    ids = {n["entity_id"] for n in nodes}
    assert ids == {"GPE:mountain_view", "GPE:castro_st", "GPE:tokyo", "GPE:shinjuku"}
    for e in edges:
        assert e["entity_a"] in ids and e["entity_b"] in ids


def test_subgraph_limit_keeps_most_mentioned(kg):
    nodes, _ = kg.subgraph(limit=3)
    assert len(nodes) == 3
    assert all(n["mention_count"] == 2 for n in nodes)


def test_subgraph_min_mentions(kg):
    nodes, _ = kg.subgraph(min_mentions=2)
    assert {n["entity_id"] for n in nodes} == {"PERSON:tara", "GPE:mountain_view", "ORG:ana"}


def test_save_round_trip(kg, tmp_path):
    out = str(tmp_path / "out" / "kg.json")
    kg.graph_path = out
    kg.save()
    reloaded = KnowledgeGraph(graph_path=out)
    reloaded.load()
    assert reloaded.get_entity("ORG:park_hyatt") == kg.get_entity("ORG:park_hyatt")
    with open(out) as f:
        assert "edges" in json.load(f)
    assert not [p for p in os.listdir(tmp_path / "out") if p.startswith(".kg-")]


def test_reload_if_changed_picks_up_new_file(kg, kg_path):
    with open(kg_path) as f:
        data = json.load(f)
    data["nodes"] = [n for n in data["nodes"] if n["id"] != "ORG:sfo"]
    data["edges"] = [e for e in data["edges"] if "ORG:sfo" not in (e["source"], e["target"])]
    with open(kg_path, "w") as f:
        json.dump(data, f)
    os.utime(kg_path, (2_000_000_000, 2_000_000_000))
    kg.reload_if_changed()
    assert kg.get_entity("ORG:sfo") is None


def test_get_graph_singleton_uses_kg_path(kg_path, monkeypatch):
    monkeypatch.setenv("KG_PATH", kg_path)
    first = graph_module.get_graph()
    assert first is graph_module.get_graph()
    assert first.node_count() == 9


@pytest.mark.xfail(raises=NotImplementedError, strict=True, reason="TODO: entity upsert")
def test_upsert_entity_contract(tmp_path):
    graph = KnowledgeGraph(graph_path=str(tmp_path / "kg.json"))
    eid = graph.upsert_entity("Tara", "PERSON", "/docs/a.txt")
    assert eid == "PERSON:tara"
    graph.upsert_entity("Tara", "PERSON", "/docs/b.txt")
    graph.upsert_entity("Tara", "PERSON", "/docs/b.txt")
    assert graph.get_entity(eid) == {
        "entity_id": "PERSON:tara",
        "name": "Tara",
        "entity_type": "PERSON",
        "mention_count": 3,
        "source_docs": ["/docs/a.txt", "/docs/b.txt"],
    }
    assert graph.dirty is True


@pytest.mark.xfail(raises=NotImplementedError, strict=True, reason="TODO: co-occurrence linking")
def test_link_entities_contract(tmp_path):
    graph = KnowledgeGraph(graph_path=str(tmp_path / "kg.json"))
    for name in ("A1", "B1"):
        graph.graph.add_node(f"PERSON:{name.lower()}", entity_id=f"PERSON:{name.lower()}", name=name,
                             entity_type="PERSON", mention_count=1, source_docs=["/d1"])
    graph.link_entities("PERSON:a1", "PERSON:b1", "/d1")
    graph.link_entities("PERSON:b1", "PERSON:a1", "/d2")
    graph.link_entities("PERSON:a1", "PERSON:a1", "/d1")
    (node, edge), = graph.get_neighbors("PERSON:a1")
    assert node["entity_id"] == "PERSON:b1"
    assert edge["co_occurrence_count"] == 2
    assert edge["shared_docs"] == ["/d1", "/d2"]
    assert not graph.graph.has_edge("PERSON:a1", "PERSON:a1")
    assert graph.dirty is True
