"""Project field resolution and tightly scoped field writes.

Every identifier is resolved through the API and validated before use, and
the writer physically cannot name a project other than the one it resolved
or a field other than the two it owns.
"""

from __future__ import annotations

from dataclasses import dataclass

from .api import ApiError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AWAITING_FIELD = "Awaiting response from"
AWAITING_TYPE = "TEXT"
DEFAULT_PROJECT = 13
OLDEST_FIELD = "Oldest outstanding response (days)"
OLDEST_TYPE = "NUMBER"
NUMBER_EPSILON = 1e-9

CLEAR_MUTATION = """
mutation($project: ID!, $item: ID!, $field: ID!) {
  clearProjectV2ItemFieldValue(
    input: {projectId: $project, itemId: $item, fieldId: $field}
  ) { projectV2Item { id } }
}
"""

FIELDS_QUERY = """
query($org: String!, $number: Int!) {
  organization(login: $org) {
    projectV2(number: $number) {
      id
      fields(first: 100) {
        nodes { ... on ProjectV2FieldCommon { id name dataType } }
      }
    }
  }
}
"""

ITEMS_QUERY = """
query($org: String!, $number: Int!, $cursor: String) {
  organization(login: $org) {
    projectV2(number: $number) {
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          content { ... on PullRequest { number repository { nameWithOwner } } }
          awaiting: fieldValueByName(name: "Awaiting response from") {
            ... on ProjectV2ItemFieldTextValue { text }
          }
          oldest: fieldValueByName(name: "Oldest outstanding response (days)") {
            ... on ProjectV2ItemFieldNumberValue { number }
          }
        }
      }
    }
  }
}
"""

UPDATE_MUTATION = """
mutation($project: ID!, $item: ID!, $field: ID!, $value: ProjectV2FieldValue!) {
  updateProjectV2ItemFieldValue(
    input: {projectId: $project, itemId: $item, fieldId: $field, value: $value}
  ) { projectV2Item { id } }
}
"""


@dataclass(frozen=True)
class Fields:
    """The validated identifiers this tracker is allowed to write."""

    project_id: str
    awaiting_id: str
    oldest_id: str


@dataclass(frozen=True)
class Item:
    """A project item standing for a pull request, with its current values."""

    number: int
    item_id: str
    awaiting: str
    oldest: object


class Writer:
    """Applies field changes, refusing anything outside the two allowed fields."""

    def __init__(self, api, fields, enabled):
        """Builds a writer; with `enabled` false it reports without mutating."""
        self._api = api
        self._enabled = enabled
        self._fields = fields

    def apply(self, item, awaiting, oldest):
        """Writes both fields for one item, skipping values already correct.

        Returns a description of each change, whether or not it was applied,
        so a dry run reports exactly what a live run would do.
        """
        changes = []

        if (item.awaiting or "") != (awaiting or ""):
            changes.append(self._text(item.item_id, awaiting))

        if _number_differs(item.oldest, oldest):
            changes.append(self._number(item.item_id, oldest))

        return changes

    def _clear(self, item_id, field_id):
        """Clears one field after checking it is one this tracker owns."""
        self._guard(field_id)
        if self._enabled:
            self._api.graphql(
                CLEAR_MUTATION,
                {
                    "project": self._fields.project_id,
                    "item": item_id,
                    "field": field_id,
                },
            )

    def _guard(self, field_id):
        """Refuses to touch any field other than the two this tracker owns."""
        if field_id not in (self._fields.awaiting_id, self._fields.oldest_id):
            raise ApiError(f"refusing to write project field {field_id}")

    def _number(self, item_id, value):
        """Sets or clears the oldest-outstanding field."""
        field_id = self._fields.oldest_id
        if value is None:
            self._clear(item_id, field_id)
            return f'"{OLDEST_FIELD}" cleared'

        self._write(item_id, field_id, {"number": value})
        return f'"{OLDEST_FIELD}" -> {value}'

    def _text(self, item_id, value):
        """Sets or clears the awaiting-response field."""
        field_id = self._fields.awaiting_id
        if not value:
            self._clear(item_id, field_id)
            return f'"{AWAITING_FIELD}" cleared'

        self._write(item_id, field_id, {"text": value})
        return f'"{AWAITING_FIELD}" -> "{value}"'

    def _write(self, item_id, field_id, value):
        """Sets one field after checking it is one this tracker owns."""
        self._guard(field_id)
        if self._enabled:
            self._api.graphql(
                UPDATE_MUTATION,
                {
                    "project": self._fields.project_id,
                    "item": item_id,
                    "field": field_id,
                    "value": value,
                },
            )


def items(api, organization, number, repository):
    """Every project item for a pull request in `repository`, with its values."""
    found = []
    cursor = None

    while True:
        data = api.graphql(
            ITEMS_QUERY, {"org": organization, "number": number, "cursor": cursor}
        )
        page = ((data.get("organization") or {}).get("projectV2") or {}).get(
            "items"
        ) or {}

        for node in page.get("nodes") or []:
            content = node.get("content") or {}
            owner = (content.get("repository") or {}).get("nameWithOwner")
            if owner != repository or content.get("number") is None:
                continue

            found.append(
                Item(
                    number=content["number"],
                    item_id=node["id"],
                    awaiting=(node.get("awaiting") or {}).get("text") or "",
                    oldest=(node.get("oldest") or {}).get("number"),
                )
            )

        info = page.get("pageInfo") or {}
        cursor = info.get("endCursor")
        if not info.get("hasNextPage") or not cursor:
            return found


def resolve(api, organization, number):
    """Looks up a project and validates both field names and their types."""
    data = api.graphql(FIELDS_QUERY, {"org": organization, "number": number})
    project = (data.get("organization") or {}).get("projectV2") or {}

    project_id = project.get("id")
    if not project_id:
        raise ApiError(f"project #{number} was not found in {organization}")

    nodes = (project.get("fields") or {}).get("nodes") or []
    by_name = {node.get("name"): node for node in nodes if node}

    return Fields(
        project_id=project_id,
        awaiting_id=_field(by_name, AWAITING_FIELD, AWAITING_TYPE),
        oldest_id=_field(by_name, OLDEST_FIELD, OLDEST_TYPE),
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _field(by_name, name, expected):
    """The id of field `name`, failing when it is missing or the wrong type."""
    node = by_name.get(name)
    if node is None:
        raise ApiError(f'project field "{name}" does not exist')

    actual = node.get("dataType")
    if actual != expected:
        raise ApiError(f'project field "{name}" is {actual}, expected {expected}')

    return node["id"]


def _number_differs(current, desired):
    """True when a number field needs rewriting, treating 3 and 3.0 as equal."""
    if current is None or desired is None:
        return (current is None) != (desired is None)

    return abs(float(current) - float(desired)) > NUMBER_EPSILON
