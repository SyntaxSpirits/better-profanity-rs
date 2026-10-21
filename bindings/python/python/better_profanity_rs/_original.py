"""The source of Profanity._hide_swear_words in better_profanity 0.7.0, which _fast compiles
again with the Rust path as its first step. Kept here so that no source files are needed at run
time; a test checks it against better_profanity.py."""

HIDE_SWEAR_WORDS = '''\
def _hide_swear_words(self, text, censor_char):
    """Replace the swear words with censor characters."""
    censored_text = ""
    cur_word = ""
    skip_index = -1
    next_words_indices = []
    start_idx_of_next_word = self._get_start_index_of_next_word(text, 0)

    # If there are no words in the text, return the raw text without parsing
    if start_idx_of_next_word >= len(text) - 1:
        return text

    # Left strip the text, to avoid inaccurate parsing
    if start_idx_of_next_word > 0:
        censored_text = text[:start_idx_of_next_word]
        text = text[start_idx_of_next_word:]

    # Splitting each word in the text to compare with censored words
    for index, char in iter(enumerate(text)):
        if index < skip_index:
            continue
        if char in ALLOWED_CHARACTERS:
            cur_word += char
            continue

        # Skip continuous non-allowed characters
        if cur_word.strip() == "":
            censored_text += char
            cur_word = ""
            continue

        # Iterate the next words combined with the current one
        # to check if it forms a swear word
        next_words_indices = self._update_next_words_indices(
            text, next_words_indices, index
        )
        contains_swear_word, end_index = any_next_words_form_swear_word(
            cur_word, next_words_indices, self.CENSOR_WORDSET
        )
        if contains_swear_word:
            cur_word = get_replacement_for_swear_word(censor_char)
            skip_index = end_index
            char = ""
            next_words_indices = []

        # If the current a swear word
        if cur_word.lower() in self.CENSOR_WORDSET:
            cur_word = get_replacement_for_swear_word(censor_char)

        censored_text += cur_word + char
        cur_word = ""

    # Final check
    if cur_word != "" and skip_index < len(text) - 1:
        if cur_word.lower() in self.CENSOR_WORDSET:
            cur_word = get_replacement_for_swear_word(censor_char)
        censored_text += cur_word
    return censored_text
'''
