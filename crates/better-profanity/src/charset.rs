use rustc_hash::FxHashSet;

/// A set of characters, such as `ALLOWED_CHARACTERS`, and which of them are whitespace to
/// Python's `str.strip()`.
#[derive(Clone, Debug)]
pub struct CharSet {
    bmp: Box<[u64]>,
    astral: FxHashSet<char>,
    spaces: FxHashSet<char>,
    len: usize,
}

impl CharSet {
    /// The set of `chars`; `is_space` tells which of them `str.strip()` removes.
    pub fn new(chars: impl IntoIterator<Item = char>, is_space: impl Fn(char) -> bool) -> Self {
        let mut set = CharSet {
            bmp: vec![0; 0x10000 / 64].into_boxed_slice(),
            astral: FxHashSet::default(),
            spaces: FxHashSet::default(),
            len: 0,
        };
        for c in chars {
            if set.contains(c) {
                continue;
            }
            set.len += 1;
            let code = c as usize;
            if code < 0x10000 {
                set.bmp[code / 64] |= 1 << (code % 64);
            } else {
                set.astral.insert(c);
            }
            if is_space(c) {
                set.spaces.insert(c);
            }
        }
        set
    }

    #[inline]
    pub fn contains(&self, c: char) -> bool {
        let code = c as usize;
        if code < 0x10000 {
            self.bmp[code / 64] & (1 << (code % 64)) != 0
        } else {
            self.astral.contains(&c)
        }
    }

    pub fn len(&self) -> usize {
        self.len
    }

    pub fn is_empty(&self) -> bool {
        self.len == 0
    }

    /// Whether `s.strip() == ""` for a string of characters from this set.
    pub(crate) fn strips_to_empty(&self, s: &[char]) -> bool {
        s.iter().all(|c| self.spaces.contains(c))
    }
}
