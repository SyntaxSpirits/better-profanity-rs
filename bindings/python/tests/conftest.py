import better_profanity
import pytest

import better_profanity_rs
from better_profanity_rs import _fast


@pytest.fixture
def fallbacks(monkeypatch):
    """Counts calls that took the Python path."""
    calls = []
    original = _fast._original_hide_swear_words

    def counting(self, text, censor_char):
        calls.append(text)
        return original(self, text, censor_char)

    monkeypatch.setattr(_fast, "_original_hide_swear_words", counting)
    return calls


@pytest.fixture
def restore_allowed():
    """Restores ALLOWED_CHARACTERS of both packages after a test changes them."""
    sets = [
        better_profanity.constants.ALLOWED_CHARACTERS,
        better_profanity_rs.constants.ALLOWED_CHARACTERS,
    ]
    saved = [set(s) for s in sets]
    yield
    for s, items in zip(sets, saved):
        s.clear()
        s.update(items)
