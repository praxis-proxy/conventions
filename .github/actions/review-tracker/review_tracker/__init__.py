"""Initial-review response tracking and overdue reminders for pull requests.

Tracks which current assignees of an open, ready pull request have not yet
submitted an initial review, how long each has been waiting, and when they
are due a reminder. Reads everything through the GitHub API; no pull request
code is ever checked out or executed.
"""
