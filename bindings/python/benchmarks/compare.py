"""Time better_profanity 0.7.0 and better_profanity_rs.

Texts of 10 to 700 words are windows of the Jigsaw toxic comments laid end to end, 20 per size
(seed 1729). The corpus run censors the civil_comments test split. Every timed output is
checked to be equal.
"""

import argparse
import gc
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import time

import better_profanity
from data import load

import better_profanity_rs


def per_call(fn, arg, min_time):
    """Mean seconds per call over at least `min_time` seconds (at least one call)."""
    calls = 0
    start = time.perf_counter()
    while True:
        fn(arg)
        calls += 1
        elapsed = time.perf_counter() - start
        if elapsed >= min_time:
            return elapsed / calls


def cpu_name():
    try:
        return subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
        ).stdout.strip()
    except OSError:
        return platform.processor()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="10,30,100,300,700")
    parser.add_argument("--texts", type=int, default=20)
    parser.add_argument("--corpus-sample", type=int, default=2000)
    parser.add_argument("--output", default="benchmark-results")
    args = parser.parse_args()

    up, rs = better_profanity.Profanity(), better_profanity_rs.Profanity()
    words = " ".join(load("jigsaw")).split()
    rng = random.Random(1729)
    results = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpu": cpu_name(),
        "cpus": os.cpu_count(),
        "better_profanity_rs": better_profanity_rs.__version__,
        "sizes": [],
    }
    for size in map(int, args.sizes.split(",")):
        texts = []
        for _ in range(args.texts):
            i = rng.randrange(len(words) - size)
            texts.append(" ".join(words[i : i + size]))
        row = {"words": size, "censored": 0}
        for name in ("contains_profanity", "censor"):
            up_times, rs_times = [], []
            for text in texts:
                assert getattr(rs, name)(text) == getattr(up, name)(text)
                up_times.append(per_call(getattr(up, name), text, 0))
                rs_times.append(per_call(getattr(rs, name), text, 0.05))
            a, b = statistics.median(up_times), statistics.median(rs_times)
            row[name] = {
                "better_profanity_ms": round(a * 1e3, 2),
                "better_profanity_rs_us": round(b * 1e6, 2),
                "speedup": round(a / b),
            }
        row["censored"] = sum(up.contains_profanity(t) for t in texts)
        results["sizes"].append(row)
        print(json.dumps(row), flush=True)

    corpus = load("civil_comments")
    sample = corpus[: args.corpus_sample]
    start = time.perf_counter()
    expected = [up.censor(t) for t in sample]
    up_sample = time.perf_counter() - start
    start = time.perf_counter()
    got = [rs.censor(t) for t in sample]
    rs_sample = time.perf_counter() - start
    assert got == expected
    start = time.perf_counter()
    censored = sum(rs.censor(t) != t for t in corpus)
    rs_corpus = time.perf_counter() - start
    results["corpus"] = {
        "name": "civil_comments test",
        "texts": len(corpus),
        "words": sum(len(t.split()) for t in corpus),
        "censored": censored,
        "better_profanity_rs_s": round(rs_corpus, 3),
        "sample_texts": len(sample),
        "sample_better_profanity_s": round(up_sample, 2),
        "sample_better_profanity_rs_s": round(rs_sample, 4),
        "sample_speedup": round(up_sample / rs_sample),
    }
    print(json.dumps(results["corpus"]), flush=True)

    def setup(fn):
        times = []
        for _ in range(10):
            gc.collect()
            start = time.perf_counter()
            fn()
            times.append(time.perf_counter() - start)
        return min(times)

    up_init = setup(better_profanity.Profanity)
    rs_init = setup(lambda: better_profanity_rs.Profanity().censor("hello"))
    results["setup_ms"] = {
        "better_profanity_init": round(up_init * 1e3, 2),
        "better_profanity_rs_init_and_first_call": round(rs_init * 1e3, 2),
    }
    print(json.dumps(results["setup_ms"]), flush=True)

    os.makedirs(args.output, exist_ok=True)
    with open(os.path.join(args.output, "results.json"), "w") as f:
        json.dump(results, f, indent=1)


if __name__ == "__main__":
    main()
