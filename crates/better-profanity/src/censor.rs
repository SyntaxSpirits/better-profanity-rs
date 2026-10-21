//! `Profanity._hide_swear_words`, step for step.

use std::collections::VecDeque;
use std::ops::Range;

use crate::{CharSet, Walk, WordSet};

/// Python's `str.lower()` for strings with at least one non-ASCII character.
///
/// Python lowercases every character on its own, except that `Σ` becomes `ς` at the end of
/// a word, and its tables follow the Unicode version of the interpreter.
pub trait Lowercase {
    /// Appends the lowercase form of `piece` to `out`.
    fn lower(&mut self, piece: &[char], out: &mut Vec<char>);
}

/// Lowercasing with Rust's Unicode tables, which apply the same rules as Python.
#[derive(Clone, Copy, Debug, Default)]
pub struct StdLowercase;

impl Lowercase for StdLowercase {
    fn lower(&mut self, piece: &[char], out: &mut Vec<char>) {
        let s: String = piece.iter().collect();
        out.extend(s.to_lowercase().chars());
    }
}

/// What `_hide_swear_words` reads besides its arguments.
#[derive(Clone, Copy, Debug)]
pub struct Config<'a> {
    /// `CENSOR_WORDSET`.
    pub words: &'a WordSet,
    /// The module-level `ALLOWED_CHARACTERS`, which splits the text into words.
    pub allowed: &'a CharSet,
    /// `self.ALLOWED_CHARACTERS`, which the helpers that look ahead for the next words use.
    pub helper_allowed: &'a CharSet,
    /// `MAX_NUMBER_COMBINATIONS`, at least 1.
    pub max_number_combinations: usize,
}

/// An entry pair of `next_words_indices`: a following word, and the same word with the
/// separators before it. Both end at `end_index`. `empty` marks the `("", index)` pair
/// that stands for "no more words".
#[derive(Clone, Debug)]
struct Pair {
    sep_start: usize,
    word: Range<usize>,
    end_index: usize,
    empty: bool,
}

/// Censors `text` as better_profanity's `_hide_swear_words(text, censor_char)` does.
///
/// Returns `None` where better_profanity returns `text` itself because it has no word to
/// check.
pub fn hide_swear_words<L: Lowercase + ?Sized>(
    text: &str,
    censor_char: &str,
    config: &Config<'_>,
    lower: &mut L,
) -> Option<String> {
    let all: Vec<char> = text.chars().collect();
    let start = start_of_next_word(&all, 0, config.helper_allowed);
    if start + 1 >= all.len() {
        return None;
    }
    let mut out = String::with_capacity(text.len() + 8);
    out.extend(&all[..start]);
    let mut scanner = Scanner {
        text: &all[start..],
        config,
        lower,
        buf: Vec::new(),
        replacement: censor_char.repeat(4),
    };
    scanner.run(&mut out);
    Some(out)
}

fn start_of_next_word(text: &[char], from: usize, allowed: &CharSet) -> usize {
    (from..text.len())
        .find(|&i| allowed.contains(text[i]))
        .unwrap_or(text.len())
}

struct Scanner<'t, 'c, L: ?Sized> {
    text: &'t [char],
    config: &'c Config<'c>,
    lower: &'c mut L,
    buf: Vec<char>,
    replacement: String,
}

impl<L: Lowercase + ?Sized> Scanner<'_, '_, L> {
    fn run(&mut self, out: &mut String) {
        let text = self.text;
        let n = text.len();
        let mut cur = 0..0;
        let mut skip_index: isize = -1;
        let mut window: VecDeque<Pair> = VecDeque::new();
        let (mut whole, mut full, mut separated) =
            (Walk::default(), Walk::default(), Walk::default());

        for (index, &c) in text.iter().enumerate() {
            if (index as isize) < skip_index {
                continue;
            }
            if self.config.allowed.contains(c) {
                if cur.is_empty() {
                    cur = index..index;
                }
                cur.end = index + 1;
                continue;
            }
            if self.config.allowed.strips_to_empty(&text[cur.clone()]) {
                out.push(c);
                cur = 0..0;
                continue;
            }

            self.update_next_words(&mut window, index);
            self.walk(&mut whole, cur.clone());
            match self.any_next_words_form_swear_word(&whole, &window, &mut full, &mut separated) {
                Some(end_index) => {
                    out.push_str(&self.replacement);
                    skip_index = end_index as isize;
                    window.clear();
                }
                None => {
                    if self.config.words.accepts(&whole) {
                        out.push_str(&self.replacement);
                    } else {
                        out.extend(&text[cur.clone()]);
                    }
                    out.push(c);
                }
            }
            cur = 0..0;
        }

        if !cur.is_empty() && skip_index < n as isize - 1 {
            self.walk(&mut whole, cur.clone());
            if self.config.words.accepts(&whole) {
                out.push_str(&self.replacement);
            } else {
                out.extend(&text[cur]);
            }
        }
    }

    /// `_update_next_words_indices`.
    fn update_next_words(&self, window: &mut VecDeque<Pair>, start_idx: usize) {
        if window.is_empty() {
            self.get_next_words(window, start_idx, self.config.max_number_combinations);
        } else {
            window.pop_front();
            if let Some(last) = window.back() {
                if !last.empty {
                    self.get_next_words(window, last.end_index, 1);
                }
            }
        }
    }

    /// `_get_next_words`, appending to `window`.
    fn get_next_words(&self, window: &mut VecDeque<Pair>, start_idx: usize, count: usize) {
        let text = self.text;
        let allowed = self.config.helper_allowed;
        let mut from = start_idx;
        for remaining in (1..=count.max(1)).rev() {
            let start = start_of_next_word(text, from, allowed);
            if start + 1 >= text.len() {
                window.push_back(Pair {
                    sep_start: start,
                    word: start..start,
                    end_index: start,
                    empty: true,
                });
                return;
            }
            // `_get_next_word_and_end_index`: the index of the first character after the
            // word, or of the word's last character if it ends the text.
            let (word_end, end_index) =
                match (start..text.len()).find(|&i| !allowed.contains(text[i])) {
                    Some(i) => (i, i),
                    None => (text.len(), text.len() - 1),
                };
            window.push_back(Pair {
                sep_start: from,
                word: start..word_end,
                end_index,
                empty: false,
            });
            if remaining == 1 {
                return;
            }
            from = end_index;
        }
    }

    /// `any_next_words_form_swear_word`, given the walk over `cur_word.lower()`.
    fn any_next_words_form_swear_word(
        &mut self,
        whole: &Walk,
        window: &VecDeque<Pair>,
        full: &mut Walk,
        separated: &mut Walk,
    ) -> Option<usize> {
        if whole.is_dead() {
            return None;
        }
        full.copy_from(whole);
        separated.copy_from(whole);
        for pair in window {
            if pair.empty {
                continue;
            }
            self.feed(full, pair.word.clone());
            self.feed(separated, pair.sep_start..pair.word.end);
            let words = self.config.words;
            if words.accepts(full) || words.accepts(separated) {
                return Some(pair.end_index);
            }
            if full.is_dead() && separated.is_dead() {
                return None;
            }
        }
        None
    }

    /// Starts `walk` over `text[range].lower()`.
    fn walk(&mut self, walk: &mut Walk, range: Range<usize>) {
        self.config.words.reset(walk);
        self.feed(walk, range);
    }

    /// Continues `walk` with `text[range].lower()`.
    fn feed(&mut self, walk: &mut Walk, range: Range<usize>) {
        if walk.is_dead() {
            return;
        }
        let words = self.config.words;
        let piece = &self.text[range];
        if piece.iter().all(char::is_ascii) {
            for &c in piece {
                words.step(walk, c.to_ascii_lowercase());
                if walk.is_dead() {
                    return;
                }
            }
            return;
        }
        self.buf.clear();
        self.lower.lower(piece, &mut self.buf);
        for &c in &self.buf {
            words.step(walk, c);
            if walk.is_dead() {
                return;
            }
        }
    }
}
