"""
Ranking metrics for the retrieval benchmark (workbook section 7.2).

`ranked` is a list of document ids, best first. `qrels` maps a document id to
its graded relevance: 2 answers the query, 1 is related, absent means 0.
"""
import math
from typing import Dict, List

RELEVANT = 1  # binary metrics count a document as relevant at grade >= 1
ANSWER = 2


def ndcg_at_k(ranked: List[str], qrels: Dict[str, int], k: int = 10) -> float:
    """Normalized DCG with exponential gain (2^rel - 1), the TREC convention."""
    def dcg(grades: List[int]) -> float:
        return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(grades))

    actual = dcg([qrels.get(d, 0) for d in ranked[:k]])
    ideal = dcg(sorted(qrels.values(), reverse=True)[:k])
    return actual / ideal if ideal else 0.0


def precision_at_k(ranked: List[str], qrels: Dict[str, int], k: int = 5) -> float:
    """Share of the top k that is relevant; fewer than k results count as misses."""
    return sum(qrels.get(d, 0) >= RELEVANT for d in ranked[:k]) / k


def reciprocal_rank(ranked: List[str], qrels: Dict[str, int], min_grade: int = RELEVANT) -> float:
    """1/rank of the first document at or above min_grade, 0 if none is ranked."""
    for i, d in enumerate(ranked):
        if qrels.get(d, 0) >= min_grade:
            return 1.0 / (i + 1)
    return 0.0


def score_query(ranked: List[str], qrels: Dict[str, int]) -> Dict[str, float]:
    return {
        "ndcg@10": ndcg_at_k(ranked, qrels, 10),
        "p@5": precision_at_k(ranked, qrels, 5),
        "mrr": reciprocal_rank(ranked, qrels),
        # Stricter: how high the document that actually answers the query lands.
        "answer_mrr": reciprocal_rank(ranked, qrels, ANSWER),
    }


def mean_scores(per_query: List[Dict[str, float]]) -> Dict[str, float]:
    if not per_query:
        return {}
    metrics = [m for m, v in per_query[0].items() if isinstance(v, (int, float))]
    return {m: sum(q[m] for q in per_query) / len(per_query) for m in metrics}
