# Release Process

## Versioning

Releases use [Semantic Versioning][semver]. The workspace
version is the single source of truth, defined in
`workspace.package.version` in the root `Cargo.toml`. All
workspace crates inherit this version.

[semver]: https://semver.org/

## Pre-release Checklist

Before tagging a release:

- [ ] Lints are clean (`make lint`)
- [ ] All tests pass locally (`make test`)
- [ ] Dependency audit passes (`make audit`)
- [ ] SemVer compliance verified (`make semver`)
- [ ] Version in root `Cargo.toml` is bumped
  (both `workspace.package.version` and any
  `workspace.dependencies` inter-crate versions)
- [ ] `Cargo.lock` is regenerated with the new version
- [ ] `make publish-dry-run` succeeds (add
  `--allow-dirty` when running against uncommitted
  changes)
- [ ] `SECURITY.md` lists the new minor version
- [ ] The `[Unreleased]` section of `CHANGELOG.md` is
  rolled into the new version (see [Changelog](#changelog))

## Tagging a Release

Tags follow the format `v<MAJOR>.<MINOR>.<PATCH>` (e.g.
`v0.1.0`) and must match `workspace.package.version`;
the release workflow rejects mismatched tags. Push the
tag to the repository:

```console
git tag v0.1.0
git push origin v0.1.0
```

Pushing the tag runs the release pipeline
(`.github/workflows/release.yaml`):

1. Validate the tag against the workspace version
2. Run the full test suite
3. Verify every release crate packages cleanly
   (publish dry run)
4. Build and publish the container image to GHCR
5. Create the GitHub release with generated notes

Publishing to crates.io stays a manual step: the
pipeline stops at the dry run. Run `cargo publish` per
crate, in dependency order, once the release is tagged
and green.

## Publishing Container Images

Container images are published to GitHub Container
Registry (GHCR) by the release pipeline. Outside of a
release, the **Publish** workflow
(`.github/workflows/publish.yaml`) can be triggered
manually via `workflow_dispatch` to publish from any
branch or tag.

### Image Tags

The publish steps produce these tags per run:

| Pattern | Example | Description |
| --------- | --------- | ------------- |
| `sha-<hash>` | `sha-abc1234` | Git commit SHA |
| `<branch>` | `main` | Branch name |
| `<version>` | `0.1.0` | Full semver (from git tag) |
| `<major>.<minor>` | `0.1` | Major.minor shorthand |

Semver tags are only generated when the workflow runs
against a semver git tag.

## Changelog

Each repository keeps a `CHANGELOG.md` at its root,
edited by hand, in the
[Keep a Changelog 1.0.0][keepachangelog] format. A
`## [Unreleased]` section sits at the top, and each
version's entries are grouped under these `###`
headings:

- `Added`: new features
- `Changed`: changes to existing behavior
- `Deprecated`: features that will be removed later
- `Removed`: features that are now gone
- `Fixed`: bug fixes
- `Security`: vulnerability fixes

A PR with a user-visible change adds its entry under
`[Unreleased]` in that same PR. Write entries for the
people who run or depend on the project, not as a copy
of the commit subject.

At release time, right before tagging, roll the
`[Unreleased]` section into a versioned heading
(`## [X.Y.Z] - YYYY-MM-DD`) and start a fresh, empty
`[Unreleased]` above it. Update the compare links at the
bottom of the file too: `[Unreleased]` now compares the
new tag to `HEAD`, and the new version compares the
previous tag to the new one. The roll covers everything
merged since the previous tag, including anything that
landed after the version bump.

The GitHub release's notes carry that version's section.
Before publishing the release, paste the section in
place of GitHub's generated "What's Changed" list; the
"New Contributors" and "Full Changelog" lines can stay.
The `skip/changelog` label (`.github/release.yml`) only
affects GitHub's generated notes, never `CHANGELOG.md`.

A repository that adopts the file partway through its
history says near the top of `CHANGELOG.md` that notes
for earlier releases are on its GitHub Releases page.

[keepachangelog]: https://keepachangelog.com/en/1.0.0/

## Release Branches

Release branches are optional and created from tags when
backports are needed. The naming convention is
`release/v<MAJOR>.<MINOR>.x` (e.g. `release/v0.1.x`).

Fixes are cherry-picked onto the release branch, a new
patch tag is created from it, and the release pipeline
runs as usual.

## Container Details

The `Containerfile` builds a minimal Alpine image:

- Static musl build using the release profile (LTO,
  single codegen unit, stripped symbols)
- Dependency layers cached via manifest-first stub
  builds, so source changes do not rebuild dependencies
- Runs as a non-root user

The template image runs the probe binary to completion.
When scaffolding a long-running service, add `EXPOSE`
and a `HEALTHCHECK`, and update the container workflow
to wait for healthy status.
