"""Project field resolution, no-op avoidance, and write restrictions."""

import unittest

from ..api import ApiError
from ..project import Fields, Item, Writer, items, resolve
from .fakes import AWAITING_ID, OLDEST_ID, PROJECT_ID, FakeApi, item_node

REPO = "praxis-proxy/praxis"


class Resolution(unittest.TestCase):
    def test_resolves_both_field_ids(self):
        fields = resolve(FakeApi(), "praxis-proxy", 13)

        self.assertEqual(fields.project_id, PROJECT_ID, "the project id is resolved")
        self.assertEqual(fields.awaiting_id, AWAITING_ID, "the text field is resolved")
        self.assertEqual(fields.oldest_id, OLDEST_ID, "the number field is resolved")

    def test_rejects_a_missing_field(self):
        api = FakeApi(fields=[{"id": "x", "name": "Status", "dataType": "TEXT"}])

        with self.assertRaises(ApiError) as caught:
            resolve(api, "praxis-proxy", 13)

        self.assertIn(
            "does not exist", str(caught.exception), "the missing field is named"
        )

    def test_rejects_a_field_of_the_wrong_type(self):
        api = FakeApi(
            fields=[
                {"id": AWAITING_ID, "name": "Awaiting response from", "dataType": "TEXT"},
                {
                    "id": OLDEST_ID,
                    "name": "Oldest outstanding response (days)",
                    "dataType": "TEXT",
                },
            ]
        )

        with self.assertRaises(ApiError) as caught:
            resolve(api, "praxis-proxy", 13)

        self.assertIn(
            "expected NUMBER", str(caught.exception), "the type mismatch is reported"
        )

    def test_rejects_a_missing_project(self):
        with self.assertRaises(ApiError):
            resolve(FakeApi(project_id=None), "praxis-proxy", 13)


class Items(unittest.TestCase):
    def test_keeps_only_pull_requests_in_this_repository(self):
        api = FakeApi(
            item_pages=[
                [
                    item_node("i1", 1, REPO, awaiting="ada", oldest=4),
                    item_node("i2", 2, "praxis-proxy/ai"),
                    {"id": "i3", "content": {}},
                ]
            ]
        )

        found = items(api, "praxis-proxy", 13, REPO)

        self.assertEqual([item.number for item in found], [1], "other repos are ignored")
        self.assertEqual(found[0].awaiting, "ada", "the current text is read")
        self.assertEqual(found[0].oldest, 4, "the current number is read")

    def test_follows_every_page(self):
        api = FakeApi(
            item_pages=[[item_node("i1", 1, REPO)], [item_node("i2", 2, REPO)]]
        )

        found = items(api, "praxis-proxy", 13, REPO)

        self.assertEqual(
            [item.number for item in found], [1, 2], "pagination must be followed"
        )

    def test_reads_an_unset_field_as_empty(self):
        api = FakeApi(item_pages=[[item_node("i1", 1, REPO)]])

        found = items(api, "praxis-proxy", 13, REPO)

        self.assertEqual(found[0].awaiting, "", "an unset text field reads as empty")
        self.assertIsNone(found[0].oldest, "an unset number field reads as None")


class Writes(unittest.TestCase):
    def test_sets_both_fields(self):
        api = FakeApi()
        writer = Writer(api, fields(), enabled=True, repository=REPO)

        changes = writer.apply(item(), "ada, grace", 4)

        self.assertEqual(len(changes), 2, f"both fields change, got {changes}")
        self.assertEqual(
            [name for name, _ in api.mutations],
            ["update", "update"],
            "both writes are applied",
        )

    def test_skips_values_already_correct(self):
        api = FakeApi()
        writer = Writer(api, fields(), enabled=True, repository=REPO)

        changes = writer.apply(item(awaiting="ada", oldest=4), "ada", 4)

        self.assertEqual(changes, [], "an unchanged item needs no write")
        self.assertEqual(api.mutations, [], "no mutation is sent for a no-op")

    def test_treats_an_integer_and_float_as_equal(self):
        api = FakeApi()
        writer = Writer(api, fields(), enabled=True, repository=REPO)

        writer.apply(item(awaiting="ada", oldest=4.0), "ada", 4)

        self.assertEqual(api.mutations, [], "4 and 4.0 are the same number")

    def test_clears_both_fields(self):
        api = FakeApi()
        writer = Writer(api, fields(), enabled=True, repository=REPO)

        changes = writer.apply(item(awaiting="ada", oldest=4), "", None)

        self.assertEqual(
            [name for name, _ in api.mutations],
            ["clear", "clear"],
            f"both fields are cleared, got {changes}",
        )

    def test_reports_without_writing_when_disabled(self):
        api = FakeApi()
        writer = Writer(api, fields(), enabled=False, repository=REPO)

        changes = writer.apply(item(), "ada", 4)

        self.assertEqual(len(changes), 2, "a dry run still reports the changes")
        self.assertEqual(api.mutations, [], "a dry run must not mutate anything")

    def test_refuses_a_field_it_does_not_own(self):
        writer = Writer(FakeApi(), fields(), enabled=True, repository=REPO)

        with self.assertRaises(ApiError):
            writer._write("i1", "PVTF_status", {"text": "Done"})

    def test_refuses_an_item_from_another_repository(self):
        api = FakeApi()
        writer = Writer(api, fields(), enabled=True, repository=REPO)

        foreign = item(awaiting="bob", oldest=9, repository="praxis-proxy/ai")

        with self.assertRaises(ApiError) as caught:
            writer.apply(foreign, "", None)

        self.assertIn(
            "praxis-proxy/ai", str(caught.exception), "the foreign item is named"
        )
        self.assertEqual(api.mutations, [], "nothing is written before the refusal")

    def test_only_ever_names_the_resolved_project_and_fields(self):
        api = FakeApi()
        writer = Writer(api, fields(), enabled=True, repository=REPO)

        writer.apply(item(), "ada", 4)
        writer.apply(item(awaiting="ada", oldest=4), "", None)

        for name, variables in api.mutations:
            self.assertEqual(
                variables["project"],
                PROJECT_ID,
                f"{name} must target only the resolved project",
            )
            self.assertIn(
                variables["field"],
                (AWAITING_ID, OLDEST_ID),
                f"{name} must target only the two owned fields",
            )


# ---------------------------------------------------------------------------
# Test Utilities
# ---------------------------------------------------------------------------


def fields():
    """The validated identifiers a writer is allowed to use."""
    return Fields(project_id=PROJECT_ID, awaiting_id=AWAITING_ID, oldest_id=OLDEST_ID)


def item(awaiting="", oldest=None, repository=REPO):
    """A project item with the given current field values."""
    return Item(
        number=1,
        repository=repository,
        item_id="i1",
        awaiting=awaiting,
        oldest=oldest,
    )


if __name__ == "__main__":
    unittest.main()
