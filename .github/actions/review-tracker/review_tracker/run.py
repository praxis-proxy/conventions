"""Scans one repository, then proposes or applies project and reminder changes.

Writes are gated twice: a run must have dry run turned off, and must also
have the matching opt-in for project fields or reminder comments. A dry run
performs reads only and still produces the full job summary.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import project as board
from .api import ApiError, GitHubApi
from .bizdays import parse_timestamp
from .reminders import due_reminders, parse_records, render
from .tracking import summarize, track

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_OPTIONS = ("bot_login", "organization", "repository")
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass
class Report:
    """Everything one run observed, proposed, or applied."""

    ambiguities: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    project: list = field(default_factory=list)
    reminders: list = field(default_factory=list)
    scanned: int = 0


def main(argv=None, environ=None, api=None, now=None, out=None):
    """Runs the tracker and returns the process exit status."""
    options = parse_options(
        sys.argv[1:] if argv is None else argv,
        os.environ if environ is None else environ,
    )

    moment = now or parse_timestamp(options.now) or datetime.now(timezone.utc)
    client = api or GitHubApi(options.token)

    report = run(client, options, moment)
    _emit(report, options, out)

    return 1 if report.failures else 0


def parse_options(argv, environ):
    """Command line options, defaulting to the action's environment."""
    parser = argparse.ArgumentParser(prog="review_tracker")
    parser.add_argument("--repository", default=environ.get("REPOSITORY"))
    parser.add_argument("--organization", default=environ.get("ORGANIZATION"))
    parser.add_argument("--bot-login", default=environ.get("BOT_LOGIN"))
    parser.add_argument(
        "--project",
        type=int,
        default=int(environ.get("PROJECT_NUMBER") or board.DEFAULT_PROJECT),
    )
    parser.add_argument(
        "--live", action="store_true", default=not _flag(environ, "DRY_RUN", True)
    )
    parser.add_argument(
        "--apply-project", action="store_true", default=_flag(environ, "APPLY_PROJECT")
    )
    parser.add_argument(
        "--apply-reminders",
        action="store_true",
        default=_flag(environ, "APPLY_REMINDERS"),
    )
    parser.add_argument("--now", default=None)

    options = parser.parse_args(argv)
    options.token = environ.get("GH_TOKEN", "")
    options.summary_path = environ.get("GITHUB_STEP_SUMMARY")

    missing = [name for name in REQUIRED_OPTIONS if not getattr(options, name)]
    if missing:
        parser.error(f"missing required options: {', '.join(sorted(missing))}")

    options.dry_run = not options.live
    options.write_project = options.apply_project and options.live
    options.write_reminders = options.apply_reminders and options.live

    return options


def run(client, options, now):
    """Scans the repository and applies whatever this run is allowed to."""
    report = Report()

    tracked, skipped = _scan(client, options, report)
    _sync_project(client, options, tracked, skipped, now, report)
    _remind(client, options, tracked, now, report)

    return report


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _emit(report, options, out):
    """Writes the job summary to the step summary file, or to `out` locally."""
    text = _summary(report, options)

    if options.summary_path:
        with open(options.summary_path, "a", encoding="utf-8") as handle:
            handle.write(text)

    print(text, file=out or sys.stdout)

    for note in report.ambiguities:
        print(f"::warning::{note}", file=out or sys.stdout)
    for note in report.failures:
        print(f"::error::{note}", file=out or sys.stdout)


def _flag(environ, name, default=False):
    """Reads a boolean action input from the environment."""
    raw = environ.get(name)
    if raw is None or raw == "":
        return default

    return raw.strip().lower() in TRUE_VALUES


def _refresh(client, options, number, now):
    """Re-reads a pull request and recomputes what is due, just before posting.

    Re-fetching state, draft status, assignees, reviews, and comments here is
    what makes a reminder safe: anything that changed since the scan, such as
    a review arriving or the author converting the pull request back to
    draft, suppresses the reminder.
    """
    repo = options.repository
    pull = client.rest("GET", f"/repos/{repo}/pulls/{number}")
    timeline = client.paginate(f"/repos/{repo}/issues/{number}/timeline")
    reviews = client.paginate(f"/repos/{repo}/pulls/{number}/reviews")
    comments = client.paginate(f"/repos/{repo}/issues/{number}/comments")

    result = track(pull, timeline, reviews)
    records, notes = parse_records(comments, options.bot_login)
    if not result.trustworthy:
        return [], list(result.ambiguities) + notes

    due, more = due_reminders(result.outstanding, records, now)
    return due, notes + more


def _remind(client, options, tracked, now, report):
    """Posts a reminder comment for every pull request that has one due."""
    for number in sorted(tracked):
        if not tracked[number].outstanding:
            continue

        try:
            due, notes = _refresh(client, options, number, now)
        except ApiError as error:
            report.failures.append(f"#{number}: no reminder sent: {error}")
            continue

        report.ambiguities.extend(f"#{number}: {note}" for note in notes)
        if notes or not due:
            continue

        listed = ", ".join(f"@{item.login} (reminder {item.stage})" for item in due)
        report.reminders.append(f"#{number}: {listed}")

        if not options.write_reminders:
            continue

        try:
            client.rest(
                "POST",
                f"/repos/{options.repository}/issues/{number}/comments",
                {"body": render(due)},
            )
        except ApiError as error:
            report.failures.append(f"#{number}: reminder comment failed: {error}")


def _scan(client, options, report):
    """Tracks every open, ready pull request, and notes the ones it cannot."""
    tracked = {}
    skipped = set()

    try:
        pulls = client.paginate(f"/repos/{options.repository}/pulls?state=open")
    except ApiError as error:
        report.failures.append(f"could not list open pull requests: {error}")
        return tracked, skipped

    for pull in pulls:
        number = pull.get("number")
        if number is None or pull.get("draft"):
            continue

        report.scanned += 1
        repo = options.repository
        try:
            timeline = client.paginate(f"/repos/{repo}/issues/{number}/timeline")
            reviews = client.paginate(f"/repos/{repo}/pulls/{number}/reviews")
        except ApiError as error:
            report.failures.append(f"#{number}: could not be read: {error}")
            skipped.add(number)
            continue

        result = track(pull, timeline, reviews)
        report.ambiguities.extend(f"#{number}: {note}" for note in result.ambiguities)

        if result.trustworthy:
            tracked[number] = result
        else:
            skipped.add(number)

    return tracked, skipped


def _summary(report, options):
    """The job summary describing what this run saw and did."""
    mode = "dry run, no writes" if options.dry_run else "live"
    lines = [
        f"## PR review tracker: {options.repository}",
        "",
        f"Mode: **{mode}** | project writes: "
        f"**{_state(options.write_project)}** | reminders: "
        f"**{_state(options.write_reminders)}**",
        "",
        f"Scanned {report.scanned} open, ready pull request(s) "
        f"against project #{options.project}.",
        "",
    ]

    verb = "Applied" if options.write_project else "Proposed"
    lines += _section(f"{verb} project field changes", report.project, "No changes.")

    verb = "Posted" if options.write_reminders else "Proposed"
    lines += _section(f"{verb} reminders", report.reminders, "None due.")

    lines += _section("Not on the project board", report.missing, "None.")
    lines += _section("Skipped, incomplete or ambiguous data", report.ambiguities, "None.")
    lines += _section("Failures", report.failures, "None.")

    return "\n".join(lines)


def _section(title, entries, empty):
    """One job summary section, rendered as a bullet list."""
    lines = [f"### {title}", ""]
    if entries:
        lines += [f"- {entry}" for entry in entries]
    else:
        lines.append(empty)
    lines.append("")

    return lines


def _state(enabled):
    """The word for whether a class of write is turned on."""
    return "enabled" if enabled else "disabled"


def _sync_project(client, options, tracked, skipped, now, report):
    """Brings both project fields in line with what the scan found."""
    try:
        fields = board.resolve(client, options.organization, options.project)
        existing = board.items(
            client, options.organization, options.project, options.repository
        )
    except ApiError as error:
        report.failures.append(f"project #{options.project}: {error}")
        return

    writer = board.Writer(client, fields, options.write_project)
    covered = set()

    for item in existing:
        covered.add(item.number)
        if item.number in skipped:
            report.ambiguities.append(
                f"#{item.number}: project fields left unchanged, data incomplete"
            )
            continue

        result = tracked.get(item.number)
        awaiting, oldest = summarize(result.outstanding, now) if result else ("", None)

        try:
            changes = writer.apply(item, awaiting, oldest)
        except ApiError as error:
            report.failures.append(f"#{item.number}: project write failed: {error}")
            continue

        if changes:
            report.project.append(f"#{item.number}: " + "; ".join(changes))

    for number in sorted(tracked):
        if number not in covered:
            report.missing.append(
                f"#{number} has no item on project #{options.project}"
            )
