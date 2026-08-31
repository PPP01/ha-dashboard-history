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
    description: str = ""  # what a person wrote about it, if anyone did


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

    def write_snapshot(
        self, key: str, text: str, message: str, meta: str | None = None
    ) -> str | None:
        """Record a state. Returns the revision, or None if nothing changed.

        `meta` carries what the dashboard *is*, as opposed to what is on
        it: title, icon, visibility. It travels in the same commit,
        because a dashboard brought back with the right cards under the
        wrong name is only half brought back.
        """
        with self._lock:
            self._ensure()
            target = self.path / f"{key}.yaml"
            meta_target = self.path / "meta" / f"{key}.yaml"

            # Compare against the last commit, never against the file on
            # disk. If an earlier run wrote the file but did not get to
            # commit it, the file already carries the new text - comparing
            # against it would drop that state from the history for good,
            # and silently, which is the one failure this project must not
            # have. Comparing against HEAD repairs such a gap by itself.
            if self.read_at(key, "HEAD") == text and (
                meta is None or self.read_meta_at(key, "HEAD") == meta
            ):
                # The repository is already right. Keep the working tree
                # honest anyway: the README invites people to look inside.
                self._write_if_stale(target, text)
                if meta is not None:
                    self._write_if_stale(meta_target, meta)
                return None

            paths = [target]
            self._write_file(target, text)
            if meta is not None:
                self._write_file(meta_target, meta)
                paths.append(meta_target)
            porcelain.add(str(self.path), [str(path) for path in paths])
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
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f"{target.name}.tmp")
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, target)

    @classmethod
    def _write_if_stale(cls, target: Path, text: str) -> None:
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            cls._write_file(target, text)

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
            paths = [self.path / f"{key}.yaml"]
            if self.read_meta_at(key, "HEAD") is not None:
                paths.append(self.path / "meta" / f"{key}.yaml")
            porcelain.remove(str(self.path), [str(path) for path in paths])
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

    def set_description(self, revision: str, text: str) -> bool:
        """Attach a person's own words to a recorded change.

        Stored as a git note on `refs/notes/commits`, which leaves the
        commit itself untouched. That is the point rather than a detail:
        rewriting a commit message rewrites the commit, and with it every
        descendant - invalidating exactly the revisions this tool hands
        out in panel responses, service results and error messages.

        An empty text removes the note instead of storing a blank one; a
        blank one would leave a row with an invisible headline and the
        automatic message hidden beneath it.

        Returns False when the revision is unknown. dulwich raises
        KeyError for an unknown object, so it has to be resolved first -
        and refusing is right anyway, since a note filed against nothing
        is a note nobody ever finds again.
        """
        with self._lock:
            self._ensure()
            repo = self._repo()
            if repo is None:
                return False
            full = self._resolve(repo, revision)
            if full is None:
                return False
            body = text.strip()
            if body:
                porcelain.notes_add(
                    str(self.path),
                    full.encode(),
                    body.encode("utf-8"),
                    author=_IDENTITY,
                    committer=_IDENTITY,
                )
            else:
                # Measured: a commit without a note returns None here
                # rather than raising, so this needs no guard of its own.
                porcelain.notes_remove(
                    str(self.path),
                    full.encode(),
                    author=_IDENTITY,
                    committer=_IDENTITY,
                )
            return True

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
        notes = self.descriptions()
        try:
            # Both paths: a rename touches only the metadata, and a change
            # that is recorded but never shown is the worst of both.
            walker = repo.get_walker(
                paths=[f"{key}.yaml".encode(), f"meta/{key}.yaml".encode()],
                max_entries=limit,
            )
            return [
                Change(
                    revision=_as_text(entry.commit.id),
                    timestamp=entry.commit.commit_time,
                    message=entry.commit.message.decode("utf-8").strip(),
                    description=notes.get(_as_text(entry.commit.id), ""),
                )
                for entry in walker
            ]
        except KeyError:
            # No HEAD yet: an empty repository has no history to walk.
            return []

    def descriptions(self) -> dict[str, str]:
        """Every description, by revision.

        One pass over the notes rather than one lookup per change: the
        panel asks for fifty changes at a time.
        """
        if not (self.path / ".git").exists():
            return {}
        # Measured: a repository that never held a note answers with an
        # empty list rather than raising, so this needs no guard.
        return {
            _as_text(sha): text.decode("utf-8")
            for sha, text in porcelain.notes_list(str(self.path))
        }

    def previous_change(self, key: str, revision: str) -> str | None:
        """The state of one dashboard just before one of its changes.

        Deliberately not the commit's parent. Another dashboard's commit
        can sit in between, and its state is no state of this dashboard
        at all - reading it would answer a question nobody asked.
        """
        full = self.resolve(revision)
        if full is None:
            return None
        found = False
        for change in self.list_changes(key, limit=1000):
            if found:
                return change.revision
            found = change.revision == full
        return None

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
        return self._read(f"{key}.yaml", revision)

    def read_meta_at(self, key: str, revision: str) -> str | None:
        """What a dashboard *was* at a revision: title, icon, visibility."""
        return self._read(f"meta/{key}.yaml", revision)

    def _read(self, path: str, revision: str) -> str | None:
        repo = self._repo()
        if repo is None:
            return None
        resolved = self._resolve(repo, revision)
        if resolved is None:
            return None
        try:
            tree = repo[repo[resolved.encode()].tree]
            _, blob_id = tree.lookup_path(repo.get_object, path.encode())
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

    def list_all_dashboards(self, limit: int = 1000) -> list[str]:
        """Every dashboard the history has ever held, deleted ones included.

        The deleted ones are the whole point of the method: a dashboard
        that is gone is exactly the one somebody comes looking for, and it
        is no longer in HEAD to be found.
        """
        repo = self._repo()
        if repo is None or self._resolve(repo, "HEAD") is None:
            return []
        names: set[str] = set()
        for entry in repo.get_walker(max_entries=limit):
            for change in entry.changes():
                for one in change if isinstance(change, list) else [change]:
                    for side in (one.old, one.new):
                        path = getattr(side, "path", None)
                        # Top level only: meta/<key>.yaml is not a dashboard.
                        if path and b"/" not in path and path.endswith(b".yaml"):
                            names.add(path.decode()[: -len(".yaml")])
        return sorted(names)

    def last_known_meta(self, key: str, limit: int = 5) -> str | None:
        """The most recent metadata recorded for a dashboard.

        For a deleted one that is the state just before the deletion -
        which is the name and icon it should carry when it comes back.
        """
        for change in self.list_changes(key, limit=limit):
            text = self.read_meta_at(key, change.revision)
            if text is not None:
                return text
        return None

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
