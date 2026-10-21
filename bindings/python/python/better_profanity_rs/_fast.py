"""The Rust path of Profanity._hide_swear_words.

better_profanity.py, constants.py, utils.py and varying_string.py next to this file are the
modules of better_profanity 0.7.0, unchanged. Importing this module replaces
Profanity._hide_swear_words with a version that runs in Rust whenever the outcome is certain to
be the same, and ALLOWED_CHARACTERS with a set that notes its own changes. In every other case
the original method runs.
"""

import functools
import weakref

from . import _core, better_profanity, constants
from .better_profanity import Profanity
from .varying_string import VaryingString

# _get_next_words recurses MAX_NUMBER_COMBINATIONS times. Above this the original runs, so that
# a RecursionError is raised where better_profanity would raise it.
_MAX_COMBINATIONS = 50

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
_original_hide_swear_words = Profanity._hide_swear_words
_matchers = weakref.WeakKeyDictionary()


class AllowedCharacters(set):
    """ALLOWED_CHARACTERS: a set that drops its Rust table whenever it changes."""

    __slots__ = ("_table",)

    def __init__(self, *args):
        super().__init__(*args)
        self._table = None

    def __reduce__(self):
        return type(self), (list(self),)


def _invalidating(method):
    @functools.wraps(method)
    def wrapper(self, *args):
        self._table = None
        return method(self, *args)

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
    """The Rust table of an AllowedCharacters set, or False if it holds anything but str.

    Strings longer than one character never equal a character of the text, and texts with
    lone surrogates take the Python path, so both are left out.
    """
    table = chars._table
    if table is None:
        table = False
        if all(type(c) is str for c in chars):
            members = [c for c in chars if len(c) == 1 and not "\ud800" <= c <= "\udfff"]
            spaces = [c for c in members if c.isspace()]
            table = _core.CharTable("".join(members), "".join(spaces))
        chars._table = table
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
        or limit > _MAX_COMBINATIONS
    ):
        return None
    main = _char_table(allowed)
    helper = main if own is allowed else _char_table(own)
    if not (main and helper):
        return None
    words = getattr(self, "CENSOR_WORDSET", None)
    try:
        matcher = _matchers.get(self)
    except TypeError:
        return None
    if matcher is None or not matcher.is_current(words):
        matcher = _core.WordMatcher(words, VaryingString)
        _matchers[self] = matcher
    return matcher.hide(text, censor_char, main, helper, max(limit, 1), _LOWERCASE)


def _hide_swear_words(self, text, censor_char):
    """Replace the swear words with censor characters."""
    if type(text) is str and type(censor_char) is str and _plain(self):
        result = _rust_hide(self, text, censor_char)
        if result is not None:
            return result
    return _original_hide_swear_words(self, text, censor_char)


_allowed = AllowedCharacters(constants.ALLOWED_CHARACTERS)
constants.ALLOWED_CHARACTERS = _allowed
better_profanity.ALLOWED_CHARACTERS = _allowed
Profanity._hide_swear_words = _hide_swear_words
