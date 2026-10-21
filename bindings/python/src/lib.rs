use std::sync::{Mutex, MutexGuard};

use better_profanity::{
    hide_swear_words, CharSet, Config, Lowercase, SetId, StdLowercase, WordSet, WordSetBuilder,
};
use pyo3::ffi;
use pyo3::intern;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyInt, PyList, PyString, PyTuple, PyType};
use rustc_hash::FxHashMap;

/// `ALLOWED_CHARACTERS` as the Rust core reads it.
#[pyclass(frozen, module = "better_profanity_rs._core")]
struct CharTable {
    set: CharSet,
}

#[pymethods]
impl CharTable {
    /// `chars` holds the one-character members of the set; `spaces` those of them for which
    /// `str.isspace()` is true.
    #[new]
    fn new(chars: &str, spaces: &str) -> Self {
        let spaces: Vec<char> = spaces.chars().collect();
        CharTable {
            set: CharSet::new(chars.chars(), |c| spaces.contains(&c)),
        }
    }
}

/// The characters of an exact `str`, with `None` for lone surrogates, or `None` for any other
/// object. Texts that contain a surrogate take the Python path, so a surrogate never matches.
fn str_chars(obj: &Bound<'_, PyAny>) -> Option<Vec<Option<char>>> {
    let s = obj.cast_exact::<PyString>().ok()?;
    let len = s.len().ok()?;
    // SAFETY: `s` is a str and every index is below its length, so PyUnicode_ReadChar cannot
    // fail.
    Some(
        (0..len)
            .map(|i| {
                char::from_u32(unsafe { ffi::PyUnicode_ReadChar(s.as_ptr(), i as ffi::Py_ssize_t) })
            })
            .collect(),
    )
}

/// Compiles `CENSOR_WORDSET` entries, reading each `CHARS_MAPPING` value once.
struct Compiler<'a, 'py> {
    varying_string: &'a Bound<'py, PyType>,
    builder: WordSetBuilder,
    /// Set per combination object, keyed by address; the entries keep the objects alive.
    sets: FxHashMap<*mut ffi::PyObject, Option<SetId>>,
    /// The same for the variant of a 1-tuple.
    variants: FxHashMap<*mut ffi::PyObject, Option<SetId>>,
    word: Vec<SetId>,
}

impl<'py> Compiler<'_, 'py> {
    /// The characters one position of a `VaryingString` matches (an empty set if only
    /// surrogates), or `None` if a variant is not a single character.
    fn combo_set(&mut self, combo: &Bound<'py, PyAny>) -> Option<SetId> {
        if let Some(&set) = self.sets.get(&combo.as_ptr()) {
            return set;
        }
        // Characters without a mapping get a new 1-tuple each, usually of a shared 1-char str.
        if let Ok(tuple) = combo.cast_exact::<PyTuple>() {
            if tuple.len() == 1 {
                let variant = tuple.get_item(0).ok()?;
                if let Some(&set) = self.variants.get(&variant.as_ptr()) {
                    return set;
                }
                let set = match str_chars(&variant)?.as_slice() {
                    &[c] => Some(self.builder.intern(c)),
                    _ => None,
                };
                self.variants.insert(variant.as_ptr(), set);
                return set;
            }
        }
        let set = (|| {
            let variants: Vec<Option<char>> = if let Ok(tuple) = combo.cast_exact::<PyTuple>() {
                let mut out = Vec::with_capacity(tuple.len());
                for variant in tuple.iter() {
                    match str_chars(&variant)?.as_slice() {
                        &[c] => out.push(c),
                        _ => return None,
                    }
                }
                out
            } else {
                str_chars(combo)?
            };
            if variants.is_empty() {
                return None;
            }
            Some(self.builder.intern(variants.into_iter().flatten()))
        })();
        self.sets.insert(combo.as_ptr(), set);
        set
    }

    /// Adds one entry. Returns false if the trie cannot express how the entry compares with
    /// strings. Entries that can only match texts with surrogates are left out.
    fn add(&mut self, item: &Bound<'py, PyAny>) -> bool {
        self.try_add(item).is_some()
    }

    fn try_add(&mut self, item: &Bound<'py, PyAny>) -> Option<()> {
        let py = item.py();
        self.word.clear();
        if item.cast_exact::<PyString>().is_ok() {
            for c in str_chars(item)? {
                let Some(c) = c else { return Some(()) };
                let set = self.builder.intern([c]);
                self.word.push(set);
            }
        } else {
            if !item.get_type().is(self.varying_string) {
                return None;
            }
            // The matcher keeps its items alive, so they must not lead back to anything else,
            // such as the Profanity object that caches the matcher.
            let fields = item.getattr(intern!(py, "__dict__")).ok()?;
            let fields = fields.cast_exact::<PyDict>().ok()?;
            let original = intern!(py, "_original");
            if fields.len() != 4
                || item
                    .getattr(original)
                    .ok()?
                    .cast_exact::<PyString>()
                    .is_err()
            {
                return None;
            }
            for name in [
                original,
                intern!(py, "_char_combos"),
                intern!(py, "_min_len"),
                intern!(py, "_max_len"),
            ] {
                if !fields.contains(name).ok()? {
                    return None;
                }
            }
            let combos = item.getattr(intern!(py, "_char_combos")).ok()?;
            let combos = combos.cast_exact::<PyList>().ok()?;
            for name in [intern!(py, "_min_len"), intern!(py, "_max_len")] {
                let len = item.getattr(name).ok()?;
                if len.cast_exact::<PyInt>().is_err()
                    || len.extract::<usize>().ok()? != combos.len()
                {
                    return None;
                }
            }
            for combo in combos.iter() {
                let set = self.combo_set(&combo)?;
                self.word.push(set);
            }
        }
        if !self.word.iter().any(|&set| self.builder.is_empty_set(set)) {
            self.builder.insert_sets(&self.word);
        }
        Some(())
    }
}

/// `CENSOR_WORDSET` compiled to a trie, with the items it was compiled from.
///
/// The items are kept so that their addresses cannot be reused while the matcher exists; the
/// list or tuple itself is not, so that the matcher holds nothing that could refer back to the
/// Profanity object it is cached for.
#[pyclass(frozen, module = "better_profanity_rs._core")]
struct WordMatcher {
    is_list: bool,
    items: Vec<Py<PyAny>>,
    set: Option<WordSet>,
}

/// The items of an exact list or tuple, and whether it is a list.
fn entries<'py>(words: &Bound<'py, PyAny>) -> Option<(bool, Vec<Bound<'py, PyAny>>)> {
    if let Ok(list) = words.cast_exact::<PyList>() {
        Some((true, list.iter().collect()))
    } else if let Ok(tuple) = words.cast_exact::<PyTuple>() {
        Some((false, tuple.iter().collect()))
    } else {
        None
    }
}

#[pymethods]
impl WordMatcher {
    /// Compiles an exact list or tuple of `VaryingString` objects (of the class given) and
    /// plain strings. For anything else, `usable` is false and nothing is kept.
    #[new]
    fn new(words: &Bound<'_, PyAny>, varying_string: &Bound<'_, PyType>) -> Self {
        let mut compiler = Compiler {
            varying_string,
            builder: WordSet::builder(),
            sets: FxHashMap::default(),
            variants: FxHashMap::default(),
            word: Vec::new(),
        };
        match entries(words) {
            Some((is_list, items)) if items.iter().all(|item| compiler.add(item)) => WordMatcher {
                is_list,
                items: items.into_iter().map(Bound::unbind).collect(),
                set: Some(compiler.builder.build()),
            },
            _ => WordMatcher {
                is_list: false,
                items: Vec::new(),
                set: None,
            },
        }
    }

    #[getter]
    fn usable(&self) -> bool {
        self.set.is_some()
    }

    /// Whether `words` is a list or tuple, as compiled, holding the same items in the same
    /// order.
    fn is_current(&self, words: &Bound<'_, PyAny>) -> bool {
        let ptr = words.as_ptr();
        // SAFETY: the type is checked first; `words` stays alive during the call, and
        // PyList_GetItem and PyTuple_GetItem return borrowed references for indexes in range,
        // which are only compared.
        unsafe {
            let (len, get): (ffi::Py_ssize_t, unsafe extern "C" fn(_, _) -> _) =
                if self.is_list && ffi::PyList_CheckExact(ptr) != 0 {
                    (ffi::PyList_Size(ptr), ffi::PyList_GetItem)
                } else if !self.is_list && ffi::PyTuple_CheckExact(ptr) != 0 {
                    (ffi::PyTuple_Size(ptr), ffi::PyTuple_GetItem)
                } else {
                    return false;
                };
            self.set.is_some()
                && len == self.items.len() as ffi::Py_ssize_t
                && self
                    .items
                    .iter()
                    .enumerate()
                    .all(|(i, item)| get(ptr, i as ffi::Py_ssize_t) == item.as_ptr())
        }
    }

    /// `_hide_swear_words(text, censor_char)`, or None if the text or `censor_char` has lone
    /// surrogates.
    #[allow(clippy::too_many_arguments)]
    fn hide<'py>(
        &self,
        py: Python<'py>,
        text: &Bound<'py, PyString>,
        censor_char: &Bound<'py, PyString>,
        allowed: &Bound<'py, CharTable>,
        helper_allowed: &Bound<'py, CharTable>,
        max_number_combinations: usize,
        lowercase: &Bound<'py, LowercaseTable>,
    ) -> PyResult<Option<Bound<'py, PyAny>>> {
        let Some(set) = &self.set else {
            return Ok(None);
        };
        let (Ok(s), Ok(c)) = (text.to_cow(), censor_char.to_cow()) else {
            return Ok(None);
        };
        let config = Config {
            words: set,
            allowed: &allowed.get().set,
            helper_allowed: &helper_allowed.get().set,
            max_number_combinations: max_number_combinations.max(1),
        };
        let mut lower = PyLower {
            py,
            table: lowercase.get(),
            error: None,
        };
        let result = hide_swear_words(&s, &c, &config, &mut lower);
        if let Some(e) = lower.error {
            return Err(e);
        }
        Ok(Some(match result {
            None => text.clone().into_any(),
            Some(out) => PyString::new(py, &out).into_any(),
        }))
    }
}

const NOT_LOADED: u32 = 0;
/// Table entries at or above this point index `Blocks::expansions`.
const EXPANSION: u32 = 0x11_0000;

/// `str.lower()` of single characters, loaded from Python 256 code points at a time.
#[derive(Default)]
struct Blocks {
    /// Per block of 256 code points, 1 + its index in `tables`, or NOT_LOADED.
    index: Vec<u32>,
    tables: Vec<[u32; 256]>,
    expansions: Vec<Box<[char]>>,
}

impl Blocks {
    /// Appends the lowercase form of `c`, or returns false if its block is not loaded.
    fn lower(&self, c: char, out: &mut Vec<char>) -> bool {
        let code = c as u32;
        let slot = match self.index.get((code >> 8) as usize) {
            Some(&slot) if slot != NOT_LOADED => slot,
            _ => return false,
        };
        let entry = self.tables[slot as usize - 1][(code & 0xFF) as usize];
        if entry >= EXPANSION {
            out.extend_from_slice(&self.expansions[(entry - EXPANSION) as usize]);
        } else {
            out.extend(char::from_u32(entry));
        }
        true
    }

    fn load(&mut self, block: u32, pairs: Vec<(u32, String)>) {
        if self.index.len() <= block as usize {
            self.index.resize(block as usize + 1, NOT_LOADED);
        }
        if self.index[block as usize] != NOT_LOADED {
            return;
        }
        let mut table = [0u32; 256];
        for (i, entry) in table.iter_mut().enumerate() {
            *entry = (block << 8) | i as u32;
        }
        for (code, lower) in pairs {
            let chars: Vec<char> = lower.chars().collect();
            let entry = &mut table[(code & 0xFF) as usize];
            if chars.len() == 1 {
                *entry = chars[0] as u32;
            } else {
                *entry = EXPANSION + self.expansions.len() as u32;
                self.expansions.push(chars.into_boxed_slice());
            }
        }
        self.tables.push(table);
        self.index[block as usize] = self.tables.len() as u32;
    }
}

/// Python's `str.lower()` for the Rust core: the interpreter's own case tables, fetched with
/// `block(start)`, which returns `(code point, lowercase)` for the characters of
/// `start..start + 256` whose lowercase differs.
#[pyclass(frozen, name = "Lowercase", module = "better_profanity_rs._core")]
struct LowercaseTable {
    block: Py<PyAny>,
    blocks: Mutex<Blocks>,
}

#[pymethods]
impl LowercaseTable {
    #[new]
    fn new(block: Py<PyAny>) -> Self {
        LowercaseTable {
            block,
            blocks: Mutex::new(Blocks::default()),
        }
    }
}

impl LowercaseTable {
    fn blocks(&self) -> MutexGuard<'_, Blocks> {
        self.blocks.lock().unwrap_or_else(|e| e.into_inner())
    }
}

struct PyLower<'py> {
    py: Python<'py>,
    table: &'py LowercaseTable,
    error: Option<PyErr>,
}

impl PyLower<'_> {
    fn python_lower(&self, piece: &[char]) -> PyResult<String> {
        let s: String = piece.iter().collect();
        PyString::new(self.py, &s).call_method0("lower")?.extract()
    }

    fn load_block(&self, block: u32) -> PyResult<()> {
        let pairs: Vec<(u32, String)> = self
            .table
            .block
            .call1(self.py, (block << 8,))?
            .extract(self.py)?;
        self.table.blocks().load(block, pairs);
        Ok(())
    }

    fn try_lower(&self, piece: &[char], out: &mut Vec<char>) -> PyResult<()> {
        // Python lowercases `Σ` depending on the characters around it, so it decides.
        if piece.contains(&'Σ') {
            out.extend(self.python_lower(piece)?.chars());
            return Ok(());
        }
        let start = out.len();
        loop {
            let missing = {
                let blocks = self.table.blocks();
                piece.iter().find(|&&c| {
                    if c.is_ascii() {
                        out.push(c.to_ascii_lowercase());
                        false
                    } else {
                        !blocks.lower(c, out)
                    }
                })
            };
            match missing {
                None => return Ok(()),
                Some(&c) => {
                    out.truncate(start);
                    self.load_block(c as u32 >> 8)?;
                }
            }
        }
    }
}

impl Lowercase for PyLower<'_> {
    fn lower(&mut self, piece: &[char], out: &mut Vec<char>) {
        if self.error.is_none() {
            let start = out.len();
            match self.try_lower(piece, out) {
                Ok(()) => return,
                Err(e) => {
                    out.truncate(start);
                    self.error = Some(e);
                }
            }
        }
        // The error is raised once the scan returns; the output is discarded.
        StdLowercase.lower(piece, out);
    }
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_class::<CharTable>()?;
    m.add_class::<WordMatcher>()?;
    m.add_class::<LowercaseTable>()?;
    Ok(())
}
