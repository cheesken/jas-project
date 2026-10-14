"""
Retrieval benchmark (sprint 10A, workbook section 7.2).

    python -m benchmark.retrieval [--size 500] [--out benchmark/results]

Builds the labelled corpus, indexes it with the production pipeline into a
throwaway store, and scores three systems on the 50 queries:

- bm25:        BM25 keyword ranking (rank_bm25) over the same chunks.
- semantic:    the production QueryService with the knowledge graph turned off.
- semantic+kg: the production QueryService as the app runs it.

Chunks are rolled up to documents (best chunk wins), and each system's top 10
documents are scored with NDCG@10, P@5 and MRR. Writes a JSON and a Markdown
report to --out. Run inside the backend image (see benchmark/README.md).
"""
import argparse
import json
import os
import platform
import re
import tempfile
import time
from datetime import datetime, timezone
from typing import Dict, List

from benchmark.indexer import index_corpus, use_work_dir
from benchmark.metrics import mean_scores, score_query
from benchmark.scenarios import SCENARIOS

SYSTEMS = ("bm25", "semantic", "semantic+kg")
TARGETS = {"ndcg@10": 0.65, "p@5": 0.60, "mrr": 0.65}
CHUNK_DEPTH = 50  # chunks fetched per query before rolling up to 10 documents
KINDS = ("keyword", "phrase", "question")

STOPWORDS = set("""a an and are as at be by did do does for from how i in is it my me of on or should
the this to was what when where which who will with you your this that did""".split())


def tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def _unique(ids: List[str], limit: int = 10) -> List[str]:
    out: List[str] = []
    for i in ids:
        if i not in out:
            out.append(i)
            if len(out) == limit:
                break
    return out


class Systems:
    def __init__(self, corpus_dir: str) -> None:
        from rank_bm25 import BM25Okapi
        from services.graph import KnowledgeGraph
        from services.query import QueryService

        self.corpus_dir = corpus_dir
        self.service = QueryService()
        got = self.service._store._collection.get(include=["documents", "metadatas"])
        self.chunk_ids = got["ids"]
        self.chunk_doc = {cid: self._doc_id(meta) for cid, meta in zip(got["ids"], got["metadatas"])}
        self.bm25 = BM25Okapi([tokenize(d) for d in got["documents"]])
        self._empty_graph = KnowledgeGraph(graph_path=os.path.join(tempfile.mkdtemp(), "none.json"))

    def _doc_id(self, meta: dict) -> str:
        if meta.get("file_type") == "browser_history":
            return f"history:{meta['url']}"
        return os.path.relpath(meta["source_path"], self.corpus_dir)

    def rank(self, system: str, query: str) -> List[str]:
        if system == "bm25":
            scores = self.bm25.get_scores(tokenize(query))
            order = sorted(range(len(scores)), key=lambda i: -scores[i])
            return _unique([self.chunk_doc[self.chunk_ids[i]] for i in order[:CHUNK_DEPTH] if scores[i] > 0])
        if system == "semantic":
            self.service._graph = lambda: self._empty_graph
        try:
            results = self.service.search(query, k=CHUNK_DEPTH)
        finally:
            self.service.__dict__.pop("_graph", None)
        return _unique([self.chunk_doc[r.chunk_id] for r in results])


def run(size: int, out_dir: str, work_dir: str) -> dict:
    corpus_dir = os.path.join(work_dir, "corpus")
    use_work_dir(os.path.join(work_dir, "index"))
    from benchmark.corpus import write_corpus  # after use_work_dir: nothing reads settings at import

    manifest = write_corpus(corpus_dir, size)
    with open(os.path.join(corpus_dir, "qrels.json")) as f:
        qrels = json.load(f)
    index_stats = index_corpus(corpus_dir)
    systems = Systems(corpus_dir)

    per_query = []
    started = time.perf_counter()
    for s in SCENARIOS:
        row = {"id": s["id"], "kind": s["kind"], "query": s["query"], "systems": {}}
        for name in SYSTEMS:
            ranked = systems.rank(name, s["query"])
            row["systems"][name] = {**score_query(ranked, qrels[s["id"]]), "top10": ranked}
        per_query.append(row)
    query_seconds = time.perf_counter() - started

    summary = {name: {"all": mean_scores([q["systems"][name] for q in per_query])} for name in SYSTEMS}
    for name in SYSTEMS:
        for kind in KINDS:
            summary[name][kind] = mean_scores([q["systems"][name] for q in per_query if q["kind"] == kind])
    for row in per_query:  # keep the JSON readable: metric values only in summaries
        for sysrow in row["systems"].values():
            for m in ("ndcg@10", "p@5", "mrr", "answer_mrr"):
                sysrow[m] = round(sysrow[m], 4)

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "corpus": {"size": manifest["size"], "counts": manifest["counts"], "queries": len(SCENARIOS),
                   "query_kinds": {k: sum(s["kind"] == k for s in SCENARIOS) for k in KINDS},
                   "chunks": len(systems.chunk_ids)},
        "config": {"embedding_model": os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
                   "ner_model": os.environ.get("NER_MODEL", "en_core_web_sm"),
                   "chunk_depth": CHUNK_DEPTH, "python": platform.python_version()},
        "timing": {"index_seconds": round(index_stats["seconds"], 1), "query_seconds": round(query_seconds, 1)},
        "targets": TARGETS,
        "summary": summary,
        "per_query": per_query,
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"retrieval_{size}.json"), "w") as f:
        json.dump(report, f, indent=1)
    with open(os.path.join(out_dir, f"retrieval_{size}.md"), "w") as f:
        f.write(to_markdown(report))
    return report


def _fmt(v: float) -> str:
    return f"{v:.3f}"


def to_markdown(r: dict) -> str:
    s = r["summary"]
    lines = [
        f"# Retrieval benchmark ({r['corpus']['size']} documents)",
        "",
        f"Run {r['run_at']}. {r['corpus']['queries']} queries ({', '.join(f'{n} {k}' for k, n in r['corpus']['query_kinds'].items())}), "
        f"{r['corpus']['size']} documents ({', '.join(f'{n} {t}' for t, n in r['corpus']['counts'].items())}), "
        f"{r['corpus']['chunks']} chunks. Embedding model `{r['config']['embedding_model']}`, NER model `{r['config']['ner_model']}`. "
        f"Indexing took {r['timing']['index_seconds']} s.",
        "",
        "| System | NDCG@10 | P@5 | MRR | Answer MRR |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name in SYSTEMS:
        a = s[name]["all"]
        lines.append(f"| {name} | {_fmt(a['ndcg@10'])} | {_fmt(a['p@5'])} | {_fmt(a['mrr'])} | {_fmt(a['answer_mrr'])} |")
    t = r["targets"]
    lines += ["", f"Targets (workbook 7.2): NDCG@10 >= {t['ndcg@10']}, P@5 >= {t['p@5']}, MRR >= {t['mrr']}. "
                  "P@5 counts grade 1 and 2 as relevant; each query has 4 relevant documents, so the best possible P@5 is 0.80. "
                  "Answer MRR is the reciprocal rank of the document that answers the query (grade 2).", ""]
    lines += ["## NDCG@10 by query kind", "", "| System | " + " | ".join(KINDS) + " |", "| --- |" + " --- |" * len(KINDS)]
    for name in SYSTEMS:
        lines.append(f"| {name} | " + " | ".join(_fmt(s[name][k]["ndcg@10"]) for k in KINDS) + " |")
    lines += ["", "## Per query (NDCG@10)", "", "| Query | Kind | " + " | ".join(SYSTEMS) + " |", "| --- | --- |" + " --- |" * len(SYSTEMS)]
    for q in r["per_query"]:
        lines.append(f"| {q['id']}: {q['query']} | {q['kind']} | " + " | ".join(_fmt(q["systems"][n]["ndcg@10"]) for n in SYSTEMS) + " |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--size", type=int, default=500)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "results"))
    ap.add_argument("--work-dir", default=None, help="defaults to a fresh temp dir")
    args = ap.parse_args()
    report = run(args.size, args.out, args.work_dir or tempfile.mkdtemp(prefix="bench-"))
    print(to_markdown(report).split("## NDCG@10 by query kind")[0])


if __name__ == "__main__":
    main()
