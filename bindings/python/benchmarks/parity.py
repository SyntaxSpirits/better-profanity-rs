"""Compare better_profanity_rs with better_profanity 0.7.0 on full corpora.

Every text is censored by both packages, in worker processes, and the outputs must be equal.
contains_profanity is `text != censor(text)` in both, so it agrees whenever censor does.

Configurations:
- default: Profanity() and censor(text);
- custom: the default words plus a few phrases, a whitelist and censor_char "#".
"""

import argparse
import json
import os
import random
import sys
import time
from multiprocessing import Pool

from data import load

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))

from inputs import WORDS, mutated_inputs  # noqa: E402

EXTRA = ["kill yourself", "go to hell", "white power", "sieg heil", "supremacia ariana"]
WHITELIST = ["ass", "hell", "damn", "crap"]
CHUNK = 100

_state = {}


def _make(module, config):
    p = module.Profanity()
    if config == "custom":
        p.load_censor_words(WORDS + EXTRA, whitelist_words=list(WHITELIST))
    return p


def _init(config):
    import better_profanity

    import better_profanity_rs
    from better_profanity_rs import _fast

    original = _fast._fast_result
    python_path = []

    def counting(self, text, censor_char):
        result = original(self, text, censor_char)
        if result is None:
            python_path.append(1)
        return result

    _fast._fast_result = counting
    _state.update(
        upstream=_make(better_profanity, config),
        port=_make(better_profanity_rs, config),
        censor_char="#" if config == "custom" else "*",
        python_path=python_path,
    )


def _check(texts):
    a, b, censor_char = _state["upstream"], _state["port"], _state["censor_char"]
    censored, mismatches = 0, []
    before = len(_state["python_path"])
    for text in texts:
        expected = a.censor(text, censor_char)
        censored += expected != text
        if b.censor(text, censor_char) != expected:
            mismatches.append(text)
    return len(texts), censored, mismatches, len(_state["python_path"]) - before


def corpora(names):
    out = {}
    for name in names:
        if name == "mutated":
            rng = random.Random(1729)
            base = [" ".join(t.split()[:30]) for t in load("wikitext")]
            out[name] = mutated_inputs(rng, base, 6000, 20000)
        else:
            out[name] = load(name)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpora", default="mutated,wikitext,civil_comments,jigsaw")
    parser.add_argument("--custom", default="mutated,wikitext", help="corpora also run with custom")
    parser.add_argument("--limit", type=int, default=None, help="texts per corpus")
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    import better_profanity_rs

    report = {
        "python": sys.version.split()[0],
        "better_profanity_rs": better_profanity_rs.__version__,
        "results": [],
    }
    start = time.perf_counter()
    texts = corpora(args.corpora.split(","))
    runs = [(name, "default") for name in texts]
    runs += [(name, "custom") for name in args.custom.split(",") if name in texts]
    for name, config in runs:
        items = texts[name][: args.limit]
        chunks = [items[i : i + CHUNK] for i in range(0, len(items), CHUNK)]
        total = censored = python_path = 0
        mismatches = []
        t0 = time.perf_counter()
        with Pool(args.workers, initializer=_init, initargs=(config,)) as pool:
            for n, c, m, p in pool.imap_unordered(_check, chunks):
                total += n
                censored += c
                mismatches += m
                python_path += p
        row = {
            "corpus": name,
            "config": config,
            "texts": total,
            "censored_by_better_profanity": censored,
            "mismatches": len(mismatches),
            "python_path_calls": python_path,
            "seconds": round(time.perf_counter() - t0, 1),
            "examples": [t[:300] for t in mismatches[:5]],
        }
        report["results"].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    report["seconds"] = round(time.perf_counter() - start, 1)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1, ensure_ascii=False)
    sys.exit(1 if any(r["mismatches"] for r in report["results"]) else 0)


if __name__ == "__main__":
    main()
