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

    def mark_deleted(self, key: str, message: str) -> str | None:
        """Record that a dashboard is gone. Returns the revision, or None.

        The file leaves the tree, exactly as a deleted file does in git:
        every earlier state stays readable by its revision, and the
        deletion shows up in that dashboard's own history rather than
        nowhere at all. Keeping the file instead would need an empty
        commit, and an empty commit touches no path - it would never
        appear in the history of the dashboard it is about.

        It also draws a line. Should a *different* dashboard later take
        the same url_path, it starts a fresh chapter instead of being
        compared against a stranger.
        """
        with self._lock:
            self._ensure()
            if self.read_at(key, "HEAD") is None:
                # Never recorded, or already marked deleted.
                return None
            porcelain.remove(str(self.path), [str(self.path / f"{key}.yaml")])
            revision = porcelain.commit(
                str(self.path),
                message=message.encode("utf-8"),
                author=_IDENTITY,
                committer=_IDENTITY,
            )
            return _as_text(revision)

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

    def resolve(self, revision: str) -> str | None:
        """Turn a revision into a full commit hash, or None if unknown.

        Accepts what a person is actually likely to paste: a full hash, a
        ref such as HEAD, an annotated tag, or an abbreviated hash of the
        kind `git log --oneline` prints. dulwich resolves none of the
        abbreviated forms by itself, and the abbreviated form is exactly
        what anyone who looks into the repository will copy out of it.
        """
        repo = self._repo()
        return None if repo is None else self._resolve(repo, revision)

    @staticmethod
    def _resolve(repo: Repo, revision: str) -> str | None:
        name = revision.strip().encode()
        if not name:
            return None
        sha = None
        try:
            sha = repo[name].id
        except (KeyError, ValueError):
            # git itself refuses fewer than four characters; so do we.
            if 4 <= len(name) < 40:
                lowered = name.lower()
                if all(char in b"0123456789abcdef" for char in lowered):
                    matches = list(repo.object_store.iter_prefix(lowered))
                    # An ambiguous prefix is refused rather than guessed:
                    # picking one of two commits would be worse than
                    # saying it is not clear which was meant.
                    if len(matches) == 1:
                        sha = matches[0]
        if sha is None:
            return None
        obj = repo[sha]
        while obj.type_name == b"tag":
            # An annotated tag points at the commit; that is what is wanted.
            obj = repo[obj.object[1]]
        return _as_text(obj.id)

    def read_at(self, key: str, revision: str) -> str | None:
        """The text of one dashboard at one revision, or None if absent.

        None means two different things - the revision is unknown, or the
        dashboard did not exist in it. Callers that report to a person
        must tell those apart with `resolve`; conflating them sends people
        looking for a fault in their dashboard instead of in their input.
        """
        repo = self._repo()
        if repo is None:
            return None
        resolved = self._resolve(repo, revision)
        if resolved is None:
            return None
        try:
            tree = repo[repo[resolved.encode()].tree]
            _, blob_id = tree.lookup_path(repo.get_object, f"{key}.yaml".encode())
        except KeyError:
            return None
        return repo[blob_id].data.decode("utf-8")

    def list_dashboards(self) -> list[str]:
        """Every dashboard the history currently tracks."""
        repo = self._repo()
        if repo is None:
            return []
        head = self._resolve(repo, "HEAD")
        if head is None:
            return []
        tree = repo[repo[head.encode()].tree]
        return sorted(
            entry.path.decode()[: -len(".yaml")]
            for entry in tree.items()
            if entry.path.endswith(b".yaml")
        )

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
