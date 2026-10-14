import math
import re
from collections import Counter
from urllib.parse import urlsplit

import pytest

from benchmark.corpus import build_documents, doc_id, has_guard_word, write_corpus
from benchmark.metrics import mean_scores, ndcg_at_k, precision_at_k, reciprocal_rank, score_query
from benchmark.retrieval import _unique, tokenize
from benchmark.scenarios import SCENARIOS

QRELS = {"answer": 2, "rel1": 1, "rel2": 1}


# ------------------------------------------------------------------ metrics

def test_ndcg_perfect_ranking_is_one():
    assert ndcg_at_k(["answer", "rel1", "rel2", "x"], QRELS) == pytest.approx(1.0)


def test_ndcg_matches_hand_computation():
    # gains 2^rel - 1: answer=3, rel=1; discounts log2(rank + 1)
    ranked = ["x", "answer", "rel1"]
    dcg = 3 / math.log2(3) + 1 / math.log2(4)
    idcg = 3 / math.log2(2) + 1 / math.log2(3) + 1 / math.log2(4)
    assert ndcg_at_k(ranked, QRELS) == pytest.approx(dcg / idcg)


def test_ndcg_ignores_results_past_k_and_handles_no_relevant():
    assert ndcg_at_k(["x"] * 10 + ["answer"], QRELS, k=10) == 0.0
    assert ndcg_at_k(["a"], {}) == 0.0


def test_precision_counts_grade_one_and_two_and_short_lists_as_misses():
    assert precision_at_k(["answer", "x", "rel1", "y", "rel2"], QRELS, 5) == pytest.approx(0.6)
    assert precision_at_k(["answer"], QRELS, 5) == pytest.approx(0.2)


def test_reciprocal_rank_binary_and_answer_only():
    ranked = ["x", "rel1", "answer"]
    assert reciprocal_rank(ranked, QRELS) == pytest.approx(1 / 2)
    assert reciprocal_rank(ranked, QRELS, min_grade=2) == pytest.approx(1 / 3)
    assert reciprocal_rank(["x"], QRELS) == 0.0


def test_score_query_and_mean():
    a = score_query(["answer", "rel1", "rel2"], QRELS)
    b = score_query(["x"], QRELS)
    assert a["mrr"] == 1.0 and b["mrr"] == 0.0
    assert mean_scores([a, b])["mrr"] == pytest.approx(0.5)
    # rows carry the ranked list too; only numeric metrics are averaged
    assert set(mean_scores([{**a, "top10": ["answer"]}, {**b, "top10": []}])) == set(a)


# ------------------------------------------------------------------ ranking helpers

def test_unique_keeps_first_occurrence_order_and_limit():
    assert _unique(["a", "b", "a", "c", "b", "d"], limit=3) == ["a", "b", "c"]


def test_tokenize_lowercases_and_drops_stopwords():
    assert tokenize("When is MY Teeth-Cleaning?") == ["teeth", "cleaning"]


# ------------------------------------------------------------------ scenarios and corpus

def test_scenarios_are_well_formed():
    assert len(SCENARIOS) == 50
    assert len({s["id"] for s in SCENARIOS}) == 50
    assert set(Counter(s["kind"] for s in SCENARIOS)) == {"keyword", "phrase", "question"}
    for s in SCENARIOS:
        assert s["guards"] and s["topic"]
        assert s["answer"]["type"] in ("note", "email", "pdf", "history")


@pytest.fixture(scope="module")
def corpus():
    return build_documents(500)


def test_corpus_has_requested_size_mix_and_unique_ids(corpus):
    docs, _ = corpus
    assert len(docs) == 500
    assert len({doc_id(d) for d in docs}) == 500
    assert Counter(d["type"] for d in docs) == {"note": 150, "history": 150, "email": 100, "pdf": 100}


def test_every_query_has_one_answer_and_three_related(corpus):
    docs, qrels = corpus
    ids = {doc_id(d) for d in docs}
    assert set(qrels) == {s["id"] for s in SCENARIOS}
    for grades in qrels.values():
        assert sorted(grades.values()) == [1, 1, 1, 2]
        assert set(grades) <= ids


def test_no_distractor_contains_a_guard_word(corpus):
    docs, qrels = corpus
    labelled = {d for grades in qrels.values() for d in grades}
    for d in docs:
        if doc_id(d) not in labelled:
            text = " ".join(str(d.get(k, "")) for k in ("text", "subject", "title", "url"))
            assert not has_guard_word(text), text


def test_each_answer_mentions_its_own_guard_word():
    # Guards must actually describe the scenario, or the distractor filter does nothing.
    for s in SCENARIOS:
        text = " ".join(str(s["answer"].get(k, "")) for k in ("text", "subject", "title", "url"))
        text += " " + " ".join(str(s["related"].get(k, "")) for k in ("text", "subject", "title", "url"))
        assert has_guard_word(text), s["id"]


def test_history_pages_never_collapse_in_the_parser(corpus):
    docs, _ = corpus
    keys = Counter((urlsplit(d["url"]).netloc, " ".join(d["title"].lower().split()))
                   for d in docs if d["type"] == "history")
    assert max(keys.values()) == 1


def test_generation_is_deterministic():
    a, _ = build_documents(500)
    b, _ = build_documents(500)
    assert [doc_id(d) for d in a] == [doc_id(d) for d in b]


def test_size_below_labelled_set_is_rejected():
    with pytest.raises(ValueError):
        build_documents(100)


def test_write_corpus_creates_parseable_files(tmp_path):
    from parsers.browser_history import parse_browser_history
    from parsers.pdf import parse_pdf

    manifest = write_corpus(str(tmp_path), 500)
    assert manifest["counts"]["pdf"] == len(list((tmp_path / "docs").glob("*.pdf")))
    visits = parse_browser_history(str(tmp_path / "browser" / "History"))
    assert len(visits) == manifest["counts"]["history"]
    first_pdf = sorted((tmp_path / "docs").glob("*.pdf"))[0]
    assert parse_pdf(str(first_pdf))[0].content.strip()
    email = (tmp_path / "emails" / "consulate_appointment.txt").read_text()
    assert re.match(r"From: .+\nTo: .+\nDate: .+\nSubject: Passport renewal", email)
