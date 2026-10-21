"""Fast drop-in replacement for better_profanity: the same censored text from a Rust core."""

import sys

from . import _fast  # noqa: F401  (must run before the first Profanity is created)
from ._core import __version__
from .better_profanity import Profanity

__all__ = ["name", "__version__", "profanity"]

name = "better_profanity_rs"

profanity = Profanity()

_SUBMODULES = ("better_profanity", "constants", "utils", "varying_string")


def install():
    """Make `import better_profanity` resolve to better_profanity_rs.

    Call it before anything imports better_profanity; modules that already imported it keep the
    original. Covers better_profanity and its modules better_profanity, constants, utils and
    varying_string.
    """
    sys.modules["better_profanity"] = sys.modules[__name__]
    for sub in _SUBMODULES:
        sys.modules["better_profanity." + sub] = sys.modules[__name__ + "." + sub]
