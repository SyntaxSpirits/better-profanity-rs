use rustc_hash::FxHashMap;

/// The words to censor, answering `string in CENSOR_WORDSET` for all of them at once.
///
/// better_profanity stores each word as a `VaryingString` and compares a string with every
/// word in turn. When every variant in `CHARS_MAPPING` is a single character, as in the
/// default mapping, a string equals a `VaryingString` exactly when it has one character per
/// position of the word and each character is one of the variants allowed at its position.
/// A word is therefore a sequence of character sets, and the words form a trie whose edges
/// are those sets. A character can lie in the sets of several edges (`*` stands for any
/// vowel), so a lookup follows every matching edge.
#[derive(Clone, Debug)]
pub struct WordSet {
    nodes: Vec<Node>,
}

#[derive(Clone, Debug, Default)]
struct Node {
    terminal: bool,
    /// One entry per character of each child's set, sorted by character.
    edges: Box<[(char, u32)]>,
}

/// A character set interned by a [`WordSetBuilder`].
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct SetId(u32);

/// Builds a [`WordSet`] from words given as sequences of character sets.
#[derive(Debug)]
pub struct WordSetBuilder {
    sets: Vec<Box<[char]>>,
    set_ids: FxHashMap<Box<[char]>, SetId>,
    /// (node, set) to child node.
    children: FxHashMap<(u32, SetId), u32>,
    terminal: Vec<bool>,
    scratch: Vec<char>,
    ids: Vec<SetId>,
}

impl Default for WordSetBuilder {
    fn default() -> Self {
        WordSetBuilder {
            sets: Vec::new(),
            set_ids: FxHashMap::default(),
            children: FxHashMap::default(),
            terminal: vec![false],
            scratch: Vec::new(),
            ids: Vec::new(),
        }
    }
}

impl WordSetBuilder {
    pub fn new() -> Self {
        Self::default()
    }

    /// The id of a set of characters; equal sets get the same id.
    pub fn intern(&mut self, chars: impl IntoIterator<Item = char>) -> SetId {
        self.scratch.clear();
        self.scratch.extend(chars);
        self.scratch.sort_unstable();
        self.scratch.dedup();
        if let Some(&id) = self.set_ids.get(self.scratch.as_slice()) {
            return id;
        }
        let id = SetId(self.sets.len() as u32);
        let set: Box<[char]> = self.scratch.as_slice().into();
        self.sets.push(set.clone());
        self.set_ids.insert(set, id);
        id
    }

    /// Whether an interned set has no characters, so that no word containing it can match.
    pub fn is_empty_set(&self, id: SetId) -> bool {
        self.sets[id.0 as usize].is_empty()
    }

    /// Adds a word given as interned sets, one per position.
    pub fn insert_sets(&mut self, positions: &[SetId]) {
        let mut node = 0u32;
        for &set in positions {
            let next = self.terminal.len() as u32;
            node = *self.children.entry((node, set)).or_insert(next);
            if node == next {
                self.terminal.push(false);
            }
        }
        self.terminal[node as usize] = true;
    }

    /// Adds a word: for each position, the characters that match there.
    pub fn insert<P, C>(&mut self, positions: P)
    where
        P: IntoIterator<Item = C>,
        C: IntoIterator<Item = char>,
    {
        let mut ids = std::mem::take(&mut self.ids);
        ids.clear();
        ids.extend(positions.into_iter().map(|p| self.intern(p)));
        self.insert_sets(&ids);
        self.ids = ids;
    }

    pub fn build(self) -> WordSet {
        let mut edges: Vec<Vec<(char, u32)>> = vec![Vec::new(); self.terminal.len()];
        for (&(node, set), &child) in &self.children {
            let set = &self.sets[set.0 as usize];
            edges[node as usize].extend(set.iter().map(|&c| (c, child)));
        }
        let nodes = edges
            .into_iter()
            .zip(self.terminal)
            .map(|(mut edges, terminal)| {
                edges.sort_unstable();
                Node {
                    terminal,
                    edges: edges.into_boxed_slice(),
                }
            })
            .collect();
        WordSet { nodes }
    }
}

/// The trie nodes reached by the characters fed so far.
#[derive(Clone, Debug, Default)]
pub struct Walk {
    states: Vec<u32>,
    next: Vec<u32>,
}

impl Walk {
    /// No word starts with the characters fed so far, so no longer string matches either.
    pub fn is_dead(&self) -> bool {
        self.states.is_empty()
    }

    pub(crate) fn copy_from(&mut self, other: &Walk) {
        self.states.clear();
        self.states.extend_from_slice(&other.states);
    }
}

impl WordSet {
    pub fn builder() -> WordSetBuilder {
        WordSetBuilder::new()
    }

    /// Whether the set has no words.
    pub fn is_empty(&self) -> bool {
        !self.nodes[0].terminal && self.nodes[0].edges.is_empty()
    }

    /// Starts `walk` at the empty string.
    pub fn reset(&self, walk: &mut Walk) {
        walk.states.clear();
        walk.states.push(0);
    }

    pub fn step(&self, walk: &mut Walk, c: char) {
        walk.next.clear();
        for &state in &walk.states {
            let edges = &self.nodes[state as usize].edges;
            let start = edges.partition_point(|&(e, _)| e < c);
            for &(e, child) in &edges[start..] {
                if e != c {
                    break;
                }
                walk.next.push(child);
            }
        }
        std::mem::swap(&mut walk.states, &mut walk.next);
    }

    /// Whether the characters fed to `walk` form one of the words.
    pub fn accepts(&self, walk: &Walk) -> bool {
        walk.states.iter().any(|&s| self.nodes[s as usize].terminal)
    }

    /// `s in CENSOR_WORDSET`.
    pub fn contains(&self, s: impl IntoIterator<Item = char>) -> bool {
        let mut walk = Walk::default();
        self.reset(&mut walk);
        for c in s {
            self.step(&mut walk, c);
            if walk.is_dead() {
                return false;
            }
        }
        self.accepts(&walk)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn set(words: &[&[&str]]) -> WordSet {
        let mut b = WordSet::builder();
        for w in words {
            b.insert(w.iter().map(|p| p.chars()));
        }
        b.build()
    }

    #[test]
    fn matches_each_position() {
        let s = set(&[&["a@*", "s$", "s$"], &["o*0", "k"], &["ab"]]);
        assert!(s.contains("ass".chars()));
        assert!(s.contains("*$s".chars()));
        assert!(s.contains("*k".chars()));
        assert!(s.contains("b".chars()));
        assert!(!s.contains("as".chars()));
        assert!(!s.contains("asss".chars()));
        assert!(!s.contains("".chars()));
        assert!(!s.is_empty());
        assert!(set(&[]).is_empty());
        assert!(set(&[&[]]).contains("".chars()));
    }
}
