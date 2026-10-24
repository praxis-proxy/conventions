"""Test utilities: an in-memory stand-in for the GitHub API."""

from ..api import ApiError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AWAITING_ID = "PVTF_awaiting"
OLDEST_ID = "PVTF_oldest"
PROJECT_ID = "PVT_project13"

DEFAULT_FIELDS = (
    {"id": AWAITING_ID, "name": "Awaiting response from", "dataType": "TEXT"},
    {
        "id": OLDEST_ID,
        "name": "Oldest outstanding response (days)",
        "dataType": "NUMBER",
    },
    {"id": "PVTF_status", "name": "Status", "dataType": "SINGLE_SELECT"},
)


class FakeApi:
    """Records every mutation and comment it is asked to make."""

    def __init__(
        self,
        fields=DEFAULT_FIELDS,
        item_pages=None,
        pages=None,
        project_id=PROJECT_ID,
        rest=None,
        fail=(),
    ):
        """Builds a double; `fail` makes any path containing it raise."""
        self.mutations = []
        self.posted = []
        self.requests = []
        self._fail = tuple(fail)
        self._fields = list(fields)
        self._item_pages = [list(page) for page in (item_pages or [[]])]
        self._pages = dict(pages or {})
        self._project_id = project_id
        self._rest = dict(rest or {})

    def graphql(self, query, variables):
        """Answers the two queries and records everything else as a mutation."""
        if "fields(first" in query:
            return {
                "organization": {
                    "projectV2": {
                        "id": self._project_id,
                        "fields": {"nodes": self._fields},
                    }
                }
            }

        if "items(first" in query:
            return self._items_page(variables.get("cursor"))

        name = "update" if "updateProjectV2ItemFieldValue" in query else "clear"
        self.mutations.append((name, variables))
        return {}

    def paginate(self, path):
        """Returns the canned collection registered for `path`."""
        self.requests.append(("GET", path))
        self._maybe_fail(path)
        return list(self._pages.get(path, []))

    def rest(self, method, path, payload=None):
        """Returns the canned body for `path`, recording any comment posted."""
        self.requests.append((method, path))
        self._maybe_fail(path)

        if method == "POST":
            self.posted.append((path, payload))
            return {}

        return dict(self._rest.get(path, {}))

    def _items_page(self, cursor):
        """One page of project items, keyed by an integer cursor."""
        index = 0 if cursor is None else int(cursor)
        more = index + 1 < len(self._item_pages)

        return {
            "organization": {
                "projectV2": {
                    "items": {
                        "pageInfo": {
                            "hasNextPage": more,
                            "endCursor": str(index + 1) if more else None,
                        },
                        "nodes": self._item_pages[index],
                    }
                }
            }
        }

    def _maybe_fail(self, path):
        """Raises when this path was registered as a simulated failure."""
        for marker in self._fail:
            if marker in path:
                raise ApiError(f"simulated failure for {path}")


def item_node(item_id, number, repository, awaiting=None, oldest=None):
    """A project item node for a pull request, with its current field values."""
    return {
        "id": item_id,
        "content": {"number": number, "repository": {"nameWithOwner": repository}},
        "awaiting": None if awaiting is None else {"text": awaiting},
        "oldest": None if oldest is None else {"number": oldest},
    }
