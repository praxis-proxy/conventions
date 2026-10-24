"""GitHub REST and GraphQL access with pagination, retries, and backoff.

The token is only ever sent as a request header. It is never placed in a URL
and never appears in an error message, so nothing here can leak it into a
workflow log or job summary.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_ROOT = "https://api.github.com"
BACKOFF_SECONDS = 2.0
MAX_ATTEMPTS = 5
MAX_SLEEP_SECONDS = 60.0  # longest single backoff, so a run cannot hang
PER_PAGE = 100
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
USER_AGENT = "praxis-review-tracker"


class ApiError(RuntimeError):
    """A GitHub API call that did not succeed after every retry."""


class GitHubApi:
    """Authenticated client for the REST and GraphQL GitHub APIs."""

    def __init__(self, token, root=API_ROOT, sleep=time.sleep):
        """Builds a client. `sleep` is injectable so tests never actually wait."""
        self._root = root.rstrip("/")
        self._sleep = sleep
        self._token = token

    def graphql(self, query, variables):
        """Runs a GraphQL document and returns its `data`, raising on errors."""
        _, body = self._send(
            "POST", f"{self._root}/graphql", {"query": query, "variables": variables}
        )

        errors = body.get("errors")
        if errors:
            raise ApiError(f"graphql: {json.dumps(errors)}")

        return body.get("data") or {}

    def paginate(self, path):
        """Returns every item of a REST collection, following `Link` headers."""
        joiner = "&" if "?" in path else "?"
        url = f"{self._root}{path}{joiner}per_page={PER_PAGE}"

        items = []
        while url:
            headers, body = self._send("GET", url, None)
            if not isinstance(body, list):
                raise ApiError(f"expected a list of results from {path}")
            items.extend(body)
            url = _next_link(headers.get("link", ""))

        return items

    def rest(self, method, path, payload=None):
        """Runs a single REST call and returns the decoded response body."""
        _, body = self._send(method, f"{self._root}{path}", payload)
        return body

    def _send(self, method, url, payload):
        """Sends one request, retrying transient failures and rate limits."""
        data = None if payload is None else json.dumps(payload).encode()
        failure = ""

        for attempt in range(1, MAX_ATTEMPTS + 1):
            request = urllib.request.Request(url, data=data, method=method)
            request.add_header("accept", "application/vnd.github+json")
            request.add_header("authorization", f"Bearer {self._token}")
            request.add_header("user-agent", USER_AGENT)
            if data is not None:
                request.add_header("content-type", "application/json")

            try:
                with urllib.request.urlopen(request) as response:
                    raw = response.read()
                    headers = _lower(response.headers)
                    return headers, (json.loads(raw) if raw else {})
            except urllib.error.HTTPError as error:
                headers = _lower(error.headers)
                failure = f"HTTP {error.code} on {method} {url}"
                if error.code not in RETRY_STATUSES and not _rate_limited(
                    error.code, headers
                ):
                    raise ApiError(failure) from None
                self._sleep(_retry_delay(headers, attempt))
            except urllib.error.URLError as error:
                failure = f"{type(error).__name__} on {method} {url}"
                self._sleep(min(BACKOFF_SECONDS * attempt, MAX_SLEEP_SECONDS))

        raise ApiError(f"{failure}; gave up after {MAX_ATTEMPTS} attempts")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _lower(headers):
    """Response headers keyed by lowercase name."""
    if headers is None:
        return {}
    return {key.lower(): value for key, value in headers.items()}


def _next_link(value):
    """The `rel="next"` URL from a `Link` header, or None when there is none."""
    for part in value.split(","):
        pieces = part.split(";")
        if len(pieces) >= 2 and 'rel="next"' in part:
            return pieces[0].strip().strip("<>")
    return None


def _rate_limited(status, headers):
    """True when a 403 is a primary or secondary rate limit rather than a denial."""
    if status != 403:
        return False
    return "retry-after" in headers or headers.get("x-ratelimit-remaining") == "0"


def _retry_delay(headers, attempt):
    """Seconds to wait before retrying, honoring the rate-limit headers."""
    after = headers.get("retry-after", "").strip()
    if after.isdigit():
        return min(float(after), MAX_SLEEP_SECONDS)

    reset = headers.get("x-ratelimit-reset", "").strip()
    if reset.isdigit() and headers.get("x-ratelimit-remaining") == "0":
        return min(max(float(reset) - time.time(), 0.0), MAX_SLEEP_SECONDS)

    return min(BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_SLEEP_SECONDS)
