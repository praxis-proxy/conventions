# Proposals

Proposals for new capabilities and refinements.

Small changes (bug fixes, minor enhancements,
documentation updates) do not require proposals.
Proposals are for features that span multiple PRs,
introduce new architectural patterns, affect the
project's public interface, or are complex enough
they warrant more process.

## Lifecycle

### 1. Discussion

Open a GitHub Discussion describing the change at a
high level. Focus on *what* and *why*, not
implementation details.

Build consensus with community members.

> **Note**: Some implementation details at this stage
> can be OK, depending on the situation. Just keep in
> mind the point of the discussion phase is to get
> consensus that what you're bringing up is a real
> concern that needs to be addressed, regardless of
> "How?" it is addressed.

### 2. Sign-off

A maintainer reviews the discussion and marks it as
approved. This confirms the project is open to the
proposed direction.

> **Note**: It's fair to directly ping maintainers
> asking for review and approval consideration when
> things get stuck.

### 3. Issue

Once the discussion is approved by a maintainer and
resolved, create an `EPIC` issue from the discussion.
Include first a link to the originating discussion,
followed by a high-level summary. This is where all
implementation work will be organized (as sub-tasks).

> **Note**: Maintainers will assign epic and sub-task
> owners.

### 4. Proposal PR

Create a proposal file in `docs/proposals/` and
submit it as a PR. File naming convention:

```console
<issue_number>_<high-level-slug>.md
```

The first PR must contain only the **What?** and
**Why?** sections. The **How?** section is almost
always contentious and must be added in a follow-up
PR after the goals and motivation are accepted. See
the [template] for the full structure.

[template]: proposals/template.md

### 5. Iteration

Iterate on the proposal in subsequent PRs. Add the
**How?** section with requirements and design details.
Refine until a maintainer marks the proposal as
accepted.

### 6. Experimental

Once accepted, someone (perhaps the authors of the
proposal) will be tasked with implementing the feature
and ship it as experimental. Experimental features are
functional but may change based on user feedback, and
nothing about them is guaranteed.

> **Note**: In particular, updates to experimental
> features may make breaking, backwards-incompatible
> changes. An experimental feature may be removed at
> any time.

### 7. Release

After a soak period determined by maintainers a
maintainer may promote the feature from experimental
to released. The proposal status is updated to
`released`.

## Status Values

| Status | Meaning |
| --- | --- |
| `proposed` | Under discussion, not yet accepted |
| `accepted` | Approved for implementation |
| `experimental` | Implemented, shipping as experimental |
| `released` | Stable, fully shipped |
| `withdrawn` | Not proceeding (includes explanation) |

> **Note**: A proposal with status `withdrawn` must
> include a clear, detailed explanation of why it was
> withdrawn.
