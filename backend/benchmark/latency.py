"""
Query latency benchmark (sprint 10B, US-NF-02).

    python -m benchmark.latency [--size 1000] [--per-kind 5] [--out benchmark/results]

Indexes a corpus of --size documents with the production pipeline (throwaway
store), serves the real FastAPI app with uvicorn, and sends queries to
/query/stream (the endpoint the desktop app uses), timing each one:

- results: until the result cards arrive. This is what US-NF-02 measures
  ("search results appear within an average of 30 seconds").
- answer:  until the local LLM's answer has finished streaming.

Queries mix the three kinds from workbook 7.2 (single keyword, multi-word
phrase, natural-language question): --per-kind of each from the benchmark set.
A warm-up query runs first so the one-off model load isn't counted. Needs
Ollama reachable at OLLAMA_URL for the answer timings.
"""
import argparse
import json
import os
import statistics
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List

from benchmark.indexer import index_corpus, use_work_dir
from benchmark.scenarios import SCENARIOS

TARGET_SECONDS = 30.0
KINDS = ("keyword", "phrase", "question")
LLM_DOWN = "LLM unavailable"


@contextmanager
def serve_api(port: int = 8765):
    import threading

    import uvicorn
    from api.main import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        if not thread.is_alive():
            raise RuntimeError("benchmark API server failed to start")
        time.sleep(0.1)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=30)


def pick_queries(per_kind: int) -> List[dict]:
    picked = []
    for kind in KINDS:
        picked += [s for s in SCENARIOS if s["kind"] == kind][:per_kind]
    return picked


def time_query(base_url: str, query: str, top_k: int = 10) -> Dict[str, float]:
    import requests

    start = time.perf_counter()
    t_results = t_answer = None
    n_results, answer = 0, ""
    with requests.get(f"{base_url}/query/stream", params={"q": query, "top_k": top_k}, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            if event["type"] == "results" and t_results is None:
                t_results = time.perf_counter() - start
                n_results = len(event["results"])
            elif event["type"] == "token":
                answer += event["token"]
            elif event["type"] in ("done", "error"):
                t_answer = time.perf_counter() - start
                break
    return {"results_s": t_results, "answer_s": t_answer, "n_results": n_results,
            "llm_ok": bool(answer) and LLM_DOWN not in answer}


def _stats(values: List[float]) -> Dict[str, float]:
    values = sorted(v for v in values if v is not None)
    if not values:
        return {}
    p95 = values[min(len(values) - 1, round(0.95 * (len(values) - 1)))]
    return {"avg": statistics.mean(values), "p50": statistics.median(values), "p95": p95, "max": values[-1]}


def run(size: int, per_kind: int, out_dir: str, work_dir: str) -> dict:
    corpus_dir = os.path.join(work_dir, "corpus")
    use_work_dir(os.path.join(work_dir, "index"))
    from benchmark.corpus import write_corpus

    manifest = write_corpus(corpus_dir, size)
    index_stats = index_corpus(corpus_dir)

    queries = pick_queries(per_kind)
    rows = []
    # A real HTTP server, not TestClient: TestClient buffers streamed responses,
    # which would hide when the results event actually arrives.
    with serve_api() as base_url:
        warmup = time_query(base_url, "warm up the models")
        for s in queries:
            rows.append({"id": s["id"], "kind": s["kind"], "query": s["query"], **time_query(base_url, s["query"])})

    summary = {"results": _stats([r["results_s"] for r in rows]),
               "answer": _stats([r["answer_s"] for r in rows if r["llm_ok"]])}
    by_kind = {k: {"results": _stats([r["results_s"] for r in rows if r["kind"] == k]),
                   "answer": _stats([r["answer_s"] for r in rows if r["kind"] == k and r["llm_ok"]])} for k in KINDS}
    res = summary["results"]
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "corpus": {"size": manifest["size"], "counts": manifest["counts"]},
        "index_seconds": round(index_stats["seconds"], 1),
        "ingest_docs_per_minute": round(manifest["size"] / index_stats["seconds"] * 60, 1),
        "ollama_model": os.environ.get("OLLAMA_MODEL", "llama3:8b"),
        "warmup": warmup,
        "queries": len(rows),
        "llm_answered": sum(r["llm_ok"] for r in rows),
        "target_seconds": TARGET_SECONDS,
        "pass": bool(res) and res["avg"] <= TARGET_SECONDS,
        "summary": summary,
        "by_kind": by_kind,
        "per_query": rows,
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"latency_{size}.json"), "w") as f:
        json.dump(report, f, indent=1)
    with open(os.path.join(out_dir, f"latency_{size}.md"), "w") as f:
        f.write(to_markdown(report))
    return report


def _s(v) -> str:
    return "n/a" if v is None else f"{v:.2f} s"


def to_markdown(r: dict) -> str:
    res, ans = r["summary"]["results"], r["summary"]["answer"]
    lines = [
        f"# Query latency (US-NF-02, {r['corpus']['size']} documents)",
        "",
        f"Run {r['run_at']}. {r['queries']} queries through `/query/stream` (the endpoint the desktop app uses), "
        f"after a warm-up query. Ollama model `{r['ollama_model']}`; it answered {r['llm_answered']} of {r['queries']}.",
        "",
        f"**US-NF-02 (average time until results appear <= {r['target_seconds']:.0f} s): {'PASS' if r['pass'] else 'FAIL'}**, "
        f"average {_s(res.get('avg'))}.",
        "",
        "| Measure | Average | Median | P95 | Max |",
        "| --- | --- | --- | --- | --- |",
        f"| Results appear | {_s(res.get('avg'))} | {_s(res.get('p50'))} | {_s(res.get('p95'))} | {_s(res.get('max'))} |",
        f"| Full LLM answer | {_s(ans.get('avg'))} | {_s(ans.get('p50'))} | {_s(ans.get('p95'))} | {_s(ans.get('max'))} |",
        "",
        f"Indexing the corpus took {r['index_seconds']} s ({r['ingest_docs_per_minute']} documents per minute, single process).",
        "",
        "## By query kind (average)",
        "",
        "| Kind | Results appear | Full LLM answer |",
        "| --- | --- | --- |",
    ]
    for k, v in r["by_kind"].items():
        lines.append(f"| {k} | {_s(v['results'].get('avg'))} | {_s(v['answer'].get('avg'))} |")
    lines += ["", "## Per query", "", "| Query | Kind | Results | Answer |", "| --- | --- | --- | --- |"]
    for q in r["per_query"]:
        lines.append(f"| {q['id']}: {q['query']} | {q['kind']} | {_s(q['results_s'])} | {_s(q['answer_s']) if q['llm_ok'] else 'LLM unavailable'} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--size", type=int, default=1000)
    ap.add_argument("--per-kind", type=int, default=5)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "results"))
    ap.add_argument("--work-dir", default=None)
    args = ap.parse_args()
    report = run(args.size, args.per_kind, args.out, args.work_dir or tempfile.mkdtemp(prefix="latency-"))
    print(to_markdown(report).split("## By query kind")[0])


if __name__ == "__main__":
    main()
