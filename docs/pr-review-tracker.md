# PR Review Tracker

Shows which pull request assignees have not yet submitted an initial
review, how long each has been waiting, and reminds them when they are
overdue. This tracks the *first* response only; it does not follow
later review rounds.

Two things are produced:

- Two fields on [project #13] are kept up to date for every tracked
  pull request.
- A reminder comment is posted on a pull request when an assignee has
  owed an initial review for too long.

[project #13]: https://github.com/orgs/praxis-proxy/projects/13

## Parts

| Path | Role |
| --- | --- |
| `.github/actions/review-tracker/` | Composite action and its Python implementation |
| `.github/workflows/pr-review-tracker.yaml` | Reusable workflow wrapping the action |

The workflow reaches the action with GitHub's [self-repository
syntax][self-repo], `uses: $/.github/actions/review-tracker`. That
resolves to *this* repository at the exact commit that is running, so
when `praxis` calls the workflow pinned at some SHA, the action comes
from this repository at that same SHA.

This matters because the workspace-relative `./` form would resolve
against the **caller's** checkout, where the action does not exist,
and a hardcoded absolute pin would have to be kept in step by hand
and would go stale on every release. `$/` needs neither, and no
`actions/checkout` step.

It requires an Actions runner of 2.336.0 or newer, which the
GitHub-hosted `ubuntu-24.04` image satisfies.

[self-repo]: https://github.blog/changelog/2026-07-30-reference-same-repository-actions-with-self-repository-syntax/

## What Counts As A Response

A response is a **submitted** review in one of four states:
`APPROVED`, `CHANGES_REQUESTED`, `COMMENTED`, or `DISMISSED`.

A review only counts with a usable `submitted_at`. That timestamp is
the evidence it was submitted rather than merely started; a review in
a counting state without one is reported, not assumed either way.

Deliberately excluded:

- Pending (unsubmitted) reviews. They carry no `submitted_at` and are
  invisible to everyone but their author.
- Ordinary pull request comments and review-thread replies.
- Reviews from accounts GitHub reports as apps.

A review counts when it was submitted at or after the reviewer's
current assignment began. A review given while the pull request was
still a draft still counts: it is a real initial response.

### Dismissal

`DISMISSED` counts because dismissal is something done to a review
afterwards; it does not un-submit it. Someone who approved and then
had that approval dismissed *did* respond, and their initial-response
timer stays stopped. Dismissal restarts neither the timer nor the
reminder sequence.

What happens after a dismissal is a further review round, which this
version does not track. See [Limitations](#limitations).

Once somebody responds, their timer stops permanently for that
assignment. Nothing else stops it: not an unrelated comment, not a
push by the author, not a label change, not a dismissal.

## When The Clock Starts

For each current human assignee:

1. Their **assignment start** is the timestamp of the most recent
   `assigned` event for them that is not followed by an `unassigned`
   event. Timeline events are replayed in timestamp order, so an
   unassign-and-reassign cycle restarts the clock and a duplicate
   `assigned` event does not.
2. Their **effective start** is the later of that assignment start and
   the most recent `ready_for_review` event on the pull request.

A pull request opened ready has no `ready_for_review` event, so the
effective start is just the assignment start.

### Repeated Draft And Ready Cycles

Only the **most recent** transition to ready counts. Every return to
ready restarts every outstanding assignee's clock from zero.

This matters here because `pr-housekeeping.yaml` converts pull
requests to draft automatically when a required check fails. A pull
request bounced to draft for red CI and later marked ready again gives
its reviewers a fresh clock, which is the intent: nobody owes a review
on a pull request that is failing CI.

The trade-off is that an author can reset reviewer clocks by toggling
draft. Reminder budgets are **not** reset by this, only clocks, so the
worst case is delayed reminders rather than repeated ones. See
[Reminders](#reminders).

## Calculations

Two clocks are used and they are deliberately different.

### Calendar Days (The Project Field)

"Oldest outstanding response (days)" is:

```text
floor((now_utc - effective_start_utc) / 24 hours)
```

Whole 24-hour periods, rounded down. A wait of 47 h 59 m reports `1`.
Weekends are included. The value is the **largest** such number among
the assignees still outstanding on that pull request.

Because this is a pure duration, no timezone affects it.

### Business Days (Reminder Thresholds)

Reminders are gated on Monday-to-Friday days, evaluated in **UTC**,
with **no holiday calendar**.

Advancing `n` business days from an instant means stepping forward one
calendar day at a time, keeping the time of day, counting only days
that land on Monday through Friday:

```text
add_business_days(Friday 10:00, 3)   = Wednesday 10:00
add_business_days(Saturday 10:00, 1) = Monday 10:00
```

Elapsed business days is the exact inverse: the largest `n` for which
`add_business_days(start, n) <= now`. The threshold check and the
"assigned N business days ago" text are derived from the same
function, so they cannot disagree.

UTC is used because every GitHub timestamp is already UTC, runners are
UTC, and there are no daylight-saving discontinuities to shift a
threshold twice a year.

## Project Visibility

For each tracked pull request:

- **"Awaiting response from"** (Text) lists the current assignees who
  still owe an initial review, comma separated and alphabetical, for
  example `ada, grace`. Logins are written without a leading `@`,
  since a project text field does not notify anyone.
- **"Oldest outstanding response (days)"** (Number) is the longest
  calendar-day wait among those people.

Both fields are **cleared** when nothing is outstanding. That covers
all of: everybody has responded, everybody was unassigned, the pull
request was closed or merged, and the pull request went back to draft.
Clearing is driven by walking the project's own items, not the open
pull request list, so a pull request that closed since the last run is
still cleaned up.

Guarantees:

- Project and field IDs are resolved through the API every run. The
  run fails if a field is missing or is not the expected type, rather
  than writing to the wrong field.
- The writer refuses any field ID other than the two resolved ones,
  and can only ever name the project it resolved.
- The writer refuses any item belonging to a different repository.
  See [Other repositories' items](#other-repositories-items).
- Current values are read first; a field already holding the right
  value is not rewritten.
- A pull request with no item on the project is **reported**, never
  added. Importing work onto the board is a human decision.
- No colors, no status field, nothing else is touched.

### Other Repositories' Items

Project #13 is shared by every repository in the organization, and the
tracker runs once per repository. A run must therefore touch only the
items for its own repository, and clearing is where that matters most:
an unscoped clear would wipe the fields of every other repository's
pull requests on every run.

Pull request numbers also repeat across repositories, so `#1` on
`praxis` and `#1` on `ai` are different items. Matching on the number
alone would cross the streams.

Two independent checks, either of which is sufficient:

1. Items are filtered to the run's repository when the board is read,
   so the rest of the run never sees a foreign item.
2. The writer re-checks the repository on every item it is handed and
   refuses the write otherwise, the same way it refuses a field it
   does not own.

Removing either one alone still leaves the other repositories
untouched; removing both is caught by four tests.

## Reminders

Policy: a first reminder after **3 business days**, then one follow-up
after a further **3 business days**, then silence for that assignment.

The comment mentions only the people who are currently assigned, still
owe an initial review, and have reached their threshold:

```text
@ada — This PR has been awaiting your initial review for 3 business days.
```

The message reports how long the review has been **owed**, not how
long ago the person was assigned. Those differ whenever a
draft-to-ready transition moved the clock, so wording it as "assigned
N business days ago" would be wrong on exactly the pull requests that
bounce through draft most often.

Multiple assignees on one pull request are evaluated independently and
can be at different stages; one comment per run carries a line for
each person due.

### Follow-Up Timing

The follow-up is measured from **when the first reminder was actually
posted**, not from the assignment. If the workflow was disabled, rate
limited, or simply not run, a late first reminder does not make the
follow-up instantly due as well.

### Durable State

Each reminder comment carries a machine-readable marker per person:

```text
<!-- praxis-review-reminder {"assigned_at":"...","login":"ada","stage":1} -->
```

State is keyed on `(login, assignment start)`, which gives the right
behavior for free:

- **Reassignment** produces a new key, so the sequence restarts.
- **Draft toggling** does not change the key, so an assignment still
  yields at most two reminders however often CI bounces the pull
  request to draft.

A marker is only believed when the comment's author is the app's own
bot account *and* GitHub reports that account as type `Bot`. A person
cannot post a comment as a bot account, so a marker pasted by hand is
ignored rather than trusted as proof a reminder was sent, in either
direction: it can neither suppress a real reminder nor fake one.

Both halves of that check matter here, because two different
identities share a similar name:

| Login | Type | What it is |
| --- | --- | --- |
| `praxis-bot-app[bot]` | `Bot` | The GitHub App. Posts the reminders. |
| `praxis-bot` | `User` | A separate machine account that submits reviews. |

Only the first is trusted. The login is never hardcoded: the workflow
derives it from the token step's `app-slug` output, so it is always
whichever app actually authenticated. Hardcoding `praxis-bot[bot]`
would be wrong on both counts, since the app's slug is
`praxis-bot-app`.

### Repeat And Concurrent Runs

Three layers:

1. The workflow's `concurrency` group serializes runs per repository.
2. Every pull request is fully re-read immediately before posting:
   the pull request itself, its **timeline**, its reviews, and its
   comments. Anything that changed since the scan suppresses the
   reminder.
3. The marker check runs against that fresh comment list.

The timeline is re-read, not just the assignee list, and the
assignment and draft-to-ready timestamps are recomputed from it.
Comparing assignee lists alone would miss somebody unassigned and
reassigned between the two reads: the list looks identical while the
assignment start, and therefore the reminder key, has moved. Taking
the stale key there would either silence a reminder that is now owed
afresh or fire one against a spent marker.

Skipped automatically: drafts, closed pull requests, people who have
responded, people no longer assigned, and anyone already reminded
twice for their current assignment.

## Safety

- **No code is checked out or executed.** Everything is read through
  the GitHub API. Pull request titles, bodies, comments, and logins
  are handled as data and never interpolated into a shell command.
- **Nothing else is modified.** Auto-assignment, review requests,
  labels, pull request state, and merge settings are untouched. The
  only writes are the two project fields and reminder comments.
- **Credentials stay out of logs.** The token is only ever sent as a
  request header; it is never put in a URL, an error message, or the
  job summary.
- **Incomplete data never triggers a reminder.** If a timestamp is
  missing or unparseable, or an API call fails after retries, that
  pull request is reported and skipped for both project writes and
  reminders. Its existing project values are left alone rather than
  cleared.
- **Rate limits are handled.** Retries honor `Retry-After` and
  `x-ratelimit-reset`, with capped exponential backoff. A run that
  gives up reports the failure and exits non-zero.

## Permissions And Secrets

Secrets, already present in each repository:

- `PRAXIS_BOT_APP_ID`
- `PRAXIS_BOT_APP_PRIVATE_KEY`

The praxis-bot GitHub App token needs:

| Scope | Level | Why |
| --- | --- | --- |
| Pull requests: read & write | Repository | List pull requests and reviews, post reminder comments |
| Issues: read | Repository | Timeline events are served from the issues endpoint |
| Metadata: read | Repository | Mandatory for any installation |
| Projects: read & write | Organization | Read and write the two project fields |

Organization **Members: read** is *not* needed. Assignees are
classified as people or apps from the API's own `type` field, so no
membership lookup happens.

The workflow requests exactly these permissions when it mints the
token, rather than inheriting whatever the installation happens to
hold. A permission the installation lacks makes the token step fail
outright, which is the intended behavior: better a loud failure than
a run that silently cannot write.

### Installation Access

There is one installation of the `praxis-bot-app` GitHub App
(app ID 4068652) on the `praxis-proxy` organization, and its
repository selection is **all repositories**. That covers `praxis`,
`ai`, `policy`, and this repository, so no installation change is
needed to roll this out.

The token is minted with the default repository scope, so it reaches
only the repository the workflow runs in. Organization-level
permissions come with the installation rather than the repository
scope, so a repository-scoped token can still write to project #13.

If the installation is missing a repository, the run fails while
listing pull requests and says so.

## Rollout

Defaults are deliberately inert: **dry run on, both opt-ins off**. A
dry run performs no writes and no comments, and produces a job summary
showing exactly what a live run would have done.

Writes are gated twice. `dry-run` must be `false` **and** the matching
opt-in must be `true`:

| `dry-run` | `apply-project` | `apply-reminders` | Effect |
| --- | --- | --- | --- |
| `true` | anything | anything | Report only |
| `false` | `false` | `false` | Report only |
| `false` | `true` | `false` | Project fields only |
| `false` | `false` | `true` | Reminders only |
| `false` | `true` | `true` | Both |

Suggested order:

1. Dry run by hand on one repository. Read the summary and confirm the
   people, the waits, and the proposed reminders look right.
2. Enable `apply-project` only. Watch the board for a few days.
3. Enable `apply-reminders`.
4. Only then add a schedule.

## Per-Repository Caller

Each repository adds its own caller, pinned to a released tag of this
repository. The caller pins once; the action reference inside the
workflow follows that pin automatically.

```yaml
name: PR Review Tracker

on:
  workflow_dispatch:
    inputs:
      dry-run:
        type: boolean
        default: true
      apply-project:
        type: boolean
        default: false
      apply-reminders:
        type: boolean
        default: false

permissions: {}

jobs:
  track:
    uses: praxis-proxy/conventions/.github/workflows/pr-review-tracker.yaml@<sha> # vX.Y.Z
    with:
      dry-run: ${{ inputs.dry-run }}
      apply-project: ${{ inputs.apply-project }}
      apply-reminders: ${{ inputs.apply-reminders }}
    secrets:
      PRAXIS_BOT_APP_ID: ${{ secrets.PRAXIS_BOT_APP_ID }}
      PRAXIS_BOT_APP_PRIVATE_KEY: ${{ secrets.PRAXIS_BOT_APP_PRIVATE_KEY }}
```

### Enabling A Schedule

This repository ships **no** schedule. Once the behavior has been
validated, add a weekday trigger:

```yaml
on:
  schedule:
    # 08:15 UTC, Monday to Friday.
    - cron: "15 8 * * 1-5"
  workflow_dispatch:
    # ... inputs as above
```

A scheduled run gets no `inputs`, so the values must be supplied
explicitly rather than relying on `${{ inputs.dry-run }}`, which is
empty on a schedule:

```yaml
    with:
      dry-run: ${{ github.event_name == 'workflow_dispatch' && inputs.dry-run || false }}
      apply-project: true
      apply-reminders: true
```

Pick a time that is a working morning for the people being reminded.
Scheduled workflows on GitHub are best-effort and can be delayed under
load; the reminder logic tolerates this because thresholds are
absolute rather than "one run equals one day".

## Testing Before The Default Branch

GitHub registers `workflow_dispatch` only from a workflow file on the
**default branch**. A dispatch-only workflow added on a feature branch
cannot be run at all: it does not appear in the Actions UI, and
`gh workflow run` returns HTTP 404 with "Workflow does not have
'workflow_dispatch' trigger". Once the file is on the default branch,
a dispatch can select any branch as its ref.

The same applies to each repository's caller: it must reach that
repository's own default branch before it can be dispatched.

So this cannot be exercised end-to-end until it merges. What is
available before then:

- `make test-scripts` covers the logic that decides who is reminded
  and how waits are measured, including incomplete data and forged
  markers.
- The script runs locally against the live API in dry run, with a
  maintainer's own token:

  ```console
  cd .github/actions/review-tracker
  GH_TOKEN=$(gh auth token) python3 -m review_tracker \
    --repository praxis-proxy/praxis \
    --organization praxis-proxy \
    --bot-login 'praxis-bot-app[bot]'
  ```

  This reads only. The token needs `read:project` in addition to the
  usual repository scopes. `--now 2026-06-04T10:00:00Z` pins the
  evaluation time, which is useful for checking a threshold.

- After merging with the inert defaults, dispatch from the default
  branch and read the job summary before enabling any opt-in.

## Limitations

- **Only the first response is tracked.** When a review is dismissed,
  or an author pushes changes after a `CHANGES_REQUESTED`, the
  reviewer is effectively owed a second look. This version says
  nothing about that: the person is already discharged and will not
  appear on the board or be reminded again for that assignment.
  Tracking later review rounds is deliberately out of scope here.
- **No holiday calendar.** A reminder can land during somebody's
  holiday or a public holiday in their country.
- **Timeline retention.** If an `assigned` event cannot be found for a
  current assignee, the pull request is reported and skipped. The
  start is never guessed from the pull request's creation or update
  time.
- **One reminder stage per run.** Somebody who crosses both thresholds
  between runs gets the first reminder on the next run and the
  follow-up on the one after, not both at once.
- **Draft toggling delays reminders.** Each return to ready restarts
  the clock, so repeated CI failures can push reminders out.
- **Project item creation is never automatic.** A pull request absent
  from the board gets no visibility until somebody adds it.
