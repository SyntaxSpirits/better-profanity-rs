//! The data of better_profanity 0.7.0: its word list, `CHARS_MAPPING` and `ALLOWED_CHARACTERS`.

use std::sync::OnceLock;

use crate::CharSet;

/// `profanity_wordlist.txt`, the default word list (916 words and phrases, one per line).
pub const WORDLIST: &str = include_str!("../data/profanity_wordlist.txt");

/// `alphabetic_unicode.json`: the letters and marks that, with ASCII letters, digits and
/// `@$*"'`, make up `ALLOWED_CHARACTERS`.
const ALPHABETIC_UNICODE: &str = include_str!("../data/alphabetic_unicode.json");

/// The default `CHARS_MAPPING`: the characters each letter of a word may be written as.
pub const CHARS_MAPPING: &[(char, &[char])] = &[
    ('a', &['a', '@', '*', '4']),
    ('i', &['i', '*', 'l', '1']),
    ('o', &['o', '*', '0', '@']),
    ('u', &['u', '*', 'v']),
    ('v', &['v', '*', 'u']),
    ('l', &['l', '1']),
    ('e', &['e', '*', '3']),
    ('s', &['s', '$', '5']),
    ('t', &['t', '7']),
];

/// `ALLOWED_CHARACTERS`: characters that belong to words. Every other character separates them.
pub fn allowed_characters() -> &'static CharSet {
    static ALLOWED: OnceLock<CharSet> = OnceLock::new();
    ALLOWED.get_or_init(|| {
        let ascii = ('a'..='z')
            .chain('A'..='Z')
            .chain('0'..='9')
            .chain("@$*\"'".chars());
        CharSet::new(
            ascii.chain(parse_string_array(ALPHABETIC_UNICODE)),
            is_python_space,
        )
    })
}

/// Python's `str.isspace()`, which is the same on CPython 3.9 to 3.15.
pub fn is_python_space(c: char) -> bool {
    matches!(
        c,
        '\t'..='\r'
            | '\x1c'..=' '
            | '\u{85}'
            | '\u{a0}'
            | '\u{1680}'
            | '\u{2000}'..='\u{200a}'
            | '\u{2028}'
            | '\u{2029}'
            | '\u{202f}'
            | '\u{205f}'
            | '\u{3000}'
    )
}

/// The non-empty lines of a word list with surrounding whitespace removed, as
/// better_profanity's `read_wordlist` returns them from a file opened in text mode.
pub fn read_wordlist(text: &str) -> impl Iterator<Item = &str> {
    text.split(['\n', '\r'])
        .map(|line| line.trim_matches(is_python_space))
        .filter(|line| !line.is_empty())
}

/// The characters of a JSON array of one-character strings, as `alphabetic_unicode.json` is.
fn parse_string_array(src: &str) -> Vec<char> {
    let mut out = Vec::new();
    let mut chars = src.chars();
    let mut in_string = false;
    let mut high: Option<u32> = None;
    while let Some(c) = chars.next() {
        if !in_string {
            in_string = c == '"';
            continue;
        }
        let code = match c {
            '"' => {
                in_string = false;
                continue;
            }
            '\\' => match chars.next() {
                Some('u') => {
                    let hex: String = chars.by_ref().take(4).collect();
                    u32::from_str_radix(&hex, 16).expect("valid \\u escape")
                }
                Some('n') => '\n' as u32,
                Some('t') => '\t' as u32,
                Some('r') => '\r' as u32,
                Some('b') => 8,
                Some('f') => 12,
                Some(other) => other as u32,
                None => break,
            },
            other => other as u32,
        };
        match (high.take(), code) {
            (None, 0xD800..=0xDBFF) => high = Some(code),
            (Some(h), 0xDC00..=0xDFFF) => {
                out.extend(char::from_u32(
                    0x10000 + ((h - 0xD800) << 10) + (code - 0xDC00),
                ));
            }
            (_, code) => out.extend(char::from_u32(code)),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn allowed_characters_match_python() {
        let unicode = parse_string_array(ALPHABETIC_UNICODE);
        assert_eq!(unicode.len(), 5849);
        assert_eq!(unicode[26], '\u{b5}');
        assert_eq!(unicode.iter().max(), Some(&'\u{e01ef}'));
        let allowed = allowed_characters();
        assert_eq!(allowed.len(), 5849 + 10 + 5);
        assert!(allowed.contains('@') && allowed.contains('é') && allowed.contains('\u{e01ef}'));
        assert!(!allowed.contains(' ') && !allowed.contains('-') && !allowed.contains('_'));
    }

    #[test]
    fn wordlist_has_916_words() {
        assert_eq!(read_wordlist(WORDLIST).count(), 916);
        let words: Vec<&str> = read_wordlist(" a \r\n\r\nb\u{85}\rc\n\n").collect();
        assert_eq!(words, ["a", "b", "c"]);
    }
}
