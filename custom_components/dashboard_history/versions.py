"""Version numbers for the history: reading, ordering, counting up.

Home-Assistant-free on purpose. This is a small calculation that can be
wrong in a way nobody notices for months - `v1.10.0` sorting below
`v1.9.0` is the classic - so it lives where plain pytest reaches it,
rather than in the panel. Same rule as the wording in `analyze.py`.

A version is an annotated git tag named `<key>/v<major>.<minor>.<patch>`.
The dashboard key is part of the name because git tags share a single
namespace: without it, only one dashboard in the whole installation
could ever have a `v1.0.0`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Deliberately strict: three plain numbers, no leading zeros, no suffix.
# Anything else is somebody's hand-made tag. Those stay visible, but they
# must never shift the numbering - a tag called `v2.0.0-beta` deciding
# that the next version is 2.0.1 would be a surprise nobody can undo.
_NUMBERS = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

LEVELS = ("patch", "minor", "major")


def version_name(key: str, parts: tuple[int, int, int]) -> str:
    """The tag name one dashboard's version carries."""
    major, minor, patch = parts
    return f"{key}/v{major}.{minor}.{patch}"


def parse(key: str, name: str) -> tuple[int, int, int] | None:
    """The three numbers in a tag name, or None if it is not this one's."""
    prefix = f"{key}/"
    if not name.startswith(prefix):
        return None
    match = _NUMBERS.match(name[len(prefix) :])
    if match is None:
        return None
    major, minor, patch = match.groups()
    return (int(major), int(minor), int(patch))


def latest(key: str, names: Iterable[str]) -> tuple[int, int, int] | None:
    """The highest version of one dashboard, or None if it has none.

    Compared as numbers rather than as text. Tuples of ints order the way
    versions are meant to; the strings they came from do not.
    """
    found = [
        parsed for name in names if (parsed := parse(key, name)) is not None
    ]
    return max(found) if found else None


def by_number(key: str, versions: Iterable) -> list:
    """Versions by number, highest first; names that will not parse last.

    Takes anything carrying a `.name` - the store's `Version`, or a
    stand-in in a test. This module knows numbers, not storage.

    Ordered by number rather than by the time the tag was made. The store
    can only know the time, and the two differ as soon as somebody goes
    back and marks an older state: the newer tag then carries the lower
    number, and ordering by time would put it on top of one that contains
    it. A name that will not parse sorts last rather than pretending to
    be version zero.
    """
    return sorted(
        versions, key=lambda v: parse(key, v.name) or (-1, -1, -1), reverse=True
    )


def bump(parts: tuple[int, int, int], level: str) -> tuple[int, int, int]:
    """The next version at one level. Everything below it resets to zero."""
    major, minor, patch = parts
    if level == "major":
        return (major + 1, 0, 0)
    if level == "minor":
        return (major, minor + 1, 0)
    if level == "patch":
        return (major, minor, patch + 1)
    raise ValueError(f"unknown level: {level}")


def candidates(key: str, names: Iterable[str]) -> dict[str, str | None]:
    """The three names the three buttons carry, and the current one.

    Counting always starts from the **highest existing** version, even
    after somebody has gone back to an older one. That keeps the numbers
    monotone, so a new version can never collide with one that is already
    there - and a collision would be a refusal in the middle of a dialog.

    Without a predecessor the count starts at 0.0.0, which puts `0.0.1`,
    `0.1.0` and `1.0.0` on the three buttons. Whoever wants a proper first
    release finds it one click away rather than having to reach for it.
    """
    current = latest(key, names)
    base = current or (0, 0, 0)
    found: dict[str, str | None] = {
        level: version_name(key, bump(base, level)) for level in LEVELS
    }
    found["current"] = version_name(key, current) if current else None
    return found
