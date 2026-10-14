# Retrieval and latency benchmarks (sprints 10A and 10B)

Both benchmarks run the production pipeline (the real `ingest_task` and
`QueryService`) inside the backend image, against a throwaway index in a temp
directory. They never touch `data/` or the running stack.

Run from the repo root after `docker compose build`:

```bash
# 10A: NDCG@10, P@5 and MRR for BM25, semantic, and semantic + knowledge graph
docker run --rm -v "$PWD":/repo -w /repo/backend -e PYTHONPATH=/repo/backend \
  jas-project-api python -m benchmark.retrieval --size 500

# 10B: US-NF-02 query latency on 1,000 documents (needs Ollama running on the host)
docker run --rm -v "$PWD":/repo -w /repo/backend -e PYTHONPATH=/repo/backend \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  jas-project-api python -m benchmark.latency --size 1000 --per-kind 5
```

Each writes a JSON and a Markdown report to `results/`.

## Test set

`scenarios.py` holds the 50 queries (14 single keyword, 14 multi-word phrase,
22 natural-language questions) over a persona's personal data. `corpus.py`
turns them into real files (notes, plain-text email exports, PDFs and a Chrome
`History` database) that go through the normal parsers.

Every query has four relevant documents, graded as in workbook 7.2:

| Grade | Document | Example for "Which restaurant did Tara recommend?" |
| --- | --- | --- |
| 2 | The answer, written by hand | Note: "Tara recommended Noosh Noshery on Castro St…" |
| 1 | A related document, written by hand | Browser visit: "Noosh Noshery - Menu - Yelp" |
| 1 | Two generated mentions of the topic | A to-do note and a reminder email about the Noosh Noshery dinner |

The other documents are distractors on similar everyday themes (other
restaurants, appointments, bills, web pages), generated from a fixed seed.
Each scenario lists guard words (Tara, Noosh); a distractor containing any
guard word is regenerated, so distractors are never relevant to a query.

Because each query has four relevant documents, the best possible P@5 is 0.80.

## Limits

- Relevance is assigned by construction, not by two independent annotators as
  workbook 7.2 describes. `qrels.json` (written next to the corpus) can be
  exported for a human pass on a sample to measure agreement.
- The corpus is synthetic. It is designed to be hard in realistic ways
  (paraphrased questions, same-genre distractors), but real personal data is
  messier and longer.
- Email is ingested as plain text; `.eml` parsing (US-F-05) isn't built.
- Latency depends heavily on the machine: the local LLM shares memory with
  Docker and everything else running.
