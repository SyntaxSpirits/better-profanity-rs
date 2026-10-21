# Changelog

## 0.1.0 - unreleased

First release.

- Rust port of `better_profanity` 0.7.0: `censor` and `contains_profanity` give the same output
  for every input, including leetspeak, phrases across separators, whitelists and custom word
  lists.
- Python package `better-profanity-rs`: the `better_profanity` API and modules, and `install()`
  to replace `import better_profanity`.
- Inputs and states the Rust core does not reproduce exactly (`str` subclasses, lone surrogates,
  multi-character `CHARS_MAPPING` variants, replaced helper methods, `MAX_NUMBER_COMBINATIONS`
  above 50 and others) run `better_profanity`'s own code, bundled in the package.
