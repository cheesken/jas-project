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


def _graph_with(tmp_path, *names):
    graph = KnowledgeGraph(graph_path=str(tmp_path / "kg.json"))
    for name in names:
        eid = make_entity_id(name, "PERSON")
        graph.graph.add_node(eid, entity_id=eid, name=name, entity_type="PERSON",
                             mention_count=1, source_docs=["/d1"])
    return graph


def test_link_entities_stores_schema_edge_attrs(tmp_path):
    graph = _graph_with(tmp_path, "Tara", "Sam")
    graph.link_entities("PERSON:tara", "PERSON:sam", "/d1")
    assert dict(graph.graph.edges["PERSON:tara", "PERSON:sam"]) == {
        "entity_a": "PERSON:tara",
        "entity_b": "PERSON:sam",
        "co_occurrence_count": 1,
        "shared_docs": ["/d1"],
        "doc_counts": {"/d1": 1},
    }


def test_link_entities_same_doc_counts_but_does_not_duplicate_doc(tmp_path):
    graph = _graph_with(tmp_path, "Tara", "Sam")
    graph.link_entities("PERSON:tara", "PERSON:sam", "/history")
    graph.link_entities("PERSON:sam", "PERSON:tara", "/history")
    edge = graph.graph.edges["PERSON:tara", "PERSON:sam"]
    assert edge["co_occurrence_count"] == 2
    assert edge["shared_docs"] == ["/history"]


def test_link_entities_unknown_entity_raises(tmp_path):
    graph = _graph_with(tmp_path, "Tara")
    with pytest.raises(ValueError):
        graph.link_entities("PERSON:tara", "PERSON:ghost", "/d1")
    assert "PERSON:ghost" not in graph.graph
    assert graph.dirty is False


def test_self_link_does_not_mark_dirty(tmp_path):
    graph = _graph_with(tmp_path, "Tara")
    graph.link_entities("PERSON:tara", "PERSON:tara", "/d1")
    assert graph.dirty is False


def test_link_cooccurring_links_every_pair_once(tmp_path):
    graph = _graph_with(tmp_path, "A1", "B1", "C1")
    linked = graph.link_cooccurring(["PERSON:a1", "PERSON:b1", "PERSON:c1", "PERSON:a1"], "/d1")
    assert linked == 3
    assert graph.graph.number_of_edges() == 3
    assert all(attrs["co_occurrence_count"] == 1 for _, _, attrs in graph.graph.edges(data=True))


def test_link_cooccurring_caps_to_most_mentioned(tmp_path):
    graph = _graph_with(tmp_path, "A1", "B1", "C1")
    mentions = ["PERSON:c1", "PERSON:a1", "PERSON:a1", "PERSON:b1", "PERSON:b1"]
    assert graph.link_cooccurring(mentions, "/d1", max_entities=2) == 1
    assert graph.graph.has_edge("PERSON:a1", "PERSON:b1")
    assert graph.graph.degree("PERSON:c1") == 0


def test_link_cooccurring_single_entity_links_nothing(tmp_path):
    graph = _graph_with(tmp_path, "A1")
    assert graph.link_cooccurring(["PERSON:a1", "PERSON:a1"], "/d1") == 0
    assert graph.dirty is False


def test_locked_reloads_and_saves_changes(kg_path):
    writer = KnowledgeGraph(graph_path=kg_path)
    with writer.locked() as kg:
        assert kg.node_count() == 9
        kg.link_entities("PERSON:tara", "ORG:park_hyatt", "/Users/test/docs/trip.pdf")
    assert writer.dirty is False

    reader = KnowledgeGraph(graph_path=kg_path)
    reader.load()
    assert reader.graph.has_edge("PERSON:tara", "ORG:park_hyatt")


def test_locked_sees_writes_made_by_another_instance(kg_path):
    first = KnowledgeGraph(graph_path=kg_path)
    first.load()
    with KnowledgeGraph(graph_path=kg_path).locked() as other:
        other.link_entities("PERSON:tara", "GPE:tokyo", "/d")
    with first.locked() as kg:
        assert kg.graph.has_edge("PERSON:tara", "GPE:tokyo")


def test_locked_without_changes_does_not_rewrite_file(kg_path):
    os.utime(kg_path, (1, 1))
    with KnowledgeGraph(graph_path=kg_path).locked():
        pass
    assert os.path.getmtime(kg_path) == 1


def _ingest(graph, doc, *mention_groups):
    """Simulate the worker: upsert each group's mentions, then link them."""
    for names in mention_groups:
        ids = [graph.upsert_entity(n, "PERSON", doc) for n in names]
        graph.link_cooccurring(ids, doc)


def test_upsert_tracks_mentions_per_document(tmp_path):
    graph = KnowledgeGraph(graph_path=str(tmp_path / "kg.json"))
    graph.upsert_entity("Tara", "PERSON", "/a")
    graph.upsert_entity("Tara", "PERSON", "/a")
    graph.upsert_entity("Tara", "PERSON", "/b")
    assert graph.graph.nodes["PERSON:tara"]["doc_mentions"] == {"/a": 2, "/b": 1}
    assert graph.get_entity("PERSON:tara")["mention_count"] == 3


def test_reingest_after_remove_document_does_not_inflate_counts(tmp_path):
    graph = KnowledgeGraph(graph_path=str(tmp_path / "kg.json"))
    _ingest(graph, "/notes.txt", ["Tara", "Sam"])
    _ingest(graph, "/other.txt", ["Tara", "Sam"])
    before_node = graph.get_entity("PERSON:tara")
    before_edge = dict(graph.graph.edges["PERSON:tara", "PERSON:sam"])

    graph.remove_document("/notes.txt")
    _ingest(graph, "/notes.txt", ["Tara", "Sam"])

    assert graph.get_entity("PERSON:tara")["mention_count"] == before_node["mention_count"] == 2
    edge = graph.graph.edges["PERSON:tara", "PERSON:sam"]
    assert edge["co_occurrence_count"] == before_edge["co_occurrence_count"] == 2
    assert sorted(edge["shared_docs"]) == ["/notes.txt", "/other.txt"]


def test_remove_document_drops_entities_and_edges_only_it_supported(tmp_path):
    graph = KnowledgeGraph(graph_path=str(tmp_path / "kg.json"))
    _ingest(graph, "/history", ["Tara", "Ghost"], ["Tara", "Sam"])
    _ingest(graph, "/notes.txt", ["Tara", "Sam"])
    graph.dirty = False

    assert graph.remove_document("/history") is True
    assert graph.dirty is True
    assert graph.get_entity("PERSON:ghost") is None
    assert graph.find_entities("ghost stories") == []
    assert graph.get_entity("PERSON:tara") == {
        "entity_id": "PERSON:tara", "name": "Tara", "entity_type": "PERSON",
        "mention_count": 1, "source_docs": ["/notes.txt"],
    }
    edge = graph.graph.edges["PERSON:tara", "PERSON:sam"]
    assert (edge["co_occurrence_count"], edge["shared_docs"]) == (1, ["/notes.txt"])


def test_remove_unknown_document_is_a_no_op(kg):
    assert kg.remove_document("/never/indexed.pdf") is False
    assert kg.dirty is False
    assert kg.node_count() == 9


def test_remove_document_handles_graphs_saved_before_per_doc_counts(kg):
    # The fixture predates doc_mentions/doc_counts: Tara has 2 mentions across 2 docs.
    kg.remove_document("/Users/test/notes/whatsapp_export.txt")
    tara = kg.get_entity("PERSON:tara")
    assert tara["mention_count"] == 1
    assert tara["source_docs"] == ["/Users/test/notes/meeting_notes_q1.txt"]
    assert kg.get_entity("ORG:noosh_noshery") is None  # only whatsapp_export mentioned it
