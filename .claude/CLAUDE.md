# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code)
when working with code in this repository.

## What This Is

A Rust workspace defining shared conventions, lint
configuration, and tooling for the praxis-proxy project.
The workspace has no crate members yet; it is a
conventions-and-config template.

## Requirements

- Rust stable 1.94+
- Rust nightly (for `rustfmt`)
- `cargo-audit`, `cargo-deny` (supply chain safety)
- `cargo-llvm-cov` (coverage, optional)

## Commands

```console
make build          # workspace build
make check          # type-check only (fast)
make test           # all tests
make test V=1       # tests with --nocapture
make fmt            # format with nightly rustfmt
make lint           # clippy -D warnings + fmt check
make doc            # docs (warnings denied, private items)
make audit          # cargo audit + cargo deny check
make all            # build + fmt + lint + test + audit
make coverage       # HTML coverage report
make coverage-check # fail if line coverage < 80%
```

Single test:

```console
cargo test test_name
cargo test -p crate_name test_name
```

## Conventions

See `docs/conventions.md` for the full guide. Key points:

- `#![deny(unsafe_code)]` in all crate roots
- All items (public and private) require `///` doc
  comments; enforced by `missing_docs` and
  `missing_docs_in_private_items` lints
- Comments answer "why?", never "what?"; use
  `tracing` for runtime narration
- Reference-style rustdoc links, not inline
- No re-export-only files; import from the source
- Do not document memory efficiency in rustdoc

## Critical Lint Constraints

These lints (from `Cargo.toml` and `clippy.toml`)
directly constrain how code must be written:

- **`unwrap_used = "deny"`**: never use `.unwrap()`;
  use `?`, `map`, or explicit match
- **`str_to_string = "deny"`**: use `to_owned()` for
  `&str` to `String`; `to_string()` only for Display
  formatting on non-string types
- **`too_many_lines` threshold: 30**: functions must
  be short; extract helpers early
- **`cognitive_complexity` threshold: 10**: keep
  branching and nesting shallow
- **`too_many_arguments` threshold: 5**: use structs
  for larger parameter sets
- **`allow_attributes_without_reason = "deny"`**:
  every `#[allow(...)]` requires a reason string,
  e.g. `#[allow(clippy::foo, reason = "...")]`
- **`items_after_statements = "deny"`**: all `let`
  bindings and items must precede executable statements
  within a block
- **`expect_used = "warn"`, `panic = "warn"`**:
  prefer fallible APIs over panicking
- **`indexing_slicing = "warn"`**: prefer `.get()`
  over direct `[]` indexing
- **`implicit_clone = "deny"`**: call `.clone()`
  explicitly, not via deref coercion
- **`todo` / `unimplemented = "deny"`**: no placeholder
  macros; handle errors properly or feature-gate
- **`unused_result_ok = "deny"`**: do not discard
  `Result` via `.ok()`; handle or propagate
- **`exit = "deny"`**: no `std::process::exit()`;
  use graceful shutdown
- **`mem_forget = "deny"`**: no `std::mem::forget()`;
  use `ManuallyDrop` if needed

## Rustdoc Lints

Compile-time rustdoc quality enforcement
(`[workspace.lints.rustdoc]`):

- Broken intra-doc links, bare URLs, unescaped
  backticks, invalid HTML/codeblock attributes: denied
- Every crate needs a crate-level doc comment
- `.cargo/config.toml` sets `rustdocflags = -D warnings`
  globally

## Idiomatic Rust

- `to_owned()` over `to_string()` for `&str`
- `String::new()` for empty strings
- Inline format args: `format!("{var}")`
- `is_some_and()` over `.map(...).unwrap_or(false)`
- Let-chains for nested `if let`
- Pre-computed numeric literals with trailing comment:
  `const MAX: usize = 10_485_760; // 10 MiB`

## File Ordering

1. Constants (with separator comment)
2. Public types, impls, functions
3. Private types and impls
4. Private utility functions (with separator)
5. `#[cfg(test)] mod tests` (always last)

Struct fields: `name` first (if present), then
alphabetical. Impl blocks: `new()` first, then
`name()`, then alphabetical.

Inside `mod tests`: imports, test functions, then
test utilities (with full-width `// Test Utilities`
separator). Test utilities stay inside `#[cfg(test)]`.

## Test Requirements

New capabilities require unit tests and integration
tests. See `docs/conventions.md` for full rules:

- No inline comments in test bodies; use assertion
  messages or `tracing` calls
- No doc comments or regular comments on test
  functions (exception: RFC conformance tests)
- Full-width separator comments only (77 dashes)
- Use "Test Utilities", not "Helpers"

## Workspace Dependencies

Declared in root `Cargo.toml`; use
`workspace = true` in crate `Cargo.toml` files:

- `serde` (with derive), `thiserror`, `tracing`,
  `tracing-subscriber` (env-filter, json), `tokio`

## Release Profile

`panic = "abort"` in release; panics are not
recoverable. Design error handling around `Result`,
not `catch_unwind`.
