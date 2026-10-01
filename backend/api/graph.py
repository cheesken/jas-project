import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.graph import get_graph

router = APIRouter()


class EntityModel(BaseModel):
    entity_id: str
    name: str
    entity_type: str
    mention_count: int
    doc_count: int


class EdgeModel(BaseModel):
    entity_a: str
    entity_b: str
    co_occurrence_count: int


class GraphResponse(BaseModel):
    nodes: List[EntityModel]
    edges: List[EdgeModel]


class DocModel(BaseModel):
    file_name: str


class NeighborModel(EntityModel):
    co_occurrence_count: int
    shared_docs: List[DocModel]


class EntityDetailResponse(BaseModel):
    entity: EntityModel
    neighbors: List[NeighborModel]
    docs: List[DocModel]


class EntitySearchResponse(BaseModel):
    results: List[EntityModel]


def _entity(e: dict) -> EntityModel:
    return EntityModel(
        entity_id=e["entity_id"],
        name=e["name"],
        entity_type=e["entity_type"],
        mention_count=e["mention_count"],
        doc_count=len(e["source_docs"]),
    )


def _docs(paths: List[str]) -> List[DocModel]:
    return [DocModel(file_name=os.path.basename(p)) for p in paths]


@router.get("/graph", response_model=GraphResponse)
def get_full_graph(
    entity_type: Optional[str] = Query(None),
    min_mentions: int = Query(1, ge=1),
    limit: Optional[int] = Query(None, ge=1, le=5000),
):
    nodes, edges = get_graph().subgraph(
        entity_type=entity_type.upper() if entity_type else None,
        min_mentions=min_mentions,
        limit=limit,
    )
    return GraphResponse(
        nodes=[_entity(n) for n in nodes],
        edges=[
            EdgeModel(
                entity_a=e["entity_a"],
                entity_b=e["entity_b"],
                co_occurrence_count=e["co_occurrence_count"],
            )
            for e in edges
        ],
    )


@router.get("/graph/search", response_model=EntitySearchResponse)
def search_graph(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
):
    return EntitySearchResponse(results=[_entity(e) for e in get_graph().search_entities(q, limit=limit)])


@router.get("/graph/{entity_id}", response_model=EntityDetailResponse)
def get_entity(entity_id: str, neighbor_limit: int = Query(50, ge=1, le=500)):
    kg = get_graph()
    entity = kg.get_entity(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    neighbors = [
        NeighborModel(
            **_entity(node).model_dump(),
            co_occurrence_count=edge.get("co_occurrence_count", 0),
            shared_docs=_docs(edge.get("shared_docs", [])),
        )
        for node, edge in kg.get_neighbors(entity_id, limit=neighbor_limit)
    ]
    return EntityDetailResponse(entity=_entity(entity), neighbors=neighbors, docs=_docs(entity["source_docs"]))
