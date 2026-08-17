# Praxis Conventions

A template repository for scaffolding Rust projects with
strict, machine-enforced quality standards: opinionated
lint configuration, forced testing with high coverage,
mutation testing, supply-chain safety, reviewability
gates on every PR, and a tag-driven release pipeline.

The `conventions-probe` crate is a minimal workspace
member that keeps every quality gate verifiable against
real code. Replace it with real crates when scaffolding
a project.

## What Is Enforced

- **Lints**: ~200 rustc/clippy/rustdoc lints at deny,
  including no unchecked arithmetic, no `as` casts, no
  `unwrap`/`panic`, exhaustive enum matching, and
  documentation on every item (public and private)
- **Testing**: unit + integration tests required; 90%
  line / 80% region coverage floor; mutation testing;
  property-based testing conventions
- **Supply chain**: `cargo audit` + `cargo deny` with
  pinned registries and a license allowlist
- **Reviewability**: PRs capped at 750 added production
  lines, with required descriptions, conventional
  commits, DCO sign-off, and signed commits
- **Everything else**: markdown, TOML, shell, spelling,
  and workflow files are linted too

## Quickstart

Install the [requirements](docs/development.md), then:

```console
make all            # build + fmt + lint + test + audit
make help           # every available target
```

## Documentation

| Document | Contents |
| --- | --- |
| [conventions.md](docs/conventions.md) | Coding style, testing, type design, lint policy |
| [development.md](docs/development.md) | Requirements, build/test/coverage commands |
| [proposals.md](docs/proposals.md) | Proposal lifecycle for larger changes |
| [release.md](docs/release.md) | Versioning, tagging, release pipeline |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contributor entry point and PR gates |

## Scaffolding a New Project

1. Create a new repository from this template
2. Replace `crates/conventions-probe` with real crates
   and update `members` in the root `Cargo.toml`
3. Update `PUBLISH_CRATES` and `LINT_CMDS` in the
   `Makefile`, and the crate list in the `Containerfile`
4. Replace the placeholder owner in
   `.github/CODEOWNERS`, the image labels in the
   `Containerfile`, and the links in
   `.github/ISSUE_TEMPLATE/config.yml`
5. Adjust `SECURITY.md` supported versions and
   `deny.toml` licenses for your dependencies
6. Run `make all` — every gate should pass before the
   first commit
