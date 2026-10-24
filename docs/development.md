# Development

## Requirements

- Rust stable 1.96+
- Rust nightly (for `rustfmt`)
- `cargo-machete` (unused dependency detection)
- `cargo-audit`, `cargo-deny` (supply chain safety)
- `cargo-llvm-cov` (coverage)
- `cargo-semver-checks` (SemVer compliance, optional)
- `cargo-mutants` (mutation testing, optional)
- `cargo-hack` (feature matrix checks, optional)
- `typos`, `taplo`, `shellcheck`, `actionlint`
  (non-Rust lint, required by `make lint`)

## Conventions

**All contributors must read and understand
[conventions.md] before contributing.** The conventions
cover code style, testing requirements, file
organization, and security practices. Submissions
that do not follow these conventions will be rejected.

[conventions.md]:./conventions.md

## Build

```console
make build
make release
make check
```

### Test

```console
make test
make mutants        # mutation testing (cargo-mutants)
```

### Supply Chain Safety

Security is enforced at every stage of development.
`cargo audit` and `cargo deny check` are run as part of
the `make audit` target. The `deny.toml` config bans
wildcard version requirements, unknown registries, and
unknown git sources. Multiple versions of the same crate
produce a warning. All crates enforce
`#![deny(unsafe_code)]` and Clippy runs with
`-D warnings` (zero tolerance).

### Formatting

Formatting requires nightly (`group_imports` and
`imports_granularity` are nightly-only). Both stable and
nightly toolchains must be installed.

```console
make fmt            # format all code
make lint           # check formatting + clippy
```

### Documentation

```console
make doc            # build docs with warnings denied
```

All items (public and private) require `///` doc
comments. The `missing_docs` and
`missing_docs_in_private_items` lints enforce this at
compile time.

Rustdoc warnings are denied globally via
`.cargo/config.toml` (`rustdocflags = ["-D", "warnings"]`),
so `cargo doc` always enforces doc quality even
outside Make.

### Coverage

```console
make coverage       # HTML coverage report
make coverage-check # fail if below threshold
```

Requires `cargo-llvm-cov`. The gate fails below **90%
line coverage or 80% region coverage**. Region coverage
counts each branch of each condition, so untested error
paths fail the gate even when every line executes.

### SemVer Compliance

```console
make semver         # cargo semver-checks
```

Requires `cargo-semver-checks`. Run before releases to
catch breaking API changes that were not reflected in
the version bump.

## Releases

See [release.md](./release.md) for versioning, the
pre-release checklist, tagging, container publishing,
and the release pipeline.

## Project Management

All repositories in the `praxis-proxy` organization
use a consistent workflow for planning, prioritizing,
and tracking work.

### Milestones

Milestones represent a body of work toward a shared
goal (e.g. a release, a feature area, or a hardening
pass). Every issue and pull request should belong to
a milestone. Milestones provide scope boundaries and
help answer "what ships together?"

### Priority

Priority is a native GitHub **issue field** (a
single-select field on the issue itself, not a label).
Every triaged issue should have exactly one priority:

| Priority | Description |
| --- | --- |
| `Urgent` | Must be worked on immediately before anything else |
| `High` | Needs to be worked on immediately, defer to urgent |
| `Medium` | Resolve after high and urgent |
| `Low` | Resolve after all other priority levels |

When picking up work, address issues in priority
order: urgent first, then high, medium, and low.

### Project Boards

GitHub project boards visualize the state of work
across milestones. Use boards to track issues through
their lifecycle (backlog, in progress, in review,
done). Boards are the primary tool for stand-ups and
status checks. An issue that is not on a board has not
been triaged.

### Picking Up Work

An issue is **triaged** once it has a milestone and is
on a project board. It takes both: a milestone or a
board on its own doesn't count.

New issues are labeled `triage/needs-triage`. When an
issue is given a milestone, the label is swapped for
`triage/accepted`, which then stays even if the
milestone is later removed.

Issues can only be assigned once they're triaged. If
someone is assigned to an issue that hasn't been
triaged yet, the [issue triage][triage] workflow
unassigns everyone on it and leaves a comment pointing
here. Ask a maintainer to triage the issue first.

[triage]: ../.github/workflows/issue-triage.yaml

### Pull Request Assignees

Every pull request gets two assignees once it is ready
for review: a maintainer from `core-maintainers` and
a reviewer from `core-reviewers`. The [PR assignees][assignees]
workflow assigns them when the PR is opened, reopened,
or marked ready for review, so drafts wait until they
are marked ready. Repositories that call the workflow
pick their own teams with the `maintainer-teams` and
`reviewer-teams` inputs.

The workflow never picks the PR author, never gives
both roles to the same person, and goes for whoever is
assigned to the fewest open PRs, so the review load
stays spread out. If someone from the right team is
already assigned, it counts them and only fills the
role that is missing.

Changing the assignees by hand is fine. The workflow
never removes anyone, and it only runs again if the PR
is reopened, or goes back to draft and is marked ready.

[assignees]: ../.github/workflows/pr-assignees.yaml

### Pull Request Review Responses

Being assigned to a pull request means you owe it an
initial review. The [review tracker][tracker] shows who
has not responded yet on [project #13][board], in the
"Awaiting response from" and "Oldest outstanding
response (days)" fields, and reminds anyone who has owed
a review for three business days, once more three
business days after that, and then stops.

A submitted review of any kind (approve, request
changes, or comment) stops your timer. Leaving an
ordinary comment does not, and neither does starting a
review you have not submitted.

See [pr-review-tracker.md] for the exact calculations,
the permissions involved, and how to turn it on.

[board]: https://github.com/orgs/praxis-proxy/projects/13
[pr-review-tracker.md]: ./pr-review-tracker.md
[tracker]: ../.github/workflows/pr-review-tracker.yaml
