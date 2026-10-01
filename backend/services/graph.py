import fcntl
import json
import logging
import os
import re
import tempfile
from collections import Counter
from contextlib import contextmanager
from itertools import combinations
from typing import Dict, Iterator, List, Optional, Tuple

import networkx as nx


logger = logging.getLogger(__name__)

ENTITY_TYPES = ("PERSON", "ORG", "GPE", "DATE")

NODE_ATTRS = ("entity_id", "name", "entity_type", "mention_count", "source_docs")
EDGE_ATTRS = ("entity_a", "entity_b", "co_occurrence_count", "shared_docs")

MIN_MATCH_LENGTH = 3
MAX_NAME_TOKENS = 6
MAX_LINKED_ENTITIES = 50


def normalize_name(name: str) -> str:
    text = re.sub(r"['’]s\b", "", name.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def make_entity_id(name: str, entity_type: str) -> str:
    return f"{entity_type.upper()}:{normalize_name(name).replace(' ', '_')}"


class KnowledgeGraph:
    def __init__(self, graph_path: Optional[str] = None) -> None:
        self.graph_path = graph_path or os.environ.get("KG_PATH", "/data/kg.json")
        self.graph = nx.Graph()
        self.dirty = False
        self._mtime: Optional[float] = None
        self._name_index: Dict[str, List[str]] = {}

    def load(self) -> None:
        try:
            mtime = os.path.getmtime(self.graph_path)
        except FileNotFoundError:
            self.graph = nx.Graph()
            self._mtime = None
            self._rebuild_index()
            return

        try:
            with open(self.graph_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            graph = nx.node_link_graph(data, directed=False, multigraph=False, edges="edges")
        except (OSError, ValueError, KeyError, nx.NetworkXError):
            logger.exception("Could not load knowledge graph from %s; keeping previous graph", self.graph_path)
            return

        self.graph = graph
        self._mtime = mtime
        self.dirty = False
        self._rebuild_index()

    def reload_if_changed(self) -> None:
        try:
            mtime = os.path.getmtime(self.graph_path)
        except FileNotFoundError:
            mtime = None
        if mtime != self._mtime:
            self.load()

    def save(self) -> None:
        directory = os.path.dirname(self.graph_path) or "."
        os.makedirs(directory, exist_ok=True)
        data = nx.node_link_data(self.graph, edges="edges")
        fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".kg-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp_path, self.graph_path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
        self._mtime = os.path.getmtime(self.graph_path)
        self.dirty = False

    def upsert_entity(self, name: str, entity_type: str, source_doc: str) -> str:
        # TODO: implement entity upsert
        raise NotImplementedError("upsert_entity is not implemented yet")

    def link_entities(self, entity_a: str, entity_b: str, doc_id: str) -> None:
        if entity_a == entity_b:
            return
        for entity_id in (entity_a, entity_b):
            if entity_id not in self.graph:
                raise ValueError(f"Cannot link unknown entity: {entity_id}")

        if self.graph.has_edge(entity_a, entity_b):
            attrs = self.graph.edges[entity_a, entity_b]
            attrs["co_occurrence_count"] = attrs.get("co_occurrence_count", 0) + 1
            shared = attrs.setdefault("shared_docs", [])
            if doc_id not in shared:
                shared.append(doc_id)
        else:
            self.graph.add_edge(
                entity_a,
                entity_b,
                entity_a=entity_a,
                entity_b=entity_b,
                co_occurrence_count=1,
                shared_docs=[doc_id],
            )
        self.dirty = True

    def link_cooccurring(
        self,
        entity_ids: List[str],
        doc_id: str,
        max_entities: int = MAX_LINKED_ENTITIES,
    ) -> int:
        """Link every pair of entities that appear together in one document.

        Pass one id per mention; repeats rank an entity higher. Only the
        `max_entities` most-mentioned are linked, since pairs grow quadratically.
        For browser history, call this once per visit (chunk), not once for the
        whole History file. Returns the number of pairs linked.
        """
        counts = Counter(entity_ids)
        # Counter keeps first-seen order and sorted() is stable, so ties stay in text order.
        ranked = sorted(counts, key=lambda e: -counts[e])[:max_entities]
        pairs = list(combinations(ranked, 2))
        for a, b in pairs:
            self.link_entities(a, b, doc_id)
        return len(pairs)

    @contextmanager
    def locked(self) -> Iterator["KnowledgeGraph"]:
        """Load, modify and save kg.json under an exclusive file lock.

        The Celery worker runs several processes that update the graph, so each
        update must re-read the latest file, change it and save before releasing
        the lock. Saves only if something changed.
        """
        directory = os.path.dirname(self.graph_path) or "."
        os.makedirs(directory, exist_ok=True)
        with open(self.graph_path + ".lock", "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                self.load()
                yield self
                if self.dirty:
                    self.save()
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)

    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    def get_entity(self, entity_id: str) -> Optional[dict]:
        if entity_id not in self.graph:
            return None
        return self._node(entity_id)

    def get_neighbors(self, entity_id: str, limit: Optional[int] = None) -> List[Tuple[dict, dict]]:
        if entity_id not in self.graph:
            return []
        pairs = [
            (self._node(n), dict(self.graph.edges[entity_id, n]))
            for n in self.graph.neighbors(entity_id)
        ]
        pairs.sort(key=lambda p: (-p[1].get("co_occurrence_count", 0), p[0]["name"]))
        return pairs[:limit] if limit is not None else pairs

    def find_entities(self, text: str) -> List[str]:
        tokens = normalize_name(text).split()
        matched: List[str] = []
        i = 0
        while i < len(tokens):
            for n in range(min(MAX_NAME_TOKENS, len(tokens) - i), 0, -1):
                phrase = " ".join(tokens[i:i + n])
                ids = self._name_index.get(phrase)
                if ids:
                    matched.extend(e for e in ids if e not in matched)
                    i += n
                    break
            else:
                i += 1
        return matched

    def search_entities(self, query: str, limit: int = 20) -> List[dict]:
        needle = normalize_name(query)
        if not needle:
            return []
        hits = [
            self._node(n)
            for n, attrs in self.graph.nodes(data=True)
            if needle in normalize_name(attrs.get("name", ""))
        ]
        hits.sort(key=lambda e: (-e["mention_count"], e["name"]))
        return hits[:limit]

    def subgraph(
        self,
        entity_type: Optional[str] = None,
        min_mentions: int = 1,
        limit: Optional[int] = None,
    ) -> Tuple[List[dict], List[dict]]:
        nodes = [
            self._node(n)
            for n, attrs in self.graph.nodes(data=True)
            if (entity_type is None or attrs.get("entity_type") == entity_type)
            and attrs.get("mention_count", 0) >= min_mentions
        ]
        nodes.sort(key=lambda e: (-e["mention_count"], e["name"]))
        if limit is not None:
            nodes = nodes[:limit]
        kept = {e["entity_id"] for e in nodes}
        edges = [
            {
                "entity_a": a,
                "entity_b": b,
                "co_occurrence_count": attrs.get("co_occurrence_count", 0),
                "shared_docs": list(attrs.get("shared_docs", [])),
            }
            for a, b, attrs in self.graph.edges(data=True)
            if a in kept and b in kept
        ]
        return nodes, edges

    def _node(self, entity_id: str) -> dict:
        attrs = self.graph.nodes[entity_id]
        return {
            "entity_id": entity_id,
            "name": attrs.get("name", entity_id),
            "entity_type": attrs.get("entity_type", "UNKNOWN"),
            "mention_count": attrs.get("mention_count", 0),
            "source_docs": list(attrs.get("source_docs", [])),
        }

    def _rebuild_index(self) -> None:
        index: Dict[str, List[str]] = {}
        for n, attrs in self.graph.nodes(data=True):
            key = normalize_name(attrs.get("name", ""))
            if len(key) < MIN_MATCH_LENGTH:
                continue
            index.setdefault(key, []).append(n)
        self._name_index = index


_graph: Optional[KnowledgeGraph] = None


def get_graph() -> KnowledgeGraph:
    global _graph
    if _graph is None:
        _graph = KnowledgeGraph()
    _graph.reload_if_changed()
    return _graph
