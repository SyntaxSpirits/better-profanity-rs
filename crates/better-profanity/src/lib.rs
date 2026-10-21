//! A port of the Python word filter [better_profanity] 0.7.0 that censors exactly the same
//! words, including their leetspeak spellings and words split by separators
//! (`f.u.c.k`, `H4nd j0b`), and leaves every other character of the text as it was.
//!
//! ```
//! use better_profanity::Profanity;
//!
//! let profanity = Profanity::new();
//! assert_eq!(
//!     profanity.censor("That wh0re gave m3 a very good H@nD j0b.", "*"),
//!     "That **** gave m3 a very good ****."
//! );
//! assert!(!profanity.contains_profanity("Hello there"));
//! ```
//!
//! [`Profanity`] follows better_profanity's `Profanity` class. The lower-level
//! [`hide_swear_words`], [`WordSet`] and [`CharSet`] reproduce its algorithm with any word
//! set, separator set and lowercasing; the Python package `better-profanity-rs` uses them to
//! match the interpreter it runs on.
//!
//! [better_profanity]: https://github.com/snguyenthanh/better_profanity

mod censor;
mod charset;
pub mod data;
mod words;

use std::path::Path;
use std::sync::OnceLock;

use rustc_hash::{FxHashMap, FxHashSet};

pub use censor::{hide_swear_words, Config, Lowercase, StdLowercase};
pub use charset::CharSet;
pub use words::{SetId, Walk, WordSet, WordSetBuilder};

/// better_profanity's `Profanity`: a list of words to censor and how to match them.
///
/// Words are lowercased with Rust's Unicode tables, which can differ from those of a given
/// Python version for characters added to Unicode recently.
#[derive(Clone, Debug)]
pub struct Profanity {
    words: Vec<Vec<Box<[char]>>>,
    set: WordSet,
    chars_mapping: FxHashMap<char, Box<[char]>>,
    custom_mapping: bool,
    max_number_combinations: usize,
}

impl Default for Profanity {
    fn default() -> Self {
        Self::new()
    }
}

impl Profanity {
    /// The default word list, as `Profanity()`.
    pub fn new() -> Self {
        let mut p = Self::empty();
        p.load_default_censor_words::<&str>(&[]);
        p
    }

    /// `Profanity(words)`; an empty list loads the default words.
    pub fn with_words<I, S>(words: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: AsRef<str>,
    {
        let mut p = Self::empty();
        p.load_censor_words::<_, _, &str>(words, &[]);
        p
    }

    fn empty() -> Self {
        Profanity {
            words: Vec::new(),
            set: WordSet::builder().build(),
            chars_mapping: data::CHARS_MAPPING
                .iter()
                .map(|&(c, variants)| (c, variants.into()))
                .collect(),
            custom_mapping: false,
            max_number_combinations: 1,
        }
    }

    /// `load_censor_words(custom_words, whitelist_words)`: replaces the words with `words`,
    /// or with the default list if `words` is empty, leaving out those in `whitelist`.
    pub fn load_censor_words<I, S, W>(&mut self, words: I, whitelist: &[W])
    where
        I: IntoIterator<Item = S>,
        S: AsRef<str>,
        W: AsRef<str>,
    {
        let words: Vec<S> = words.into_iter().collect();
        if words.is_empty() {
            self.load_default_censor_words(whitelist);
        } else {
            self.populate(words.iter().map(AsRef::as_ref), whitelist);
        }
    }

    /// `load_censor_words(whitelist_words=whitelist)`: the default word list.
    pub fn load_default_censor_words<W: AsRef<str>>(&mut self, whitelist: &[W]) {
        self.populate(data::read_wordlist(data::WORDLIST), whitelist);
    }

    /// `load_censor_words_from_file(path, whitelist_words)`: one word per line of a UTF-8
    /// file. Unlike [`load_censor_words`](Self::load_censor_words), an empty file leaves no
    /// words.
    pub fn load_censor_words_from_file<W: AsRef<str>>(
        &mut self,
        path: impl AsRef<Path>,
        whitelist: &[W],
    ) -> std::io::Result<()> {
        let text = std::fs::read_to_string(path)?;
        self.populate(data::read_wordlist(&text), whitelist);
        Ok(())
    }

    /// `add_censor_words(words)`: adds words as they are, without lowercasing them or
    /// updating [`max_number_combinations`](Self::max_number_combinations).
    pub fn add_censor_words<I, S>(&mut self, words: I)
    where
        I: IntoIterator<Item = S>,
        S: AsRef<str>,
    {
        for word in words {
            let entry = self.varying(word.as_ref());
            self.words.push(entry);
        }
        self.rebuild();
    }

    /// Replaces `CHARS_MAPPING`, which applies to words loaded or added afterwards.
    pub fn set_chars_mapping<I, V>(&mut self, mapping: I)
    where
        I: IntoIterator<Item = (char, V)>,
        V: IntoIterator<Item = char>,
    {
        self.chars_mapping = mapping
            .into_iter()
            .map(|(c, variants)| (c, variants.into_iter().collect()))
            .collect();
        self.custom_mapping = true;
    }

    /// `MAX_NUMBER_COMBINATIONS`: how many following words are joined to the current one
    /// when looking for phrases. Loading words raises it to the largest number of separator
    /// characters in a word; it never decreases on its own.
    pub fn max_number_combinations(&self) -> usize {
        self.max_number_combinations
    }

    pub fn set_max_number_combinations(&mut self, n: usize) {
        self.max_number_combinations = n;
    }

    /// The number of words, as `len(CENSOR_WORDSET)`.
    pub fn len(&self) -> usize {
        self.words.len()
    }

    pub fn is_empty(&self) -> bool {
        self.words.is_empty()
    }

    /// `censor(text, censor_char)`: replaces each swear word with `censor_char` four times.
    /// With no words loaded, the default list is used, as better_profanity loads it then.
    pub fn censor(&self, text: &str, censor_char: &str) -> String {
        if self.words.is_empty() {
            let mut defaults;
            let source = if self.custom_mapping {
                defaults = self.clone();
                defaults.load_default_censor_words::<&str>(&[]);
                &defaults
            } else {
                static DEFAULT: OnceLock<Profanity> = OnceLock::new();
                DEFAULT.get_or_init(Profanity::new)
            };
            let max = self
                .max_number_combinations
                .max(source.max_number_combinations);
            return source.censor_with(text, censor_char, max);
        }
        self.censor_with(text, censor_char, self.max_number_combinations)
    }

    /// `contains_profanity(text)`: whether censoring changes the text.
    pub fn contains_profanity(&self, text: &str) -> bool {
        self.censor(text, "*") != text
    }

    fn censor_with(&self, text: &str, censor_char: &str, max: usize) -> String {
        let allowed = data::allowed_characters();
        let config = Config {
            words: &self.set,
            allowed,
            helper_allowed: allowed,
            max_number_combinations: max.max(1),
        };
        hide_swear_words(text, censor_char, &config, &mut StdLowercase)
            .unwrap_or_else(|| text.to_owned())
    }

    fn populate<'w, W: AsRef<str>>(
        &mut self,
        words: impl Iterator<Item = &'w str>,
        whitelist: &[W],
    ) {
        let whitelist: FxHashSet<String> = whitelist
            .iter()
            .map(|w| w.as_ref().to_lowercase())
            .collect();
        let unique: FxHashSet<&str> = words.collect();
        let allowed = data::allowed_characters();
        let mut entries = Vec::with_capacity(unique.len());
        for word in unique {
            let word = word.to_lowercase();
            if whitelist.contains(&word) {
                continue;
            }
            let separators = word.chars().filter(|&c| !allowed.contains(c)).count();
            self.max_number_combinations = self.max_number_combinations.max(separators);
            entries.push(self.varying(&word));
        }
        self.words = entries;
        self.rebuild();
    }

    /// `VaryingString(word, char_map=CHARS_MAPPING)`.
    fn varying(&self, word: &str) -> Vec<Box<[char]>> {
        word.chars()
            .map(|c| {
                self.chars_mapping
                    .get(&c)
                    .cloned()
                    .unwrap_or_else(|| Box::new([c]))
            })
            .collect()
    }

    fn rebuild(&mut self) {
        let mut builder = WordSet::builder();
        for word in &self.words {
            builder.insert(word.iter().map(|p| p.iter().copied()));
        }
        self.set = builder.build();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn censor(text: &str) -> String {
        static P: OnceLock<Profanity> = OnceLock::new();
        P.get_or_init(Profanity::new).censor(text, "*")
    }

    #[test]
    fn upstream_examples() {
        assert_eq!(
            censor("That wh0re gave m3 a very good H4nd j0b, dude. You gotta check."),
            "That **** gave m3 a very good ****, dude. You gotta check."
        );
        assert_eq!(
            censor("Those 2 girls 1 cup. You gotta check. "),
            "Those ****. You gotta check. "
        );
        assert_eq!(censor("2 girls 1 cup"), "****");
        assert_eq!(censor("fuck 2 girls 1 cup"), "**** ****");
        assert_eq!(
            censor("  wh0re gave m3 a very good H@nD j0b."),
            "  **** gave m3 a very good ****."
        );
        assert_eq!(
            censor("...pen1s...hello_cat_vagina,,,,qew"),
            "...****...hello_cat_****,,,,qew"
        );
        assert_eq!(censor(""), "");
        assert_eq!(censor("Hi there"), "Hi there");
        assert!(Profanity::new().contains_profanity("he is a m0th3rf*cker"));
    }

    #[test]
    fn custom_words_and_whitelist() {
        let mut p = Profanity::with_words(["happy", "jolly", "merry"]);
        assert!(!p.contains_profanity("Fuck you!"));
        assert!(p.contains_profanity("Have a merry day! :)"));
        p.load_default_censor_words(&["boobs"]);
        assert_eq!(p.censor("I have boobs", "*"), "I have boobs");
        p.add_censor_words(["supremacia ariana"]);
        assert_eq!(p.censor("supremacia ariana", "*"), "****");

        let mut p = Profanity::with_words(["gâu"]);
        assert_eq!(
            p.censor("Con chó sủa gâu gâu!", "-"),
            "Con chó sủa ---- ----!"
        );
        p.load_censor_words(["хайль"], &["x"]);
        assert_eq!(
            p.censor("соседский мальчик сказал хайль и я опешил.", "*"),
            "соседский мальчик сказал **** и я опешил."
        );
    }

    #[test]
    fn added_phrase_matches_across_a_space() {
        let mut custom = Profanity::with_words(["happy", "jolly"]);
        assert_eq!(custom.max_number_combinations(), 1);
        custom.add_censor_words(["merry christmas"]);
        assert!(custom.contains_profanity("Merry Christmas!"));
        assert_eq!(custom.censor("m3rry christmas", "#"), "####");
        // With one following word, better_profanity joins only every other word to the next.
        assert_eq!(custom.censor("a m3rry christmas", "#"), "a m3rry christmas");
        assert_eq!(custom.censor("a b m3rry christmas", "#"), "a b ####");
    }

    #[test]
    fn empty_list_falls_back_to_defaults() {
        let mut p = Profanity::with_words(["only"]);
        p.load_censor_words(["only"], &["ONLY"]);
        assert!(p.is_empty());
        assert_eq!(p.censor("fuck", "*"), "****");
    }
}
