import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from services.embedding import EmbeddingService
from services.graph import KnowledgeGraph, get_graph, normalize_name
from services.vector_store import VectorStore

logger = logging.getLogger(__name__)

SOURCE_TYPES = {
    "pdf": "Document",
    "txt": "Document",
    "image": "Image",
    "browser_history": "Browser History",
}

DIRECT_BOOST = 0.15
NEIGHBOR_BOOST = 0.05
MAX_NEIGHBORS = 10


@dataclass
class Result:
    chunk_id: str
    content: str
    source_path: str
    file_name: str
    source_type: str
    score: float
    last_modified: str
    entities: List[str] = field(default_factory=list)


# Sources that pack many independent entries into one file. The graph records
# them per file, so a boost must be earned by the chunk itself mentioning the
# entity; otherwise one visit naming "Sara" would boost every page in History.
PER_ENTRY_SOURCES = {"browser_history"}


@dataclass
class KGContext:
    boosts: Dict[str, float] = field(default_factory=dict)
    entities: Dict[str, List[str]] = field(default_factory=dict)
    name_boosts: Dict[str, Dict[str, float]] = field(default_factory=dict)


class QueryService:
    def __init__(self) -> None:
        self.k = 10
        self._embedder = EmbeddingService()
        self._store = VectorStore()

    def search(self, query: str, k: Optional[int] = None) -> List[Result]:
        if query.strip() == "":
            raise ValueError("Query must not be empty")
        effective_k = k if k is not None else self.k

        query_vector = self._embedder.embed(query)
        raw = self._store.query(query_vector, k=effective_k)

        kg_context = self._kg_context(query)
        raw = self.merge_kg_results(raw, self._fetch_kg_chunks(query_vector, raw, kg_context, effective_k))

        results = [self._to_result(r, kg_context) for r in raw]
        return self.rank_results(results)[:effective_k]

    def count(self) -> int:
        return self._store.count()

    def _graph(self) -> KnowledgeGraph:
        return get_graph()

    def _kg_context(self, query: str) -> KGContext:
        context = KGContext()
        try:
            kg = self._graph()
            matched = kg.find_entities(query)
        except Exception:
            logger.exception("Knowledge graph lookup failed; using vector results only")
            return context

        for entity_id in matched:
            entity = kg.get_entity(entity_id)
            if entity is None:
                continue
            self._apply(context, entity["source_docs"], DIRECT_BOOST, entity["name"])

            neighbors = kg.get_neighbors(entity_id, limit=MAX_NEIGHBORS)
            top_count = max((e.get("co_occurrence_count", 0) for _, e in neighbors), default=0)
            for node, edge in neighbors:
                weight = edge.get("co_occurrence_count", 0) / top_count if top_count else 0.0
                self._apply(context, node["source_docs"], NEIGHBOR_BOOST * weight, node["name"])
        return context

    @staticmethod
    def _apply(context: KGContext, docs: List[str], boost: float, name: str) -> None:
        for doc in docs:
            context.boosts[doc] = max(context.boosts.get(doc, 0.0), boost)
            names = context.entities.setdefault(doc, [])
            if name not in names:
                names.append(name)
            per_name = context.name_boosts.setdefault(doc, {})
            per_name[name] = max(per_name.get(name, 0.0), boost)

    def _fetch_kg_chunks(
        self,
        query_vector: List[float],
        raw: List[dict],
        context: KGContext,
        k: int,
    ) -> List[dict]:
        seen: Set[str] = {r["metadata"]["source_path"] for r in raw}
        missing = sorted(
            (doc for doc in context.boosts if doc not in seen),
            key=lambda d: -context.boosts[d],
        )[:k]
        if not missing:
            return []
        try:
            extra = self._store.query(query_vector, k=k, where={"source_path": {"$in": missing}})
        except Exception:
            logger.exception("Knowledge graph chunk lookup failed")
            return []

        best: Dict[str, dict] = {}
        for r in extra:
            path = r["metadata"]["source_path"]
            if path not in best or r["distance"] < best[path]["distance"]:
                best[path] = r
        return list(best.values())

    @staticmethod
    def merge_kg_results(vector_results: List[dict], kg_results: List[dict]) -> List[dict]:
        merged = list(vector_results)
        ids = {r["id"] for r in vector_results}
        merged.extend(r for r in kg_results if r["id"] not in ids)
        return merged

    @staticmethod
    def rank_results(results: List[Result]) -> List[Result]:
        return sorted(results, key=lambda r: r.score, reverse=True)

    @staticmethod
    def _to_result(r: dict, context: KGContext) -> Result:
        path = r["metadata"]["source_path"]
        similarity = 1.0 - r["distance"]
        boost = context.boosts.get(path, 0.0)
        entities = list(context.entities.get(path, []))
        if r["metadata"].get("file_type") in PER_ENTRY_SOURCES:
            text = f" {normalize_name(r['document'])} "
            entities = [n for n in entities if f" {normalize_name(n)} " in text]
            boost = max((context.name_boosts.get(path, {})[n] for n in entities), default=0.0)
        return Result(
            chunk_id=r["id"],
            content=r["document"],
            source_path=path,
            # Browser history chunks all share one source file ("History"), so the
            # page title is the meaningful name to show on the result card.
            file_name=r["metadata"].get("title") or os.path.basename(path),
            source_type=SOURCE_TYPES.get(r["metadata"].get("file_type"), "Document"),
            score=max(0.0, min(1.0, similarity + boost)),
            last_modified=r["metadata"]["last_modified"],
            entities=entities,
        )


_service: Optional[QueryService] = None


def _get_service() -> QueryService:
    global _service
    if _service is None:
        _service = QueryService()
    return _service


def search(query: str, k: int = 10) -> List[Result]:
    return _get_service().search(query, k=k)


def count() -> int:
    return _get_service().count()
