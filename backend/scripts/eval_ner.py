"""
Score NER against a small labelled set of personal-data sentences.

Usage (inside the backend image):
    python scripts/eval_ner.py [model ...]

Defaults to the model NERService loads. Prints precision, recall and F1 per
model, overall and per entity type, plus the misses and false positives, so a
model or filtering change can be checked against the F1 >= 0.80 target.
Matching is exact on (normalized name, type).
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.graph import ENTITY_TYPES, normalize_name
from services.ner import DEFAULT_MODEL, NERService

DEFAULT_SET = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ner_eval.jsonl"


def _key(name: str, etype: str):
    return normalize_name(name.removeprefix("the ").removeprefix("The ")), etype


def evaluate(ner: NERService, examples: list) -> dict:
    tp, fp, fn = Counter(), Counter(), Counter()
    misses, extras = [], []
    for ex in examples:
        gold = {_key(n, t) for n, t in ex["entities"]}
        pred = {_key(n, t) for n, t in ner.extract(ex["text"], source=ex.get("source", "text"))}
        for k in pred & gold:
            tp[k[1]] += 1
        for k in pred - gold:
            fp[k[1]] += 1
            extras.append((ex["text"], k))
        for k in gold - pred:
            fn[k[1]] += 1
            misses.append((ex["text"], k))
    return {"tp": tp, "fp": fp, "fn": fn, "misses": misses, "extras": extras}


def _prf(tp: int, fp: int, fn: int):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def main():
    models = sys.argv[1:] or [DEFAULT_MODEL]
    path = Path(os.environ.get("NER_EVAL_SET", DEFAULT_SET))
    examples = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for model in models:
        res = evaluate(NERService(model), examples)
        tp, fp, fn = (sum(res[k].values()) for k in ("tp", "fp", "fn"))
        p, r, f = _prf(tp, fp, fn)
        print(f"\n== {model}: P={p:.2f} R={r:.2f} F1={f:.2f}  (tp={tp} fp={fp} fn={fn}, {len(examples)} examples)")
        for t in ENTITY_TYPES:
            tp_t, fp_t, fn_t = res["tp"][t], res["fp"][t], res["fn"][t]
            print(f"   {t:7} F1={_prf(tp_t, fp_t, fn_t)[2]:.2f}  tp={tp_t} fp={fp_t} fn={fn_t}")
        if os.environ.get("VERBOSE"):
            for text, k in res["misses"]:
                print(f"   miss  {k}  <- {text}")
            for text, k in res["extras"]:
                print(f"   extra {k}  <- {text}")


if __name__ == "__main__":
    main()
