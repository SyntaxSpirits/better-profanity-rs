"""Texts for the parity runs and benchmarks, downloaded from Hugging Face at pinned revisions.

- civil_comments: the test split of google/civil_comments (97,320 comments from news sites);
- jigsaw: train.csv of the Jigsaw Toxic Comment Classification Challenge (159,571 Wikipedia talk
  page comments, about one in ten toxic);
- wikitext: the test split of wikitext-103, one Wikipedia paragraph per line.
"""

import csv
import hashlib
import os
import urllib.request

import pyarrow.parquet as pq

HF = "https://huggingface.co/datasets"
SOURCES = {
    "civil_comments": (
        f"{HF}/google/civil_comments/resolve/f2970eb3a55777454c94069077cc8d9b5866312d/"
        "data/test-00000-of-00001.parquet",
        "410f803ff161e7c4ba005db7de5b444cac413f4861bf056b0fd69d670d75aa08",
    ),
    "jigsaw": (
        f"{HF}/thesofakillers/jigsaw-toxic-comment-classification-challenge/resolve/"
        "50f3c926ec8c07b440cb17b55d8cd80e8484497e/train.csv",
        "bd4084611bd27c939ba98e5e63bc3e5a2c1a4e99477dcba46c829e4c986c429d",
    ),
    "wikitext": (
        f"{HF}/Salesforce/wikitext/resolve/b08601e04326c79dfdd32d625aee71d232d685c3/"
        "wikitext-103-raw-v1/test-00000-of-00001.parquet",
        "5f1bea067869d04849c0f975a2b29c4ff47d867f484f5010ea5e861eab246d91",
    ),
}
CACHE = os.environ.get(
    "BETTER_PROFANITY_BENCH_CACHE", os.path.expanduser("~/.cache/better-profanity-rs-bench")
)


def _download(name):
    url, sha256 = SOURCES[name]
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{name}{os.path.splitext(url)[1]}")
    if not os.path.exists(path):
        with urllib.request.urlopen(url) as r, open(path + ".part", "wb") as f:
            f.write(r.read())
        os.replace(path + ".part", path)
    with open(path, "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != sha256:
            raise ValueError(f"{path} does not match its SHA-256; delete it to download again")
    return path


def load(name):
    path = _download(name)
    if name == "civil_comments":
        return pq.read_table(path, columns=["text"]).column("text").to_pylist()
    if name == "wikitext":
        lines = pq.read_table(path, columns=["text"]).column("text").to_pylist()
        return [line.strip() for line in lines if line.strip() and not line.startswith(" =")]
    csv.field_size_limit(2**31 - 1)
    with open(path, encoding="utf-8", newline="") as f:
        return [row["comment_text"] for row in csv.DictReader(f)]
