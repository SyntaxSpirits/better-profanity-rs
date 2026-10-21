"""Comparison with better_profanity 0.7.0: the same output, or the same exception, for every
input, word list and change to a Profanity object or to the modules."""

import ast
import compileall
import copy
import gc
import inspect
import os
import pathlib
import pickle
import random
import shutil
import subprocess
import sys
import textwrap
import threading
import weakref

import better_profanity as up
import better_profanity.better_profanity as up_module
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from inputs import CLEAN, SEPARATORS, WORDS, mutate, mutated_inputs, phrase

import better_profanity_rs as rs
import better_profanity_rs.better_profanity as rs_module
from better_profanity_rs import _fast, _original

CENSOR_CHARS = ["*", "-", "", "##", "é", "\U0001f600", 5, None]

EXAMPLES = [
    "",
    " ",
    "a",
    "ab",
    " a",
    "a ",
    "  ",
    "\n",
    "fuck",
    "fuck ",
    " fuck",
    "fuck.",
    "f",
    "sh1t",
    "Sh!t",
    "$hit",
    "5h17",
    "f u c k",
    "f.u.c.k",
    "f-u-c-k",
    "f_u_c_k",
    "f.u.c.k.",
    ".f.u.c.k",
    "f*ck",
    "fu*k",
    "****",
    "*****",
    "aaaa",
    "@@@@",
    "2 girls 1 cup",
    "2  girls 1 cup",
    "2 girls 1 cupcake",
    "two girls 1 cup",
    "Those 2 girls 1 cup. You gotta check. ",
    "blow job",
    "blowjob",
    "blow-job",
    "blow_job",
    "blow. job",
    "blow\njob",
    "blow . job",
    "hand job",
    "H4nd j0b",
    "h@nd   j0b",
    "hand",
    "job",
    "ass",
    "a$$",
    "@$$",
    "class",
    "assassin",
    "Scunthorpe",
    "cocktail",
    "fuck fuck fuck",
    "fuckfuck",
    "fuck-ass",
    "ass-fucker",
    "dog-fucker",
    "doggie style",
    "doggie-style",
    "doggy  style",
    "bull shit",
    "bullshit",
    "bull-shit",
    "bull_shit",
    "bull.shit",
    "bull. shit",
    "blue waffle",
    "brown showers",
    "...pen1s...hello_cat_vagina,,,,qew",
    "he is a m0th3rf*cker",
    "That wh0re gave m3 a very good H4nd j0b, dude. You gotta check.",
    "  wh0re gave m3 a very good H@nD j0b.",
    "\t fuck\n",
    "Đây là 1 câu nói bậy.",
    "fück",
    "FUCK",
    "FuCk",
    "fucK",
    "fuc\u212a",
    "ΣΑΣ",
    "σας",
    "İ",
    "fuckİ",
    "İfuck",
    "i\u0307",
    "fuck\u00a0you",
    "fuck\u2028you",
    "fuck\U0001f642you",
    "\U0001f642",
    "\U0001f642\U0001f642fuck",
    "fúck",
    "wh0re",
    "a" * 100,
    "fuck " * 40,
    '"fuck"',
    "'fuck'",
    "fuck's",
    'shit"',
    "@fuck@",
    "$fuck$",
    "x fuck",
    "fuck x",
    "x x fuck x x",
    "fuck a",
    "a fuck",
    "bitch a",
    "a b c d e f g h",
    "1 2 3",
    "f\x00uck",
    "fuck\x1cyou",
    "\ud800",
    "fuck\ud800",
    "\ud800fuck",
    "fu\udfffck",
    "nigg3r",
    "n1gga",
    "c0ck sucker",
    "cocksucker",
    "mother fucker",
    "motherfucker",
    "a\u2c2fx",
    "a\u2c5fx",
    "\u2c2f",
    "\ua7c0\ua7c1",
    "\U00010570",
    "\u212b\u2126",
]


def outcome(fn, *args, **kwargs):
    try:
        return "ok", fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        return "raise", type(e), str(e)


def state(p):
    return (
        sorted(repr(getattr(w, "_original", w)) for w in p.CENSOR_WORDSET),
        p.MAX_NUMBER_COMBINATIONS,
    )


def assert_same(a, b, text, censor_char="*"):
    assert outcome(b.censor, text, censor_char) == outcome(a.censor, text, censor_char), (
        text,
        censor_char,
    )
    assert outcome(b.contains_profanity, text) == outcome(a.contains_profanity, text), text


def pair(*args, **kwargs):
    a = outcome(up.Profanity, *args, **kwargs)
    b = outcome(rs.Profanity, *args, **kwargs)
    if a[0] == "raise":
        assert b == a
        return None, None
    return a[1], b[1]


@pytest.fixture(scope="module")
def default_pair():
    return up.Profanity(), rs.Profanity()


def test_examples(default_pair, fallbacks):
    a, b = default_pair
    for text in EXAMPLES:
        for censor_char in CENSOR_CHARS:
            assert_same(a, b, text, censor_char)
    surrogates = {t for t in EXAMPLES if any("\ud800" <= c <= "\udfff" for c in t)}
    assert set(fallbacks) == surrogates


def test_empty_and_unchanged_text_is_returned_as_is(default_pair):
    _, b = default_pair
    for text in ["", " ", "a", " a", "...", "\U0001f642"]:
        assert b.censor(text) is text


def test_mutated_inputs(default_pair, fallbacks):
    a, b = default_pair
    rng = random.Random(1729)
    base = [" ".join(CLEAN[i : i + 14]) for i in range(0, len(CLEAN) - 14, 3)]
    censored = 0
    for text in mutated_inputs(rng, base, 300, 1000):
        expected = a.censor(text)
        assert b.censor(text) == expected, text
        censored += expected != text
    assert censored > 600
    assert not fallbacks


def test_upstream_module_objects():
    for text in EXAMPLES[:60]:
        up.profanity.load_censor_words()
        rs.profanity.load_censor_words()
        assert_same(up.profanity, rs.profanity, text)


WORD_LISTS = [
    ["happy", "jolly", "merry"],
    ["хайль"],
    ["противоя́дия", "употребле́ния"],
    ["gâu", "câu", "bậy"],
    ["İstanbul", "istanbul"],
    ["ΣΑΣ", "σας", "ας"],
    ["a b c d e f"],
    ["x-y-z", "x y", "x"],
    ["fu ck", "f"],
    [" lead", "trail ", " both "],
    ["", "a"],
    ["A", "B", "ab"],
    ["ǅ", "ß", "SS", "ﬀ", "é", "É"],
    ["*", "****", "@", "**"],
    ["f!ck", "s#it", "a.b.c", "1 2 3"],
    ["a\u2c5fx", "\u2c5f", "k", "\u212bm"],
    [" ".join("abcdefghij")],
    [" ".join("abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz")],
    ["blow job", "hand job", "job"],
    ["fuck"] * 3,
    ("tuple", "words"),
    {"set", "words"},
    "string",
]


def texts_for(words, rng, count=80):
    words = [w for w in words if isinstance(w, str)] or ["x"]
    out = list(EXAMPLES[::3])
    for _ in range(count):
        n = rng.randint(1, 5)
        parts = [
            phrase(rng, rng.choice(words), SEPARATORS + [",", "  ", "\u00a0"]) for _ in range(n)
        ]
        seps = [rng.choice(SEPARATORS + ["... ", "\n"]) for _ in range(n)]
        out.append("".join(p + s for p, s in zip(parts, seps)))
    return out


@pytest.mark.parametrize("words", WORD_LISTS, ids=range(len(WORD_LISTS)))
def test_word_lists(words, fallbacks):
    rng = random.Random(repr(words))
    # Above 50 following words the Python path runs; it is slow, so fewer texts.
    python_path = any(sum(not c.isalnum() for c in w) > 50 for w in words)
    for whitelist in [None, ["fuck", "a"], list(words)[:1] if not isinstance(words, str) else None]:
        a, b = pair(words) if whitelist is None else pair()
        if a is None:
            continue
        if whitelist is not None:
            for p in (a, b):
                p.load_censor_words(words, whitelist_words=list(whitelist))
        assert state(b) == state(a)
        for text in texts_for(words, rng, 10 if python_path else 80):
            assert_same(a, b, text)
            assert_same(a, b, text, "-")
    if not python_path:
        assert all(any("\ud800" <= c <= "\udfff" for c in t) for t in fallbacks)


def test_whitelist_and_load_errors(tmp_path):
    files = {
        "crlf": "fuck\r\nhappy \r\n\r\n  \n Merry\n",
        "bom": "\ufeffhappy\njolly\n",
        "cr": "a\rb\r\rc",
        "empty": "",
        "nel": "happy\u0085\njolly\u2028\n",
    }
    for name, content in files.items():
        with open(tmp_path / name, "w", encoding="utf-8", newline="") as f:
            f.write(content)
    (tmp_path / "latin1").write_bytes("caf\xe9\n".encode("latin-1"))

    calls = [
        ("load_censor_words", (), {}),
        ("load_censor_words", ([],), {}),
        ("load_censor_words", (None,), {"whitelist_words": ["Fuck", "SHIT"]}),
        ("load_censor_words", (), {"whitelist_words": ("fuck",)}),
        ("load_censor_words", (), {"whitelist_words": {"fuck"}}),
        ("load_censor_words", (), {"whitelist_words": ()}),
        ("load_censor_words", (), {"whitelist_words": "fuck"}),
        ("load_censor_words", (), {"whitelist_words": ["fuck", 1]}),
        ("load_censor_words", (), {"whitelist_words": [1]}),
        ("load_censor_words", (), {"whitelist_words": []}),
        ("load_censor_words", (), {"other": 1}),
        ("load_censor_words", ("abc",), {}),
        ("load_censor_words", ([1, "a", "b c d"],), {}),
        ("load_censor_words", ([None],), {}),
        ("load_censor_words", (iter(["happy", "x y z w"]),), {}),
        ("load_censor_words", ({"key": 1},), {}),
        ("load_censor_words", (5,), {}),
        ("add_censor_words", (["New", "x y"],), {}),
        ("add_censor_words", (("a b c",),), {}),
        ("add_censor_words", ({"set"},), {}),
        ("add_censor_words", ("str",), {}),
        ("add_censor_words", ([1],), {}),
        ("add_censor_words", ([b"bytes"],), {}),
        ("load_censor_words_from_file", ("missing.txt",), {}),
    ]
    calls += [
        ("load_censor_words_from_file", (str(tmp_path / name),), {}) for name in [*files, "latin1"]
    ]
    calls.append(
        ("load_censor_words_from_file", (str(tmp_path / "crlf"),), {"whitelist_words": ["MERRY"]})
    )
    for method, args, kwargs in calls:
        a, b = up.Profanity(["seed"]), rs.Profanity(["seed"])
        expected = outcome(getattr(a, method), *copy.deepcopy(args), **copy.deepcopy(kwargs))
        got = outcome(getattr(b, method), *copy.deepcopy(args), **copy.deepcopy(kwargs))
        assert got == expected, (method, args, kwargs)
        assert state(b) == state(a)
        for text in ["fuck", "happy days", "Merry x y z w", "a b c d", "seed", "New x y", "café"]:
            assert_same(a, b, text)

    for words in [123, False, 1.5, None, [], "missing.txt", str(tmp_path / "crlf"), {"a": 1}]:
        a, b = pair(words)
        if a is not None:
            assert state(b) == state(a)
            assert_same(a, b, "fuck happy")


def test_whitelist_lowercases_callers_list():
    whitelist_a, whitelist_b = ["FUCK", "Shit"], ["FUCK", "Shit"]
    up.Profanity().load_censor_words(whitelist_words=whitelist_a)
    rs.Profanity().load_censor_words(whitelist_words=whitelist_b)
    assert whitelist_b == whitelist_a == ["fuck", "shit"]


def test_non_str_inputs(default_pair):
    a, b = default_pair

    class Text(str):
        def __ne__(self, other):
            return True

    class Char(str):
        def __mul__(self, n):
            return "!"

    for text in [5, None, b"fuck", ["fuck"], 1.5, Text("fuck"), Text("hello"), object]:
        for censor_char in ["*", Char("-"), 7]:
            assert_same(a, b, text, censor_char)


SCENARIOS = {}


def scenario(fast):
    def register(fn):
        SCENARIOS[fn.__name__] = (fn, fast)
        return fn

    return register


@scenario(fast=True)
def append_str(p, module):
    p.CENSOR_WORDSET.append("hello")


@scenario(fast=True)
def append_upper_str(p, module):
    p.CENSOR_WORDSET.append("Hello")


@scenario(fast=True)
def append_varying_string(p, module):
    p.CENSOR_WORDSET.append(module.VaryingString("he1lo", char_map=p.CHARS_MAPPING))


@scenario(fast=True)
def replace_item(p, module):
    p.CENSOR_WORDSET[0] = module.VaryingString("fuck", char_map={})


@scenario(fast=True)
def remove_items(p, module):
    del p.CENSOR_WORDSET[::2]


@scenario(fast=True)
def clear_wordset(p, module):
    p.CENSOR_WORDSET.clear()


@scenario(fast=True)
def assign_list(p, module):
    p.CENSOR_WORDSET = ["fuck", "hello world", module.VaryingString("h3llo", char_map={})]


@scenario(fast=True)
def assign_tuple(p, module):
    p.CENSOR_WORDSET = tuple(p.CENSOR_WORDSET)


@scenario(fast=True)
def add_after_load(p, module):
    p.load_censor_words(["one"])
    p.add_censor_words(["two words", "THREE"])


@scenario(fast=False)
def object_in_wordset(p, module):
    p.CENSOR_WORDSET.append(1)


@scenario(fast=False)
def subclass_in_wordset(p, module):
    class Word(module.VaryingString):
        pass

    p.CENSOR_WORDSET.append(Word("hello", char_map=p.CHARS_MAPPING))


@scenario(fast=False)
def list_subclass_wordset(p, module):
    class Words(list):
        pass

    p.CENSOR_WORDSET = Words(p.CENSOR_WORDSET)


@scenario(fast=False)
def multi_char_mapping(p, module):
    p.CHARS_MAPPING["u"] = ("u", "|_|", "v")
    p.load_censor_words(["fuck", "hello"])


@scenario(fast=False)
def empty_variant(p, module):
    p.CHARS_MAPPING["e"] = ("e", "")
    p.load_censor_words(["hello", "bee"])


@scenario(fast=False)
def shared_variant_object(p, module):
    variant = "".join(["a", "@"])
    p.CENSOR_WORDSET.append(module.VaryingString("a", char_map={"a": variant}))
    p.CENSOR_WORDSET.append(module.VaryingString("x", char_map={"x": (variant,)}))


@scenario(fast=True)
def string_mapping(p, module):
    p.CHARS_MAPPING["o"] = "o0Q"
    p.CHARS_MAPPING["x"] = ("x", "%")
    p.load_censor_words(["box", "hello"])


@scenario(fast=True)
def no_mapping(p, module):
    p.CHARS_MAPPING = {}
    p.load_censor_words()


@scenario(fast=True)
def mapping_without_letter(p, module):
    p.CHARS_MAPPING["a"] = ("@", "4")
    p.load_censor_words(["ass", "bad"])


for _value, _fast_ok in [
    (0, True),
    (2, True),
    (3, True),
    (10, True),
    (50, True),
    (51, True),
    (300, True),
    (990, False),
    (-1, True),
    (True, False),
    (2.5, False),
    (10**20, False),
]:

    def _set_max(p, module, value=_value):
        p.MAX_NUMBER_COMBINATIONS = value

    SCENARIOS[f"max_{_value!r}"] = (_set_max, _fast_ok)


@scenario(fast=False)
def plain_allowed_set(p, module):
    p.ALLOWED_CHARACTERS = set(p.ALLOWED_CHARACTERS) | {"-"}


@scenario(fast=False)
def instance_helper(p, module):
    p._get_next_words = lambda text, start, num=1: type(p)._get_next_words(p, text, start, num + 1)


@scenario(fast=False)
def patched_replacement(p, module):
    module.get_replacement_for_swear_word = lambda c: c * 2


@scenario(fast=False)
def patched_any_next(p, module):
    original = module.any_next_words_form_swear_word
    module.any_next_words_form_swear_word = lambda w, i, c: original(w, i[:2], c)


def run_scenario(name, monkeypatch, fallbacks):
    fn, fast = SCENARIOS[name]
    a, b = up.Profanity(), rs.Profanity()
    with monkeypatch.context() as m:
        for module in (up_module, rs_module):
            for attr in ("get_replacement_for_swear_word", "any_next_words_form_swear_word"):
                m.setattr(module, attr, getattr(module, attr))
        fn(a, up_module)
        fn(b, rs_module)
        rng = random.Random(name)
        texts = EXAMPLES[:120] + texts_for(["hello", "box", "fuck", "one", "two words"], rng)
        texts = [t for t in texts if not any("\ud800" <= c <= "\udfff" for c in t)]
        for text in texts:
            assert_same(a, b, text)
        assert state(b) == state(a)
    return fast, len(fallbacks) / (2 * len(texts))


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_attribute_changes(name, monkeypatch, fallbacks):
    fast, share = run_scenario(name, monkeypatch, fallbacks)
    if fast:
        assert share == 0
    else:
        assert share > 0.5


ALLOWED_CHANGES = {
    "add_hyphen": lambda s: s.add("-"),
    "add_space": lambda s: s.add(" "),
    "add_nbsp": lambda s: s.update({"\u00a0", "\u2028"}),
    "remove_letter": lambda s: s.discard("a"),
    "swap_same_size": lambda s: (s.remove("e"), s.add("_")),
    "ior": lambda s: s.__ior__({".", ","}),
    "isub": lambda s: s.__isub__({"s", "S"}),
    "add_long_string": lambda s: s.add("ab"),
    "add_surrogate": lambda s: s.add("\ud800"),
    "clear": lambda s: s.clear(),
}


@pytest.mark.parametrize("name", list(ALLOWED_CHANGES))
def test_allowed_characters_changes(name, restore_allowed, fallbacks):
    a, b = up.Profanity(), rs.Profanity()
    rng = random.Random(name)
    texts = EXAMPLES[:120] + texts_for(["fuck", "blow job", "a b"], rng)
    for text in texts[:20]:
        assert_same(a, b, text)
    ALLOWED_CHANGES[name](up.constants.ALLOWED_CHARACTERS)
    ALLOWED_CHANGES[name](rs.constants.ALLOWED_CHARACTERS)
    fallbacks.clear()
    for text in texts:
        assert_same(a, b, text)
    surrogates = sum(any("\ud800" <= c <= "\udfff" for c in t) for t in texts)
    assert len(fallbacks) == 2 * surrogates


def test_allowed_characters_with_other_objects(restore_allowed, fallbacks):
    a, b = up.Profanity(), rs.Profanity()
    up.constants.ALLOWED_CHARACTERS.add(5)
    rs.constants.ALLOWED_CHARACTERS.add(5)
    for text in EXAMPLES[:40]:
        assert_same(a, b, text)
    assert fallbacks


def test_subclasses(fallbacks):
    def make(module):
        class MoreWords(module.Profanity):
            def _get_next_words(self, text, start_idx, num_of_next_words=1):
                return super()._get_next_words(text, start_idx, num_of_next_words + 1)

        class Plain(module.Profanity):
            def censor(self, text, censor_char="#"):
                return super().censor(text, censor_char)

        class Shadowing(module.Profanity):
            @property
            def CENSOR_WORDSET(self):
                return self._words

            @CENSOR_WORDSET.setter
            def CENSOR_WORDSET(self, value):
                self._words = [w for w in value if str(w) != "fuck"]

        class Unhashable(module.Profanity):
            def __eq__(self, other):
                return True

        return [MoreWords(), Plain(), Shadowing(), Unhashable()]

    for a, b in zip(make(up), make(rs)):
        before = len(fallbacks)
        for text in EXAMPLES[:100]:
            assert_same(a, b, text)
        if type(b).__name__ == "Plain":
            assert (
                len(fallbacks)
                == before
                + sum(any("\ud800" <= c <= "\udfff" for c in t) for t in EXAMPLES[:100]) * 2
            )


def test_missing_attributes():
    for name in ["ALLOWED_CHARACTERS", "MAX_NUMBER_COMBINATIONS", "CENSOR_WORDSET"]:
        a, b = up.Profanity(), rs.Profanity()
        delattr(a, name)
        delattr(b, name)
        for text in ["", "a", "  ", "fuck", "fuck you", "x y"]:
            assert outcome(b._hide_swear_words, text, "*") == outcome(
                a._hide_swear_words, text, "*"
            ), (name, text)


def test_allowed_characters_changed_by_reentrant_update(restore_allowed):
    def censor_while_updating(p):
        def changes():
            yield "!"
            p.censor("abcd")
            yield "-"

        p.censor("ab-cd")
        p.ALLOWED_CHARACTERS.update(changes())
        return p.censor("ab-cd")

    assert censor_while_updating(rs.Profanity(["abcd"])) == censor_while_updating(
        up.Profanity(["abcd"])
    )


def test_allowed_characters_during_an_update(restore_allowed):
    def censor_during_update(p):
        seen = []

        def changes():
            yield "!"
            seen.append(p.censor("abcd"))
            yield "-"
            seen.append(p.censor("ab-cd"))

        p.ALLOWED_CHARACTERS.update(changes())
        return seen + [p.censor("ab-cd")]

    assert censor_during_update(rs.Profanity(["abcd"])) == censor_during_update(
        up.Profanity(["abcd"])
    )


def test_allowed_characters_changed_by_other_threads(restore_allowed):
    p = rs.Profanity(["hello"])
    allowed = rs.constants.ALLOWED_CHARACTERS
    stop = threading.Event()
    errors = []

    def censor():
        try:
            while not stop.is_set():
                p.censor("hello there-hello")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    def mutate():
        while not stop.is_set():
            allowed.add("-")
            allowed.discard("-")

    threads = [threading.Thread(target=censor) for _ in range(4)]
    threads += [threading.Thread(target=mutate) for _ in range(2)]
    switch = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        for t in threads:
            t.start()
        threading.Event().wait(1.5)
    finally:
        stop.set()
        for t in threads:
            t.join()
        sys.setswitchinterval(switch)
    assert not errors
    for text in ["hello there-hello", "hello-there", "a-hello"]:
        assert p.censor(text) == up.Profanity(["hello"]).censor(text)


def test_cache_calls_no_hash_or_eq(fallbacks):
    def make(module):
        class Strict(module.Profanity):
            def __hash__(self):
                raise RuntimeError("unexpected hash")

            def __eq__(self, other):
                raise RuntimeError("unexpected eq")

        return Strict(["hello"])

    a, b = make(up), make(rs)
    for text in ["hello", "a hello b", "h3llo", "nothing"]:
        assert_same(a, b, text)
    assert not fallbacks


def test_cache_does_not_keep_profanity_alive():
    for words in (lambda p: [p], lambda p: ["hello"], lambda p: tuple(p.CENSOR_WORDSET)):
        p = rs.Profanity(["hello"])
        p.CENSOR_WORDSET = words(p)
        p.censor("hello")
        ref = weakref.ref(p)
        del p
        gc.collect()
        assert ref() is None
    assert all(entry[0]() is not None for entry in _fast._matchers.values())


RECURSION_CHECK = """
import sys
import better_profanity, better_profanity_rs

def at_depth(depth, fn, *args):
    if depth:
        return at_depth(depth - 1, fn, *args)
    try:
        return "ok", fn(*args)
    except RecursionError as e:
        return "raise", e.args

def outcome(depth, fn, *args):
    try:
        return at_depth(depth, fn, *args)
    except RecursionError:
        return "too deep for the test itself"

def pair(words, combinations):
    out = []
    for module in (better_profanity, better_profanity_rs):
        p = module.Profanity(words)
        p.MAX_NUMBER_COMBINATIONS = combinations
        p.censor("warm up")
        out.append(p)
    return out

# CPython 3.11 names the operation that hit the limit, which can differ at the very edge.
kind = (lambda r: r[0]) if sys.version_info[:2] == (3, 11) else (lambda r: r)
diffs = []
for limit, combinations in [(40, 5), (60, 30), (90, 40), (200, 120)]:
    a, b = pair(["bad", "bad bad"], combinations)
    text = "bad " * 45
    sys.setrecursionlimit(limit)
    try:
        for depth in range(limit):
            for fn in ("censor", "contains_profanity"):
                x = outcome(depth, getattr(a, fn), text)
                y = outcome(depth, getattr(b, fn), text)
                if kind(x) != kind(y):
                    diffs.append((limit, combinations, depth, fn, x, y))
    finally:
        sys.setrecursionlimit(1000)
print(len(diffs), diffs[:3])
"""


def test_recursion_errors_match():
    out = subprocess.run(
        [sys.executable, "-c", RECURSION_CHECK], capture_output=True, text=True, check=True
    )
    assert out.stdout.startswith("0 "), out.stdout


def test_original_source_is_upstreams():
    upstream_source = textwrap.dedent(inspect.getsource(up.Profanity._hide_swear_words))
    assert upstream_source == _original.HIDE_SWEAR_WORDS
    path = pathlib.Path(rs_module.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Profanity")
    method = next(n for n in cls.body if getattr(n, "name", None) == "_hide_swear_words")
    lines = path.read_text(encoding="utf-8").splitlines()[method.lineno - 1 : method.end_lineno]
    assert textwrap.dedent("\n".join(lines)) + "\n" == _original.HIDE_SWEAR_WORDS


SOURCELESS_CHECK = """
import better_profanity_rs
from better_profanity_rs import _fast, _original

assert not better_profanity_rs.__file__.endswith(".py")
p = better_profanity_rs.Profanity()
assert _fast._fast_result(p, "that sh1t", "*") == "that ****"
print(p.censor("f.u.c.k you"))
"""


def test_import_without_source_files(tmp_path):
    package = pathlib.Path(rs.__file__).parent
    copy_ = tmp_path / "better_profanity_rs"
    shutil.copytree(package, copy_, ignore=shutil.ignore_patterns("__pycache__"))
    compileall.compile_dir(str(copy_), legacy=True, quiet=1)
    for source in copy_.glob("*.py"):
        source.unlink()
    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    out = subprocess.run(
        [sys.executable, "-c", SOURCELESS_CHECK], capture_output=True, text=True, env=env
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout == up.Profanity().censor("f.u.c.k you") + "\n"


def test_module_keeps_the_gil():
    source = pathlib.Path(__file__).parents[1] / "src" / "lib.rs"
    if not source.exists():
        pytest.skip("Rust sources not available")
    assert "#[pymodule(gil_used = true)]" in source.read_text(encoding="utf-8")


def test_pickle_and_copy(fallbacks):
    a, b = up.Profanity(["hello", "x y"]), rs.Profanity(["hello", "x y"])
    b.CENSOR_WORDSET.append("extra")
    a.CENSOR_WORDSET.append("extra")
    for clone in (pickle.loads(pickle.dumps(b)), copy.deepcopy(b), copy.copy(b)):
        assert state(clone) == state(a)
        for text in ["hello there", "x  y", "extra", "fuck", "h3llo"]:
            assert clone.censor(text) == a.censor(text)
    assert not fallbacks


def test_threads():
    a = up.Profanity(["хайль", "gâu", "ΣΑΣ"])
    texts = [
        f"{i} соседский мальчик сказал ХАЙЛЬ и gâu ΣΑΣ σας {chr(0x400 + i)}" for i in range(400)
    ]
    expected = [a.censor(t) for t in texts]
    b = rs.Profanity(["хайль", "gâu", "ΣΑΣ"])
    errors = []

    def work():
        try:
            for _ in range(3):
                assert [b.censor(t) for t in texts] == expected
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors


def test_install():
    code = """
import better_profanity_rs
better_profanity_rs.install()
import better_profanity
from better_profanity import Profanity, profanity
from better_profanity.better_profanity import Profanity as P2
from better_profanity.varying_string import VaryingString
from better_profanity.constants import ALLOWED_CHARACTERS
import better_profanity.utils
assert better_profanity is better_profanity_rs
assert Profanity is P2 is better_profanity_rs.Profanity
assert profanity is better_profanity_rs.profanity
assert VaryingString is better_profanity_rs.varying_string.VaryingString
assert ALLOWED_CHARACTERS is profanity.ALLOWED_CHARACTERS
print(profanity.censor("fuck this"))
"""
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout == "**** this\n"


def test_public_names():
    for name in ["Profanity", "profanity", "name", "__version__"]:
        assert hasattr(rs, name)
    assert rs.__all__ == up.__all__
    for module in ["better_profanity", "constants", "utils", "varying_string"]:
        upstream = __import__(f"better_profanity.{module}", fromlist=["x"])
        ours = __import__(f"better_profanity_rs.{module}", fromlist=["x"])
        public = {n for n in vars(upstream) if not n.startswith("__")}
        assert public <= set(vars(ours)), module
    assert set(vars(up.Profanity())) == set(vars(rs.Profanity()))


TEXT_CHARS = (
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@$*\"'"
    " _-.,!?\n\t\u00a0\u2028\x1c\x00"
    "éüßİ\u0131Σσς\u2126\u212a\u212b\u01c5\ufb00\u0301\u0307"
    "\u1e9e\u2c2f\u2c5f\ua7c0\U00010570\U0001f600\u216b\u24d0\u24b6"
)

token = st.one_of(
    st.sampled_from(WORDS),
    st.builds(
        lambda w, seed: mutate(random.Random(seed), w), st.sampled_from(WORDS), st.integers()
    ),
    st.sampled_from(CLEAN),
    st.text(alphabet=TEXT_CHARS, max_size=6),
)
separator = st.one_of(
    st.sampled_from(SEPARATORS + ["  ", ", ", "\n", "...", "\u00a0"]),
    st.text(alphabet=" _-.,!?\n\u2028Σ\U0001f600", max_size=3),
)
texts = st.lists(st.tuples(token, separator), max_size=12).map(
    lambda ps: "".join(a + b for a, b in ps)
)


@settings(max_examples=400, deadline=None)
@given(
    text=st.one_of(texts, st.text(max_size=40)), censor_char=st.sampled_from(["*", "-", "", "xy"])
)
def test_fuzz_default_words(default_pair, text, censor_char):
    a, b = default_pair
    assert_same(a, b, text, censor_char)


word = st.one_of(
    st.sampled_from(WORDS),
    st.text(alphabet=TEXT_CHARS, min_size=0, max_size=8),
    st.lists(st.text(alphabet="abcxyzΣσİi", min_size=1, max_size=4), min_size=1, max_size=4).map(
        " ".join
    ),
)


@settings(max_examples=600, deadline=None)
@given(
    words=st.lists(word, min_size=1, max_size=6),
    whitelist=st.none() | st.lists(word, max_size=2),
    text=texts,
    max_combinations=st.none() | st.integers(-2, 8),
)
def test_fuzz_custom_words(words, whitelist, text, max_combinations):
    a, b = up.Profanity(), rs.Profanity()
    for p in (a, b):
        p.load_censor_words(
            list(words), whitelist_words=None if whitelist is None else list(whitelist)
        )
        if max_combinations is not None:
            p.MAX_NUMBER_COMBINATIONS = max_combinations
    assert state(b) == state(a)
    extended = text + " " + " ".join(phrase(random.Random(text), w) for w in words)
    for t in (text, extended):
        assert_same(a, b, t)
