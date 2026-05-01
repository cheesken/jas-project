import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List

from services.query import search, count
from services.ollama import OllamaService, OllamaUnavailableError, OllamaTimeoutError

logger = logging.getLogger(__name__)
router = APIRouter()


class ResultModel(BaseModel):
    chunk_id: str
    content: str
    file_name: str
    source_type: str
    last_modified: str
    score: float


class QueryResponse(BaseModel):
    results: List[ResultModel]
    response: str


@router.get("/query", response_model=QueryResponse)
def get_query(
    q: str = Query(..., min_length=1),
    top_k: int = Query(10, ge=1, le=50),
):
    # Detect empty DB. Uses the services.query singleton — do NOT instantiate
    # VectorStore() here directly; that would create a redundant ChromaDB PersistentClient.
    if count() == 0:
        return QueryResponse(
            results=[],
            response="No documents have been indexed yet. Please upload a PDF first.",
        )

    # Whitespace-only queries pass Pydantic's min_length=1 but are rejected by QueryService.
    try:
        results = search(query=q, k=top_k)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not results:
        return QueryResponse(
            results=[],
            response="No matches for that query. Try different wording.",
        )

    try:
        ollama = OllamaService()
        llm_response = ollama.generate(query=q, context_chunks=[r.content for r in results])
    except (OllamaUnavailableError, OllamaTimeoutError):
        logger.exception("Ollama call failed; falling back to results-only response")
        llm_response = "LLM unavailable. Showing raw search results only."

    # source_path is intentionally NOT exposed — only file_name goes to the frontend.
    return QueryResponse(
        results=[
            ResultModel(
                chunk_id=r.chunk_id,
                content=r.content,
                file_name=r.file_name,
                source_type=r.source_type,
                last_modified=r.last_modified,
                score=r.score,
            )
            for r in results
        ],
        response=llm_response,
    )
