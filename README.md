# better-profanity-rs

[![CI](https://github.com/SyntaxSpirits/better-profanity-rs/actions/workflows/ci.yml/badge.svg)](https://github.com/SyntaxSpirits/better-profanity-rs/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/better-profanity-rs.svg)](https://pypi.org/project/better-profanity-rs/)
[![Crates.io](https://img.shields.io/crates/v/better-profanity.svg)](https://crates.io/crates/better-profanity)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[`better_profanity`](https://pypi.org/project/better-profanity/) with a Rust core: the same
censored text for every input, about 2,300 times faster on a 10-word message and
10,000 to 12,500 times faster on texts of 100 to 700 words
([benchmarks](https://github.com/SyntaxSpirits/better-profanity-rs/blob/main/BENCHMARKS.md)).

`better_profanity` is downloaded about two million times a month, although its last release, 0.7.0,
dates from November 2020. It is slow: `contains_profanity` takes 9 ms for a 10-word message and
0.9 s for a 700-word article on an M1 Pro with CPython 3.13. The word list is a Python list of 916
objects, and each word of the text, alone and joined with the words after it, is compared with every
one of them by a method that tries the leetspeak variants letter by letter. `better-profanity-rs`
turns the word list into a trie whose edges are sets of characters (`a`, `@`, `*` and `4` for an
`a`) and runs the original scan, step for step, in Rust. Words in leetspeak, phrases split by
separators (`f.u.c.k`, `H4nd j0b`), whitelists, custom word lists and the quirks of the original
give the same output.

The Python package is `better-profanity-rs`; the Rust crate is `better-profanity`. This is an
independent project, not affiliated with the author of `better_profanity`.

## Python

```sh
pip install better-profanity-rs
```

Change the import and keep the rest of your code:

```python
from better_profanity_rs import profanity  # was: from better_profanity import profanity

profanity.censor("That wh0re gave m3 a very good H4nd j0b, dude.")
# 'That **** gave m3 a very good ****, dude.'
profanity.contains_profanity("he is a m0th3rf*cker")
# True
profanity.load_censor_words(["happy", "jolly"], whitelist_words=["jolly"])
profanity.censor("Happy and jolly days", "-")
# '---- and jolly days'
```

`Profanity`, `load_censor_words`, `load_censor_words_from_file`, `add_censor_words`, `censor`
and `contains_profanity` take the same arguments as in `better_profanity` 0.7.0 and return the
same results or raise the same exceptions. The attributes `CENSOR_WORDSET`, `CHARS_MAPPING`,
`MAX_NUMBER_COMBINATIONS` and `ALLOWED_CHARACTERS` can be read and changed as before, and the
modules `better_profanity`, `constants`, `utils` and `varying_string` are those of 0.7.0.

### Code you do not control

When a library imports `better_profanity` itself, call `install()` before importing it:

```python
import better_profanity_rs

better_profanity_rs.install()  # `import better_profanity` now returns better_profanity_rs

import my_web_app
```

`install()` covers `better_profanity` and its modules `better_profanity`, `constants`, `utils`
and `varying_string`. Modules that imported `better_profanity` before the call keep the
original.

## Rust

```toml
[dependencies]
better-profanity = "0.1"
```

```rust
use better_profanity::Profanity;

let profanity = Profanity::new();
assert_eq!(
    profanity.censor("That wh0re gave m3 a very good H@nD j0b.", "*"),
    "That **** gave m3 a very good ****."
);

let mut custom = Profanity::with_words(["happy", "jolly"]);
custom.add_censor_words(["merry christmas"]);
assert!(custom.contains_profanity("Merry Christmas!"));
```

`Profanity` follows the Python class; `hide_swear_words`, `WordSet` and `CharSet` expose the
scan for other word sets, separator sets and lowercasing rules. The crate lowercases with Rust's
Unicode tables, which can differ from those of a given Python for characters added to Unicode
recently; the Python package always uses the running interpreter's `str.lower()`.

## Compatibility

The tests compare `better-profanity-rs` with `better_profanity` 0.7.0 and fail on any
difference in output or exception: the original's own test suite, hand-picked cases,
dictionary words in leetspeak inside texts and joined by separators, custom word lists and
whitelists, invalid arguments, every kind of attribute change listed below, subclasses,
pickling, threads and property-based tests, on CPython 3.9 to 3.14. A separate script compares
285,074 texts, among them the civil_comments test split and the Jigsaw toxic comments (50,532
of the texts are censored), and 28,183 of them again with a custom word list and whitelist, on
CPython 3.9, 3.11, 3.13 and 3.14: no output differs (see [BENCHMARKS.md](BENCHMARKS.md)).

This includes the original's quirks. For example, `add_censor_words` does not raise
`MAX_NUMBER_COMBINATIONS`, and when it is 1, only every other word is joined to the next one.
After `Profanity(["happy", "jolly"]).add_censor_words(["merry christmas"])`, both packages
censor "m3rry christmas" and "a b m3rry christmas" but not "a m3rry christmas".

`better_profanity`'s own code, bundled in the package, runs whenever the Rust core could
behave differently, so the output stays the same and only the speed-up is lost:

- the text or `censor_char` is not an exact `str` (a `str` subclass, for example), or contains
  lone surrogates;
- `CENSOR_WORDSET` is not an exact list or tuple of `VaryingString` objects and strings, or a
  `CHARS_MAPPING` value used by a word has a variant that is not exactly one character
  (`better_profanity` also accepts longer and empty variants);
- `MAX_NUMBER_COMBINATIONS` is not an `int` or is above 50;
- `ALLOWED_CHARACTERS` was replaced by another set, or holds something other than strings;
- a subclass or a patch replaces `_get_next_words`, `_update_next_words_indices`,
  `_get_start_index_of_next_word`, `_get_next_word_and_end_index`,
  `get_replacement_for_swear_word`, `any_next_words_form_swear_word` or
  `VaryingString.__eq__`, or turns one of the attributes into a property.

Changes in place are seen. `CENSOR_WORDSET` is compiled again when its items change: each call
checks that the list still holds the same objects, which takes about 1 µs for the default
list. `ALLOWED_CHARACTERS` is a `set` subclass that notes its changes. Lowercasing uses the
interpreter's `str.lower()`, so, as with `better_profanity`, results follow the Unicode version
of the Python running them.

Known differences:

- The private attributes of a `VaryingString` (`_char_combos`, `_min_len`, `_max_len`) are
  read when the word list is compiled; changing them later on an object already in
  `CENSOR_WORDSET` is not seen.
- `ALLOWED_CHARACTERS` is a `set` subclass; changes made through `set` itself, as in
  `set.add(ALLOWED_CHARACTERS, "-")`, are not seen.
- `__version__` and `name` are those of `better_profanity_rs`.

## Development

```sh
cargo test -p better-profanity
cd bindings/python
uv sync --group dev
uv run pytest
cd benchmarks && uv run --group bench python parity.py   # all corpora
```

## License

MIT, the same licence as `better_profanity`, whose code, word list and character list this
project includes. See [NOTICE](NOTICE).
