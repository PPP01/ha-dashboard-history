"""The history store: a git repository the integration owns.

git is used as a storage engine, not as a user-facing tool. It gives
deduplication, compression, history and tags for free — reimplementing
those would be the classic mistake for a feature that *is* version
control.

The repository is created and maintained by this integration alone. It
never shells out to a git binary: whether one exists differs between
Home Assistant OS, Container, Core and Supervised installations.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo

_LOGGER = logging.getLogger(__name__)

_IDENTITY = b"Dashboard History <dashboard-history@localhost>"


@dataclass(frozen=True)
class Change:
    """One recorded state of one dashboard."""

    revision: str
    timestamp: int
    message: str


@dataclass(frozen=True)
class Version:
    """A named point in the history. It groups, it never squashes."""

    name: str
    revision: str
    title: str
    description: str


def _as_text(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


class HistoryStore:
    """Stores dashboard states and reads them back."""

    def __init__(self, path) -> None:
        self.path = Path(path)
        # dulwich takes an exclusive lock on the git index while it writes.
        # Two dashboards saved in the same moment run in two executor
        # threads; measured, eight parallel commits let exactly one through
        # and the other seven raised FileLocked. Writes are serialised here
        # rather than left to chance.
        self._lock = threading.Lock()

    # -- writing -------------------------------------------------------

    def ensure(self) -> None:
        """Create the repository if it does not exist yet."""
        with self._lock:
            self._ensure()

    def _ensure(self) -> None:
        """Same, for callers that already hold the lock."""
        if (self.path / ".git").exists():
            return
        self.path.mkdir(parents=True, exist_ok=True)
        porcelain.init(str(self.path))
        _LOGGER.info("Created dashboard history repository at %s", self.path)

    def write_snapshot(self, key: str, text: str, message: str) -> str | None:
        """Record a state. Returns the revision, or None if nothing changed."""
        with self._lock:
            self._ensure()
            target = self.path / f"{key}.yaml"

            # Compare against the last commit, never against the file on
            # disk. If an earlier run wrote the file but did not get to
            # commit it, the file already carries the new text - comparing
            # against it would drop that state from the history for good,
            # and silently, which is the one failure this project must not
            # have. Comparing against HEAD repairs such a gap by itself.
            if self.read_at(key, "HEAD") == text:
                # The repository is already right. Keep the working tree
                # honest anyway: the README invites people to look inside.
                if not target.exists() or target.read_text(encoding="utf-8") != text:
                    self._write_file(target, text)
                return None

            self._write_file(target, text)
            porcelain.add(str(self.path), [str(target)])
            revision = porcelain.commit(
                str(self.path),
                message=message.encode("utf-8"),
                author=_IDENTITY,
                committer=_IDENTITY,
            )
            return _as_text(revision)

    @staticmethod
    def _write_file(target: Path, text: str) -> None:
        """Write through a temporary file.

        An interrupted run must not leave a truncated YAML behind that
        later looks like a real state.
        """
        temp = target.with_name(f"{target.name}.tmp")
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, target)

    def create_version(
        self, name: str, title: str, description: str, revision: str | None = None
    ) -> None:
        """Mark a point in the history with a name, title and description."""
        with self._lock:
            self._ensure()
            self._create_version(name, title, description, revision)

    def _create_version(
        self, name: str, title: str, description: str, revision: str | None
    ) -> None:
        body = f"{title}\n\n{description}".encode("utf-8")
        porcelain.tag_create(
            str(self.path),
            name.encode("utf-8"),
            message=body,
            author=_IDENTITY,
            annotated=True,
            objectish=revision.encode() if revision else b"HEAD",
        )

    # -- reading -------------------------------------------------------

    def _repo(self) -> Repo | None:
        if not (self.path / ".git").exists():
            return None
        return Repo(str(self.path))

    def list_changes(self, key: str, limit: int = 50) -> list[Change]:
        """Every recorded state of one dashboard, newest first."""
        repo = self._repo()
        if repo is None:
            return []
        try:
            walker = repo.get_walker(paths=[f"{key}.yaml".encode()], max_entries=limit)
            return [
                Change(
                    revision=_as_text(entry.commit.id),
                    timestamp=entry.commit.commit_time,
                    message=entry.commit.message.decode("utf-8").strip(),
                )
                for entry in walker
            ]
        except KeyError:
            # No HEAD yet: an empty repository has no history to walk.
            return []

    def read_at(self, key: str, revision: str) -> str | None:
        """The text of one dashboard at one revision, or None if absent."""
        repo = self._repo()
        if repo is None:
            return None
        try:
            tree = repo[repo[revision.encode()].tree]
            _, blob_id = tree.lookup_path(repo.get_object, f"{key}.yaml".encode())
        except KeyError:
            return None
        return repo[blob_id].data.decode("utf-8")

    def list_versions(self) -> list[Version]:
        """Every named point, newest first."""
        repo = self._repo()
        if repo is None:
            return []
        found: list[tuple[int, Version]] = []
        for ref in repo.refs.as_dict(b"refs/tags"):
            tag = repo[repo.refs[b"refs/tags/" + ref]]
            if not hasattr(tag, "object"):
                # A lightweight tag, made by hand. Not ours; skip it rather
                # than crash on the missing fields.
                continue
            message = (tag.message or b"").decode("utf-8")
            title, _, description = message.partition("\n\n")
            found.append(
                (
                    tag.tag_time,
                    Version(
                        name=ref.decode(),
                        revision=_as_text(tag.object[1]),
                        title=title.strip(),
                        description=description.strip(),
                    ),
                )
            )
        # as_dict has no order of its own; the docstring promises one.
        return [version for _, version in sorted(found, key=lambda p: -p[0])]
