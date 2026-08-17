# CLAUDE.md

This file provides guidance to Claude Code
(claude.ai/code) when working with code in this
repository.

## What This Is

A Rust workspace defining shared conventions, lint
configuration, and tooling for the praxis-proxy
project. The only member is `conventions-probe`, a
minimal lib + bin crate that exists so every quality
gate (build, lint, doc, test, coverage, audit) runs
against real code. Replace it with real crates when
scaffolding a project.

## Requirements

- Rust stable 1.96+
- Rust nightly (for `rustfmt`)
- `cargo-machete` (unused dependency detection)
- `cargo-audit`, `cargo-deny` (supply chain safety)
- `cargo-llvm-cov` (coverage, optional)
- `cargo-semver-checks` (SemVer compliance, optional)

## Commands

```console
make build          # workspace build
make check          # type-check only (fast)
make test           # all tests
make test V=1       # tests with --nocapture
make mutants        # mutation testing (cargo-mutants)
make fmt            # format with nightly rustfmt
make lint           # clippy -D warnings + fmt check + machete
make lint-extra     # typos + taplo + shellcheck + actionlint
make doc            # docs (warnings denied, private items)
make audit          # cargo audit + cargo deny check
make semver         # cargo semver-checks
make publish-dry-run # package + verify release crates
make container      # build container image
make all            # build + fmt + lint + lint-extra + test + audit
make coverage       # HTML coverage report
make coverage-check # fail if lines < 90% or regions < 80%
```

Single test:

```console
cargo test test_name
cargo test -p crate_name test_name
```

## Conventions

See `docs/conventions.md` for the full guide.

## Rustdoc Lints

Compile-time rustdoc quality enforcement
(`[workspace.lints.rustdoc]`):

- Broken intra-doc links, bare URLs, unescaped
  backticks, invalid HTML/codeblock attributes:
  denied
- Every crate needs a crate-level doc comment
- `.cargo/config.toml` sets
  `rustdocflags = -D warnings` globally

## Workspace Dependencies

Declared in root `Cargo.toml`; use
`workspace = true` in crate `Cargo.toml` files:

- `serde` (with derive), `thiserror`, `tracing`,
  `tracing-subscriber` (env-filter, json), `tokio`

## Release Profile

`panic = "abort"` in release; panics are not
recoverable. Design error handling around `Result`,
not `catch_unwind`.
