"""Inputs for comparing better_profanity_rs with better_profanity: dictionary words in leetspeak,
inserted into texts and joined by separators."""

from better_profanity_rs.utils import get_complete_path_of_file, read_wordlist

WORDS = sorted(read_wordlist(get_complete_path_of_file("profanity_wordlist.txt")))

CHARS_MAPPING = {
    "a": ("a", "@", "*", "4"),
    "i": ("i", "*", "l", "1"),
    "o": ("o", "*", "0", "@"),
    "u": ("u", "*", "v"),
    "v": ("v", "*", "u"),
    "l": ("l", "1"),
    "e": ("e", "*", "3"),
    "s": ("s", "$", "5"),
    "t": ("t", "7"),
}

SEPARATORS = [" ", "_", "-", ". ", ""]

CLEAN_TEXT = (
    "If you tickle us do we not laugh? If you poison us do we not die? And if you wrong us "
    "shall we not revenge? The committee met on Tuesday to discuss the budget for the coming "
    "year, and the chair said the assessment would be published in March. Scunthorpe United "
    "played at home; the class assistant passed the ball to Dick Van Dyke. Cocktails at the "
    "Essex hotel, where a hancock shitake mushroom risotto was served, cost $5 each. "
    "Ein Hund läuft über die Straße. Đây là 1 câu nói. Соседский мальчик сказал привет."
)
CLEAN = CLEAN_TEXT.split()


def mutate(rng, word, rate=0.35):
    """`word` with some letters in leetspeak or upper case, and sometimes a letter changed so
    that it no longer matches."""
    out = []
    for c in word:
        variants = CHARS_MAPPING.get(c.lower())
        if variants and rng.random() < rate:
            c = rng.choice(variants)
        elif rng.random() < 0.15:
            c = c.upper()
        out.append(c)
    r = rng.random()
    if r < 0.05 and len(out) > 1:
        del out[rng.randrange(len(out))]
    elif r < 0.1:
        out.insert(rng.randrange(len(out) + 1), rng.choice("xq"))
    return "".join(out)


def phrase(rng, word, separators=SEPARATORS):
    """A dictionary word or phrase in leetspeak, with the spaces of a phrase replaced."""
    parts = [mutate(rng, w) for w in word.split(" ")]
    return rng.choice(separators).join(parts) if rng.random() < 0.5 else " ".join(parts)


def text_with_words(rng, base, inserts):
    """`base` split on spaces with `inserts` mutated dictionary words placed between words."""
    tokens = base.split(" ")
    for _ in range(inserts):
        tokens.insert(rng.randrange(len(tokens) + 1), phrase(rng, rng.choice(WORDS)))
    return " ".join(tokens)


def word_pair(rng, separators=SEPARATORS):
    """Two words, each a mutated dictionary word or a clean word, joined by a separator."""
    a, b = (
        phrase(rng, rng.choice(WORDS)) if rng.random() < 0.7 else rng.choice(CLEAN)
        for _ in range(2)
    )
    return a + rng.choice(separators) + b


def mutated_inputs(rng, base_texts, texts, pairs):
    """`texts` real texts with dictionary words inserted and `pairs` word pairs."""
    out = [text_with_words(rng, rng.choice(base_texts), rng.randint(1, 4)) for _ in range(texts)]
    out += [word_pair(rng) for _ in range(pairs)]
    return out
