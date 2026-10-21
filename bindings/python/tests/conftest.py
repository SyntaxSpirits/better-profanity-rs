import better_profanity
import pytest

import better_profanity_rs
from better_profanity_rs import _fast


@pytest.fixture
def fallbacks(monkeypatch):
    """Counts calls that took the Python path."""
    calls = []
    original = _fast._fast_result

    def counting(self, text, censor_char):
        result = original(self, text, censor_char)
        if result is None:
            calls.append(text)
        return result

    monkeypatch.setattr(_fast, "_fast_result", counting)
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
