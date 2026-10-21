"""The Rust path of Profanity._hide_swear_words.

better_profanity.py, constants.py, utils.py and varying_string.py next to this file are the
modules of better_profanity 0.7.0, unchanged. Importing this module gives
Profanity._hide_swear_words a first step that returns the result from Rust whenever it is certain
to be the same, and replaces ALLOWED_CHARACTERS with a set that notes its own changes. In every
other case the original body runs.
"""

import ast
import functools
import inspect
import linecache
import sys
import textwrap
import weakref

from . import _core, better_profanity, constants
from .better_profanity import Profanity
from .varying_string import VaryingString

# Frames kept free below the recursion limit, beyond those the original's recursion needs.
_MARGIN = 20

_HELPERS = (
    "_get_start_index_of_next_word",
    "_get_next_word_and_end_index",
    "_get_next_words",
    "_update_next_words_indices",
)
_HELPER_NAMES = frozenset(_HELPERS)
_ORIGINAL_HELPERS = tuple(getattr(Profanity, name) for name in _HELPERS)
# Class attributes that would change what the instance attributes read below return.
_SHADOWING = frozenset(
    {
        "__getattribute__",
        "__getattr__",
        "CENSOR_WORDSET",
        "ALLOWED_CHARACTERS",
        "MAX_NUMBER_COMBINATIONS",
    }
)
_MODULE = vars(better_profanity)
_ANY_NEXT = better_profanity.any_next_words_form_swear_word
_REPLACEMENT = better_profanity.get_replacement_for_swear_word
_VARYING_EQ = VaryingString.__eq__
# id(Profanity object) -> (weak reference to it, usable WordMatcher)
_matchers = {}


class AllowedCharacters(set):
    """ALLOWED_CHARACTERS: a set that drops its Rust table whenever it changes.

    `_version` is increased before and after every change, so a table built while a change is
    in progress, from another thread or from code the change itself runs, is never kept.
    """

    __slots__ = ("_table", "_version")

    def __init__(self, *args):
        self._changing()
        try:
            super().__init__(*args)
        finally:
            self._changing()

    def _changing(self):
        self._version = getattr(self, "_version", 0) + 1
        self._table = None

    def __reduce__(self):
        return type(self), (list(self),)


def _invalidating(method):
    @functools.wraps(method)
    def wrapper(self, *args):
        self._changing()
        try:
            return method(self, *args)
        finally:
            self._changing()

    return wrapper


for _name in (
    "add",
    "clear",
    "discard",
    "pop",
    "remove",
    "update",
    "difference_update",
    "intersection_update",
    "symmetric_difference_update",
    "__ior__",
    "__iand__",
    "__isub__",
    "__ixor__",
):
    setattr(AllowedCharacters, _name, _invalidating(getattr(set, _name)))


def _char_table(chars):
    """The Rust table of an AllowedCharacters set, or False if it holds anything but str or
    changed while the table was built.

    Strings longer than one character never equal a character of the text, and texts with
    lone surrogates take the Python path, so both are left out.
    """
    table = chars._table
    if table is not None:
        return table
    version = chars._version
    # list() copies the set in one step, which no other thread can interrupt.
    items = list(chars)
    table = False
    if all(type(c) is str for c in items):
        members = [c for c in items if len(c) == 1 and not "\ud800" <= c <= "\udfff"]
        spaces = [c for c in members if c.isspace()]
        table = _core.CharTable("".join(members), "".join(spaces))
    chars._table = table
    if chars._version != version:
        chars._table = None
        return False
    return table


def _lowercase_block(start):
    """(code point, lowercase) for the characters of start..start + 256 that str.lower()
    changes."""
    pairs = []
    for code in range(start, start + 256):
        char = chr(code)
        lower = char.lower()
        if lower != char:
            pairs.append((code, lower))
    return pairs


_LOWERCASE = _core.Lowercase(_lowercase_block)


def _plain(self):
    """Whether _hide_swear_words would call the original helpers and module functions."""
    cls = type(self)
    for klass in cls.__mro__[:-1]:
        if klass.__dict__.keys() & _SHADOWING:
            return False
    return (
        (
            cls._get_start_index_of_next_word,
            cls._get_next_word_and_end_index,
            cls._get_next_words,
            cls._update_next_words_indices,
        )
        == _ORIGINAL_HELPERS
        and _HELPER_NAMES.isdisjoint(vars(self))
        and _MODULE.get("any_next_words_form_swear_word") is _ANY_NEXT
        and _MODULE.get("get_replacement_for_swear_word") is _REPLACEMENT
        and VaryingString.__eq__ is _VARYING_EQ
    )


def _near_recursion_limit(combinations):
    """Whether the original could exceed the recursion limit from here: it recurses about
    `combinations` calls deep. Frames are counted twice because CPython 3.11 and older also
    count nested C calls toward the limit, assumed to be at most one per Python frame."""
    depth = (sys.getrecursionlimit() - max(combinations, 0) - _MARGIN) // 2
    if depth <= 0:
        return True
    try:
        sys._getframe(depth)
    except ValueError:
        return False
    return True


def _forget(key, ref, matchers=_matchers):
    entry = matchers.get(key)
    if entry is not None and entry[0] is ref:
        matchers.pop(key, None)


def _matcher(self, words):
    """The compiled CENSOR_WORDSET of a Profanity object, or None if it cannot be compiled.

    The cache is keyed by id() so that no __hash__ or __eq__ of a subclass runs, and holds only
    usable matchers, which keep nothing that leads back to the object.
    """
    key = id(self)
    entry = _matchers.get(key)
    ref = entry[0] if entry is not None and entry[0]() is self else None
    if ref is not None and entry[1].is_current(words):
        return entry[1]
    matcher = _core.WordMatcher(words, VaryingString)
    if not matcher.usable:
        _matchers.pop(key, None)
        return None
    if ref is None:
        ref = weakref.ref(self, functools.partial(_forget, key))
    _matchers[key] = (ref, matcher)
    return matcher


def _rust_hide(self, text, censor_char):
    """The censored text from Rust, or None if Rust cannot reproduce this call exactly."""
    allowed = _MODULE.get("ALLOWED_CHARACTERS")
    # better_profanity reads these only for some texts, so a missing one is left to it.
    own = getattr(self, "ALLOWED_CHARACTERS", None)
    limit = getattr(self, "MAX_NUMBER_COMBINATIONS", None)
    if (
        type(allowed) is not AllowedCharacters
        or type(own) is not AllowedCharacters
        or type(limit) is not int
        or _near_recursion_limit(limit)
    ):
        return None
    main = _char_table(allowed)
    helper = main if own is allowed else _char_table(own)
    if not (main and helper):
        return None
    matcher = _matcher(self, getattr(self, "CENSOR_WORDSET", None))
    if matcher is None:
        return None
    return matcher.hide(text, censor_char, main, helper, max(limit, 1), _LOWERCASE)


def _fast_result(self, text, censor_char):
    """The censored text from Rust, or None where the original body must run.

    It runs as the first call of _hide_swear_words, at the depth of the original's first call,
    and calls no Python function before it has checked that the stack is far from the
    recursion limit, so that RecursionError is raised exactly where the original raises it.
    """
    if type(text) is not str or type(censor_char) is not str:
        return None
    try:
        sys._getframe((sys.getrecursionlimit() - _MARGIN) // 2)
        return None
    except ValueError:
        pass
    if not _plain(self):
        return None
    return _rust_hide(self, text, censor_char)


def _with_rust_path(method):
    """`method` with `_fast_result` tried first.

    The original body is compiled again, in its own module's namespace, instead of being called
    from a wrapper: it then runs in the same frame and at the same depth as in better_profanity
    and reads the same, possibly patched, module globals.
    """
    source = textwrap.dedent(inspect.getsource(method))
    function = ast.parse(source).body[0]
    docstring = function.body[0]
    indent = " " * docstring.col_offset
    lines = source.splitlines()
    lines[docstring.end_lineno : docstring.end_lineno] = [
        f"{indent}_result = _rust._fast_result(self, text, censor_char)",
        f"{indent}if _result is not None:",
        f"{indent}    return _result",
    ]
    factory = "def _factory(_rust):\n{}\n    return {}\n".format(
        textwrap.indent("\n".join(lines), "    "), function.name
    )
    filename = f"<better_profanity_rs: Profanity.{function.name}>"
    linecache.cache[filename] = (len(factory), None, factory.splitlines(True), filename)
    namespace = {}
    exec(compile(factory, filename, "exec"), vars(better_profanity), namespace)
    replacement = namespace["_factory"](sys.modules[__name__])
    replacement.__qualname__ = method.__qualname__
    return replacement


_allowed = AllowedCharacters(constants.ALLOWED_CHARACTERS)
constants.ALLOWED_CHARACTERS = _allowed
better_profanity.ALLOWED_CHARACTERS = _allowed
Profanity._hide_swear_words = _with_rust_path(Profanity._hide_swear_words)
