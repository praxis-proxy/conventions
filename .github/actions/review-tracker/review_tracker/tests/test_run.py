"""End-to-end orchestration: dry runs, opt-ins, clearing, and refresh guards."""

import contextlib
import io
import unittest
from datetime import datetime, timezone

from ..run import main, parse_options, run
from .fakes import FakeApi, item_node

BOT = "praxis-bot[bot]"
REPO = "praxis-proxy/praxis"

# Monday 2026-06-01 10:00 plus three business days.
ASSIGNED = "2026-06-01T10:00:00Z"
NOW = datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc)


class DryRun(unittest.TestCase):
    def test_makes_no_mutations_or_comments(self):
        api = standard()

        report = run(api, options(), NOW)

        self.assertEqual(api.mutations, [], "a dry run must not write project fields")
        self.assertEqual(api.posted, [], "a dry run must not post comments")
        self.assertEqual(report.failures, [], f"nothing should fail: {report.failures}")

    def test_still_reports_what_it_would_do(self):
        report = run(standard(), options(), NOW)

        self.assertEqual(
            report.project,
            ['#1: "Awaiting response from" -> "ada"; '
             '"Oldest outstanding response (days)" -> 3'],
            "the proposed field changes are reported",
        )
        self.assertEqual(
            report.reminders, ["#1: @ada (reminder 1)"], "the proposed reminder is shown"
        )

    def test_ignores_the_opt_ins_while_dry(self):
        api = standard()

        run(api, options(APPLY_PROJECT="true", APPLY_REMINDERS="true"), NOW)

        self.assertEqual(api.mutations, [], "dry run overrides the project opt-in")
        self.assertEqual(api.posted, [], "dry run overrides the reminder opt-in")


class OptIns(unittest.TestCase):
    def test_project_opt_in_writes_only_fields(self):
        api = standard()

        run(api, options(DRY_RUN="false", APPLY_PROJECT="true"), NOW)

        self.assertEqual(
            [name for name, _ in api.mutations],
            ["update", "update"],
            "both project fields are written",
        )
        self.assertEqual(api.posted, [], "the reminder opt-in was not given")

    def test_reminder_opt_in_posts_only_comments(self):
        api = standard()

        run(api, options(DRY_RUN="false", APPLY_REMINDERS="true"), NOW)

        self.assertEqual(api.mutations, [], "the project opt-in was not given")
        self.assertEqual(len(api.posted), 1, "one reminder comment is posted")

        path, payload = api.posted[0]
        self.assertEqual(
            path, f"/repos/{REPO}/issues/1/comments", "the comment goes on the PR"
        )
        self.assertIn("@ada", payload["body"], "the due assignee is mentioned")

    def test_live_without_an_opt_in_writes_nothing(self):
        api = standard()

        run(api, options(DRY_RUN="false"), NOW)

        self.assertEqual(api.mutations, [], "project writes need their own opt-in")
        self.assertEqual(api.posted, [], "reminders need their own opt-in")


class Clearing(unittest.TestCase):
    def test_clears_a_closed_pull_request(self):
        api = standard(
            item_pages=[[item_node("i9", 9, REPO, awaiting="bob", oldest=5)]]
        )

        report = run(api, options(DRY_RUN="false", APPLY_PROJECT="true"), NOW)

        self.assertEqual(
            [name for name, _ in api.mutations],
            ["clear", "clear"],
            f"a PR no longer open has both fields cleared: {report.project}",
        )

    def test_clears_when_everyone_has_responded(self):
        api = standard(
            reviews=[
                {
                    "state": "APPROVED",
                    "user": {"login": "ada"},
                    "submitted_at": "2026-06-02T10:00:00Z",
                }
            ],
            item_pages=[[item_node("i1", 1, REPO, awaiting="ada", oldest=1)]],
        )

        run(api, options(DRY_RUN="false", APPLY_PROJECT="true"), NOW)

        self.assertEqual(
            [name for name, _ in api.mutations],
            ["clear", "clear"],
            "a discharged pull request has both fields cleared",
        )

    def test_clears_and_sends_nothing_after_a_dismissed_review(self):
        api = standard(
            reviews=[
                {
                    "state": "DISMISSED",
                    "user": {"login": "ada"},
                    "submitted_at": "2026-06-02T10:00:00Z",
                }
            ],
            item_pages=[[item_node("i1", 1, REPO, awaiting="ada", oldest=1)]],
        )

        run(api, options(DRY_RUN="false", APPLY_PROJECT="true",
                         APPLY_REMINDERS="true"), NOW)

        self.assertEqual(
            [name for name, _ in api.mutations],
            ["clear", "clear"],
            "a dismissed review still discharges the pull request",
        )
        self.assertEqual(
            api.posted,
            [],
            "dismissal must not restart the reminder sequence",
        )

    def test_leaves_other_repositories_items_untouched(self):
        foreign = [
            item_node("ai-1", 1, "praxis-proxy/ai", awaiting="bob", oldest=9),
            item_node("pol-7", 7, "praxis-proxy/policy", awaiting="carol", oldest=4),
        ]
        api = standard(
            item_pages=[foreign + [item_node("i1", 1, REPO, awaiting="stale", oldest=99)]]
        )

        run(api, options(DRY_RUN="false", APPLY_PROJECT="true"), NOW)

        touched = {variables["item"] for _, variables in api.mutations}
        self.assertEqual(
            touched,
            {"i1"},
            "a run for one repository must only ever write its own items",
        )

    def test_does_not_clear_a_same_numbered_pull_request_elsewhere(self):
        api = standard(
            item_pages=[
                [
                    item_node("ai-1", 1, "praxis-proxy/ai", awaiting="bob", oldest=9),
                    item_node("i1", 1, REPO),
                ]
            ]
        )

        run(api, options(DRY_RUN="false", APPLY_PROJECT="true"), NOW)

        touched = {variables["item"] for _, variables in api.mutations}
        self.assertNotIn(
            "ai-1",
            touched,
            "pull request numbers repeat across repositories; the item must not collide",
        )

    def test_reports_a_pull_request_with_no_project_item(self):
        report = run(standard(item_pages=[[]]), options(), NOW)

        self.assertEqual(
            report.missing,
            ["#1 has no item on project #13"],
            "a missing item is reported rather than created",
        )


class IncompleteData(unittest.TestCase):
    def test_leaves_project_fields_alone_when_data_is_ambiguous(self):
        api = standard(
            timeline=[],
            item_pages=[[item_node("i1", 1, REPO, awaiting="ada", oldest=9)]],
        )

        report = run(api, options(DRY_RUN="false", APPLY_PROJECT="true"), NOW)

        self.assertEqual(
            api.mutations, [], "an ambiguous pull request is never written"
        )
        self.assertTrue(
            any("incomplete" in note for note in report.ambiguities),
            f"the skip must be reported: {report.ambiguities}",
        )

    def test_sends_no_reminder_when_data_is_ambiguous(self):
        api = standard(timeline=[])

        run(api, options(DRY_RUN="false", APPLY_REMINDERS="true"), NOW)

        self.assertEqual(api.posted, [], "incomplete data must not trigger a reminder")

    def test_reports_an_api_failure_and_writes_nothing(self):
        api = standard(fail=("/issues/1/timeline",))

        report = run(api, options(DRY_RUN="false", APPLY_PROJECT="true"), NOW)

        self.assertTrue(report.failures, "an API failure must be surfaced")
        self.assertEqual(api.mutations, [], "a PR that could not be read is untouched")

    def test_exits_non_zero_on_failure(self):
        api = standard(fail=("/issues/1/timeline",))
        out = io.StringIO()

        status = main([], environment(), api=api, now=NOW, out=out)

        self.assertEqual(status, 1, "a failed run must fail the job")
        self.assertIn("::error::", out.getvalue(), "the failure is annotated")


class RefreshBeforePosting(unittest.TestCase):
    def test_suppresses_when_the_pull_request_went_draft(self):
        api = standard()
        api._rest[f"/repos/{REPO}/pulls/1"] = pull(draft=True)

        run(api, options(DRY_RUN="false", APPLY_REMINDERS="true"), NOW)

        self.assertEqual(api.posted, [], "a PR drafted since the scan is skipped")

    def test_suppresses_when_the_pull_request_closed(self):
        api = standard()
        api._rest[f"/repos/{REPO}/pulls/1"] = pull(state="closed")

        run(api, options(DRY_RUN="false", APPLY_REMINDERS="true"), NOW)

        self.assertEqual(api.posted, [], "a PR closed since the scan is skipped")

    def test_suppresses_when_a_review_arrived_since_the_scan(self):
        api = ChangingApi(
            **standard_kwargs(),
            after={
                f"/repos/{REPO}/pulls/1/reviews": [
                    {
                        "state": "COMMENTED",
                        "user": {"login": "ada"},
                        "submitted_at": "2026-06-03T10:00:00Z",
                    }
                ]
            },
        )

        run(api, options(DRY_RUN="false", APPLY_REMINDERS="true"), NOW)

        self.assertEqual(api.posted, [], "a review landing mid-run cancels the reminder")

    def test_detects_a_reassignment_between_the_two_reads(self):
        reassigned = "2026-06-04T09:00:00Z"
        api = ChangingApi(
            **standard_kwargs(
                comments=[marker_comment("ada", ASSIGNED, 1, "2026-06-04T08:00:00Z")]
            ),
            after={
                f"/repos/{REPO}/issues/1/timeline": [
                    {"event": "assigned", "assignee": {"login": "ada"},
                     "created_at": ASSIGNED},
                    {"event": "unassigned", "assignee": {"login": "ada"},
                     "created_at": "2026-06-04T08:30:00Z"},
                    {"event": "assigned", "assignee": {"login": "ada"},
                     "created_at": reassigned},
                ]
            },
        )

        run(api, options(DRY_RUN="false", APPLY_REMINDERS="true"), NOW)

        self.assertEqual(
            api.posted,
            [],
            "the fresh assignment is only minutes old, so nothing is due yet",
        )

    def test_an_old_marker_does_not_silence_a_new_assignment(self):
        spent = "2026-05-15T10:00:00Z"
        api = ChangingApi(
            **standard_kwargs(
                comments=[marker_comment("ada", spent, 2, "2026-05-20T08:00:00Z")]
            ),
            after={
                f"/repos/{REPO}/issues/1/timeline": [
                    {"event": "assigned", "assignee": {"login": "ada"},
                     "created_at": spent},
                    {"event": "unassigned", "assignee": {"login": "ada"},
                     "created_at": "2026-05-20T10:00:00Z"},
                    {"event": "assigned", "assignee": {"login": "ada"},
                     "created_at": ASSIGNED},
                ]
            },
        )

        run(api, options(DRY_RUN="false", APPLY_REMINDERS="true"), NOW)

        self.assertEqual(len(api.posted), 1, "the new assignment earns a reminder")
        self.assertIn(
            "@ada",
            api.posted[0][1]["body"],
            "a spent marker from a previous assignment must not silence this one",
        )

    def test_suppresses_when_a_reminder_already_exists(self):
        api = standard(
            comments=[marker_comment("ada", ASSIGNED, 1, "2026-06-04T09:00:00Z")]
        )

        run(api, options(DRY_RUN="false", APPLY_REMINDERS="true"), NOW)

        self.assertEqual(api.posted, [], "a concurrent run must not remind twice")


class Options(unittest.TestCase):
    def test_defaults_to_a_dry_run_with_no_opt_ins(self):
        parsed = parse_options([], {"REPOSITORY": REPO, "ORGANIZATION": "o",
                                    "BOT_LOGIN": BOT})

        self.assertTrue(parsed.dry_run, "dry run is the default")
        self.assertFalse(parsed.write_project, "project writes are off by default")
        self.assertFalse(parsed.write_reminders, "reminders are off by default")
        self.assertEqual(parsed.project, 13, "project #13 is the default board")

    def test_requires_the_identifying_options(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_options([], {})


# ---------------------------------------------------------------------------
# Test Utilities
# ---------------------------------------------------------------------------


class ChangingApi(FakeApi):
    """Serves different data the second time a path is read, as a refresh does."""

    def __init__(self, after=None, **kwargs):
        super().__init__(**kwargs)
        self._after = dict(after or {})
        self._seen = set()

    def paginate(self, path):
        """Returns the original page once, then the replacement."""
        original = super().paginate(path)
        if path in self._seen and path in self._after:
            return list(self._after[path])

        self._seen.add(path)
        return original


def environment(**overrides):
    """The action environment, with any overrides applied."""
    values = {
        "BOT_LOGIN": BOT,
        "ORGANIZATION": "praxis-proxy",
        "PROJECT_NUMBER": "13",
        "REPOSITORY": REPO,
    }
    values.update(overrides)
    return values


def options(**overrides):
    """Parsed options for a run, dry by default."""
    return parse_options([], environment(**overrides))


def pull(state="open", draft=False):
    """The tracked pull request payload."""
    return {
        "number": 1,
        "state": state,
        "draft": draft,
        "assignees": [{"login": "ada", "type": "User"}],
    }


def standard(**overrides):
    """A fake API serving one open pull request with one outstanding assignee."""
    return FakeApi(**standard_kwargs(**overrides))


def standard_kwargs(timeline=None, reviews=None, comments=None, item_pages=None,
                    fail=()):
    """Constructor arguments for the standard fixture."""
    events = (
        [{"event": "assigned", "assignee": {"login": "ada"}, "created_at": ASSIGNED}]
        if timeline is None
        else timeline
    )

    return {
        "fail": fail,
        "item_pages": item_pages or [[item_node("i1", 1, REPO)]],
        "pages": {
            f"/repos/{REPO}/pulls?state=open": [pull(), draft_pull()],
            f"/repos/{REPO}/issues/1/timeline": events,
            f"/repos/{REPO}/pulls/1/reviews": reviews or [],
            f"/repos/{REPO}/issues/1/comments": comments or [],
        },
        "rest": {f"/repos/{REPO}/pulls/1": pull()},
    }


def draft_pull():
    """A draft pull request, which must never be scanned."""
    return {"number": 2, "state": "open", "draft": True, "assignees": []}


def marker_comment(login, assigned_at, stage, posted_at):
    """A reminder comment the bot itself posted."""
    body = (
        f'<!-- praxis-review-reminder {{"assigned_at":"{assigned_at}",'
        f'"login":"{login}","stage":{stage}}} -->'
    )
    return {"body": body, "created_at": posted_at, "user": {"login": BOT, "type": "Bot"}}


if __name__ == "__main__":
    unittest.main()
