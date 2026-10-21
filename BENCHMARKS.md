# Benchmarks

`bindings/python/benchmarks/compare.py` times `better_profanity` 0.7.0 and
`better-profanity-rs` with the default word list. Texts of 10, 30, 100, 300 and 700 words are
windows of the [Jigsaw toxic comments](https://huggingface.co/datasets/thesofakillers/jigsaw-toxic-comment-classification-challenge)
laid end to end, 20 per size (seed 1729), so some of them contain swear words. Each figure is
the median over the 20 texts: one call per text for `better_profanity`, and calls repeated for
at least 50 ms per text for `better-profanity-rs`. Every output was checked to be equal to
`better_profanity`'s.

## Apple M1 Pro (6 performance and 2 efficiency cores), macOS 14.5, CPython 3.13.9, better-profanity-rs 0.1.0

| Words | Texts with swear words | `contains_profanity`, better_profanity | better-profanity-rs | Speed-up | `censor`, better_profanity | better-profanity-rs | Speed-up |
|---|---|---|---|---|---|---|---|
| 10 | 0 of 20 | 9.03 ms | 3.91 µs | 2,311× | 9.20 ms | 3.90 µs | 2,357× |
| 30 | 1 of 20 | 34.64 ms | 5.62 µs | 6,161× | 34.08 ms | 5.67 µs | 6,014× |
| 100 | 1 of 20 | 123.77 ms | 11.87 µs | 10,428× | 123.41 ms | 11.78 µs | 10,475× |
| 300 | 16 of 20 | 375.45 ms | 30.15 µs | 12,453× | 375.34 ms | 29.92 µs | 12,544× |
| 700 | 17 of 20 | 888.63 ms | 78.17 µs | 11,368× | 885.14 ms | 76.66 µs | 11,546× |

`contains_profanity` is `text != censor(text)` in both packages, so it costs the same as
`censor`. `better_profanity` compares each word, and each word joined with up to five following
words, with all 916 words of the list; `better-profanity-rs` walks a trie once per word. About
2 µs of each call is fixed: the checks that decide whether Rust may run, among them confirming
that `CENSOR_WORDSET` still holds the same 916 objects (about 1 µs).

Censoring all 97,320 comments of the civil_comments test split (5.0 million words; 10,046 comments
change) takes 1.08 s with `better-profanity-rs`. `better_profanity` takes 121 s for the first 2,000
of them, against 0.023 s (5,221×), which puts the whole split at about 1.6 hours on one core.

`Profanity()` takes 2.1 ms in `better_profanity`. `better-profanity-rs` runs the same constructor
and compiles the word list on the first call; both together take 2.8 ms. The list is compiled again
only when `CENSOR_WORDSET` changes.

Raw results: [`bindings/python/benchmarks/results/m1-pro.json`](bindings/python/benchmarks/results/m1-pro.json).

## Parity on full corpora

`bindings/python/benchmarks/parity.py` censors every text with both packages, in worker
processes, and counts the texts whose output differs. The corpora:

- mutated: 6,000 Wikipedia paragraphs (first 30 words) with one to four dictionary words in
  leetspeak inserted, and 20,000 pairs of words joined by `' '`, `'_'`, `'-'`, `'. '` or
  nothing, each word a dictionary word or phrase in leetspeak or a clean word (seed 1729);
- wikitext: the paragraphs of the wikitext-103 test split;
- civil_comments: the test split of
  [google/civil_comments](https://huggingface.co/datasets/google/civil_comments);
- jigsaw: train.csv of the Jigsaw Toxic Comment Classification Challenge.

"default" is `Profanity()` with `censor(text)`. "custom" loads the default words plus five
phrases with the whitelist `["ass", "hell", "damn", "crap"]` and censors with `"#"`. In every
run the Rust path handled all texts; none fell back to the Python code.

| Corpus | Configuration | Texts | Censored by better_profanity | CPython 3.9.20 | CPython 3.11.5 | CPython 3.13.9 | CPython 3.14.8 |
|---|---|---|---|---|---|---|---|
| mutated | default | 26,000 | 19,876 | 0 differ | 0 differ | 0 differ | 0 differ |
| wikitext | default | 2,183 | 171 | 0 differ | 0 differ | 0 differ | 0 differ |
| civil_comments | default | 97,320 | 10,046 | 0 differ | 0 differ | 0 differ | 0 differ |
| jigsaw | default | 159,571 | 20,439 | 0 differ | 0 differ | 0 differ | 0 differ |
| mutated | custom | 26,000 | 19,823 | 0 differ | 0 differ | 0 differ | 0 differ |
| wikitext | custom | 2,183 | 159 | 0 differ | 0 differ | 0 differ | 0 differ |
| all | | 313,257 | 70,514 | 0 differ | 0 differ | 0 differ | 0 differ |

The "Full parity" GitHub workflow runs the same script on Linux, macOS and Windows.

## Reproducing

```sh
cd bindings/python
uv sync --group dev --group bench
cd benchmarks
uv run python compare.py --output results-local
uv run python parity.py
```

The datasets (90 MB) are downloaded from Hugging Face at pinned revisions on the first run,
checked against their SHA-256 and cached in `~/.cache/better-profanity-rs-bench`
(`BETTER_PROFANITY_BENCH_CACHE` overrides it). `better_profanity` needs about four CPU-hours for
all corpora, so `parity.py --limit N` compares the first N texts of each.
