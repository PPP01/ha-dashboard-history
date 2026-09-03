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
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from dulwich import porcelain
from dulwich.errors import RefFormatError
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

    def _file_for(self, key: str, *folders: str) -> Path:
        """The file a key names in the store, or a refusal.

        The key comes from Home Assistant's dashboard registry and ends
        up in a file name, so it decides where this class writes.
        Measured before this check existed: a dashboard registered over
        the API under the url_path "../weiter-weg" was recorded to a file
        outside the repository this class owns, where nothing reads it
        back and nothing removes it.

        Asked of the built path, not of the key, and that is the point:
        `keys.is_safe_key` decides one layer up what may become a key at
        all, and this decides the only thing that matters *here* - the
        file stays inside the store. Two independent questions rather
        than the same one asked twice, and this one holds whatever a
        later caller hands in.

        Deliberately not stricter than that. A key with a slash in it
        makes a nested `energie/x.yaml`, which is wrong but is still a
        file this store owns - and one recorded before the key rule
        existed has to stay deletable, or its history is stuck where no
        operation can reach it. Refusing new ones is the key rule's job;
        refusing to write outside the store is this one's.
        """
        base = self.path.joinpath(*folders)
        target = base / f"{key}.yaml"
        root = self.path.resolve()
        resolved = target.resolve()
        if resolved == root or root not in resolved.parents:
            raise ValueError(
                f"dashboard key {key!r} does not name a file in the store"
            )
        return target

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
            target = self._file_for(key)
            meta_target = self._file_for(key, "meta")

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
            paths = [self._file_for(key)]
            if self.read_meta_at(key, "HEAD") is not None:
                paths.append(self._file_for(key, "meta"))
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
        self._refuse_colliding_name(name)
        marked = self._marked_commit(revision)
        body = f"{title}\n\n{description}".encode("utf-8")
        try:
            porcelain.tag_create(
                str(self.path),
                name.encode("utf-8"),
                message=body,
                author=_IDENTITY,
                annotated=True,
                objectish=marked,
            )
        except RefFormatError as err:
            # A name git itself cannot accept - a space in it, `..`, or one
            # of `~^:?*[`. That is the same class of answer as a name that
            # collides with an existing one, so it leaves here as the same
            # kind of exception. Converted *here* on purpose: dulwich's
            # types belong to this module, and RefFormatError inherits
            # straight from Exception - a caller catching ValueError would
            # let it escape as a bare traceback.
            raise ValueError(f"git cannot use that as a version name: {name}") from err

    def _marked_commit(self, revision: str | None) -> bytes:
        """The commit a version is about to be pinned to.

        Resolved here rather than left to `tag_create`, which takes any
        object at all: a blob id makes a tag that reads back as a version
        and can never be returned to - and a version, unlike a
        description, has nothing that deletes it again. Refused as a
        ValueError, the same kind of answer a colliding name gives, so the
        one place that already catches those needs no second branch.
        """
        repo = self._repo()
        found = None if repo is None else self._resolve(repo, revision or "HEAD")
        if found is None:
            raise ValueError(f"unknown revision: {revision or 'HEAD'}")
        return found.encode()

    def _refuse_colliding_name(self, name: str) -> None:
        """Refuse a version name git could not hold beside the others.

        A ref is a file, and a ref namespace is a directory of the same
        path - so `home` and `home/v1.0.0` cannot both exist. Measured on
        dulwich 1.2.14: the attempt raises IsADirectoryError *and* leaves
        a `.lock` file behind, which is a worse thing to hand a person
        than a sentence saying what is in the way.
        """
        repo = self._repo()
        if repo is None:
            return
        existing = {ref.decode() for ref in repo.refs.as_dict(b"refs/tags")}
        if name in existing:
            raise ValueError(f"version already exists: {name}")
        # Every proper prefix that ends at a `/`, not just the first one.
        # A dashboard key may hold a slash - Home Assistant accepts
        # `url_path="dh-slash/check"`, and decision 13 of the design
        # record names a version `<key>/v<major>.<minor>.<patch>` - so the
        # parent that matters for `dh-slash/check/v1.0.0` is
        # `dh-slash/check`, which looking at the first segment alone never
        # sees. The collision it missed then arrived as the raw
        # NotADirectoryError plus the stray `.lock` file this refusal
        # exists to prevent.
        parts = name.split("/")
        for depth in range(1, len(parts)):
            parent = "/".join(parts[:depth])
            if parent in existing:
                raise ValueError(
                    f"cannot create {name}: a version named {parent} is in the way"
                )
        below = sorted(one for one in existing if one.startswith(f"{name}/"))
        if below:
            raise ValueError(
                f"cannot create {name}: {below[0]} is in the way"
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

    def forget(self, key: str) -> int:
        """Remove a dashboard's history for good. Returns commits removed.

        The only irreversible operation here, in a tool built to stop
        things disappearing. It exists because a deleted dashboard stays
        in the list forever: delete one every few months and the list is
        mostly gravestones.

        git can only really remove something by rewriting history, so
        every revision from the first affected commit onwards changes.
        That is not a detail to gloss over - two things hang off revisions
        and would vanish silently:

        * **Descriptions** are git notes, keyed by commit sha. They are
          read before the rewrite and written back onto the new commits.
          A description on a commit that disappears goes with it: it
          described a state that no longer exists, and a description on
          the wrong state is worse than none.
        * **Named versions** are tags pointing at a commit. This
          dashboard's own - every tag under `<key>/`, which is where
          decision 13 of the design record puts them - are deleted with
          it: a version belongs to one dashboard, and carrying it onto a
          surviving ancestor would leave it hanging on a stranger's
          commit, unreadable and still counted when the next version of a
          dashboard by that name is numbered. Any other tag is rebuilt
          with its original message and time, and moves to the nearest
          surviving ancestor if its own commit disappears.

        A commit that touched nothing but this dashboard disappears
        entirely rather than becoming an empty commit; its children are
        re-parented. An empty commit in this history would be a state
        somebody could click that says nothing.
        """
        with self._lock:
            repo = self._repo()
            if repo is None:
                return 0
            if self._resolve(repo, "HEAD") is None:
                return 0
            if key not in set(self.list_all_dashboards()):
                return 0
            return self._forget(repo, key)

    def _forget(self, repo: Repo, key: str) -> int:
        from dulwich.objects import Commit, Tag, Tree  # noqa: PLC0415

        notes = self.descriptions()
        versions = self._raw_tags(repo)

        # Oldest first: a commit can only be rewritten once its parents are.
        order = [entry.commit for entry in repo.get_walker()][::-1]
        target = f"{key}.yaml".encode()
        # `nearest` maps every old commit to the surviving commit that
        # stands in its place - itself if kept, its ancestor if dropped.
        # `kept` holds only the ones that survived as themselves.
        nearest: dict[bytes, bytes | None] = {}
        kept: dict[bytes, bytes] = {}
        removed = 0

        for commit in order:
            tree_id = self._tree_without(repo, commit.tree, target, Tree)
            parents = [
                nearest[parent]
                for parent in commit.parents
                if nearest.get(parent) is not None
            ]
            empty = not repo[tree_id].items()
            if (parents and repo[parents[0]].tree == tree_id) or (
                not parents and empty
            ):
                # Nothing left in it that this dashboard did not own.
                nearest[commit.id] = parents[0] if parents else None
                removed += 1
                continue
            fresh = Commit()
            fresh.tree = tree_id
            fresh.parents = parents
            fresh.author = commit.author
            fresh.committer = commit.committer
            fresh.author_time = commit.author_time
            fresh.author_timezone = commit.author_timezone
            fresh.commit_time = commit.commit_time
            fresh.commit_timezone = commit.commit_timezone
            fresh.message = commit.message
            fresh.encoding = commit.encoding
            repo.object_store.add_object(fresh)
            nearest[commit.id] = fresh.id
            kept[commit.id] = fresh.id

        self._point_head(repo, nearest.get(order[-1].id) if order else None)
        self._rewrite_notes(repo, notes, kept)
        self._rewrite_tags(repo, versions, nearest, Tag, key)

        # Rewriting refs only makes the old objects unreachable; the blobs
        # and commits stay on disk, and `resolve` still finds them. Without
        # this, "forgotten for good" would be a claim the repository
        # contradicts. The grace period is zero on purpose - the usual
        # fourteen days protect objects another writer may be building, and
        # the only other writer here is this class, holding the lock this
        # method runs under.
        from dulwich.gc import garbage_collect  # noqa: PLC0415

        garbage_collect(repo, prune=True, grace_period=0)
        return removed

    @staticmethod
    def _tree_without(repo: Repo, tree_id: bytes, target: bytes, tree_class) -> bytes:
        """The same tree without one dashboard's two files.

        Written for this layout rather than as a general filter: the
        repository is exactly two levels deep - `<key>.yaml` at the top and
        `meta/<key>.yaml` below - and a general recursion would be more
        code with more ways to be subtly wrong.
        """
        tree = repo[tree_id]
        rebuilt = tree_class()
        changed = False
        for entry in tree.items():
            if entry.path == target:
                changed = True
                continue
            if entry.path == b"meta":
                inner = repo[entry.sha]
                if any(item.path == target for item in inner.items()):
                    changed = True
                    kept_meta = tree_class()
                    for item in inner.items():
                        if item.path != target:
                            kept_meta.add(item.path, item.mode, item.sha)
                    if not kept_meta.items():
                        continue  # an empty meta/ directory has no meaning
                    repo.object_store.add_object(kept_meta)
                    rebuilt.add(b"meta", entry.mode, kept_meta.id)
                    continue
            rebuilt.add(entry.path, entry.mode, entry.sha)
        if not changed:
            return tree_id
        repo.object_store.add_object(rebuilt)
        return rebuilt.id

    @staticmethod
    def _point_head(repo: Repo, head: bytes | None) -> None:
        """Move the branch to the rewritten tip, or remove it entirely."""
        try:
            branch = repo.refs.follow(b"HEAD")[0][-1]
        except (KeyError, IndexError):
            branch = b"refs/heads/master"
        if head is None:
            # Everything was forgotten. An empty repository is a valid
            # state here: list_changes already answers [] without a HEAD.
            if branch in repo.refs:
                del repo.refs[branch]
            return
        repo.refs[branch] = head

    @staticmethod
    def _raw_tags(repo: Repo) -> list:
        """Every ref under `refs/tags`, before the rewrite invalidates it.

        Both shapes, as `(ref, tag object or None, the sha it marks)`. An
        annotated tag - the only kind this class makes - is a tag object
        that points at the commit; a lightweight one is the ref pointing
        straight at the commit, with no object of its own.

        Collecting only the annotated ones was a hole in "forgotten for
        good": a lightweight tag was neither deleted nor rewritten, so it
        went on pointing at a pre-rewrite commit and kept the whole old
        history reachable - `garbage_collect` prunes nothing that a ref
        can still reach. Measured: with one present, `forget` reported
        success while the forgotten text stayed readable from the object
        store. Decision 13 of the design record blesses hand-made tags
        explicitly, which makes them likely rather than exotic.
        """
        found = []
        for ref in repo.refs.as_dict(b"refs/tags"):
            tag = repo[repo.refs[b"refs/tags/" + ref]]
            annotated = hasattr(tag, "object")
            found.append((ref, tag if annotated else None,
                          tag.object[1] if annotated else tag.id))
        return found

    def _rewrite_notes(
        self, repo: Repo, notes: dict[str, str], kept: dict[bytes, bytes]
    ) -> None:
        """Put the descriptions back on the commits that survived."""
        if b"refs/notes/commits" in repo.refs:
            del repo.refs[b"refs/notes/commits"]
        for old, text in notes.items():
            new = kept.get(old.encode())
            if new is None:
                continue  # its commit is gone; the description goes too
            porcelain.notes_add(
                str(self.path),
                new,
                text.encode("utf-8"),
                author=_IDENTITY,
                committer=_IDENTITY,
            )

    @staticmethod
    def _rewrite_tags(
        repo: Repo,
        versions: list,
        nearest: dict[bytes, bytes | None],
        tag_class,
        key: str,
    ) -> None:
        """Rebuild the named versions against the rewritten commits.

        The dashboard's own versions go with it. Since decision 13 of the
        design record a version belongs to one dashboard and is named
        `<key>/v<major>.<minor>.<patch>`, so every tag under `<key>/` is
        forgotten here rather than moved. Moving it was right while a
        version marked a moment of the whole history; measured after
        decision 13 it left `gone/v1.0.0` sitting on another dashboard's
        commit, `read_at` answering None for it, and the numbering for a
        future `gone` counting up from a version nobody can reach.

        Every other tag keeps the old behaviour: rebuilt with its original
        message and time, moved to the nearest surviving ancestor when its
        own commit disappears. A lightweight tag has no object to rebuild
        - the ref *is* the tag - so it is re-pointed instead. Inventing a
        tag object for it would hand somebody back a different kind of tag
        than the one they made.
        """
        namespace = f"{key}/".encode()
        for ref, old, target in versions:
            del repo.refs[b"refs/tags/" + ref]
            if ref.startswith(namespace):
                continue  # this dashboard's own version; forgotten with it
            moved = nearest.get(target)
            if moved is None:
                continue  # nothing left for it to mark
            if old is None:
                repo.refs[b"refs/tags/" + ref] = moved
                continue
            fresh = tag_class()
            fresh.object = (old.object[0], moved)
            fresh.name = old.name
            fresh.message = old.message
            fresh.tagger = old.tagger
            fresh.tag_time = old.tag_time
            fresh.tag_timezone = old.tag_timezone
            repo.object_store.add_object(fresh)
            repo.refs[b"refs/tags/" + ref] = fresh.id

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
        ref such as HEAD, the name of a version, or an abbreviated hash of
        the kind `git log --oneline` prints. dulwich resolves neither the
        names nor the abbreviated forms by itself.
        """
        repo = self._repo()
        return None if repo is None else self._resolve(repo, revision)

    @staticmethod
    def _resolve(repo: Repo, revision: str) -> str | None:
        name = revision.strip().encode()
        if not name:
            return None
        sha = None
        # git's own search order. dulwich expands none of it by itself:
        # `repo[b"v1.0.0"]` raises KeyError even when refs/tags/v1.0.0 is
        # right there, because Repo.__getitem__ does no ref-name
        # expansion. Measured on dulwich 1.2.14 (2026-09-02) - and the
        # belief that it did was what decision 10 of the design record
        # rested on when it kept the version services. A tag is only
        # addressable from here.
        for candidate in (name, b"refs/tags/" + name, b"refs/heads/" + name):
            try:
                sha = repo[candidate].id
            except (KeyError, ValueError):
                continue
            break
        if sha is None and 4 <= len(name) < 40:
            # git itself refuses fewer than four characters; so do we.
            lowered = name.lower()
            if all(char in b"0123456789abcdef" for char in lowered):
                matches = list(repo.object_store.iter_prefix(lowered))
                # An ambiguous prefix is refused rather than guessed:
                # picking one of two commits would be worse than saying
                # it is not clear which was meant.
                if len(matches) == 1:
                    sha = matches[0]
        if sha is None:
            return None
        obj = repo[sha]
        while obj.type_name == b"tag":
            # An annotated tag points at the commit; that is what is wanted.
            try:
                obj = repo[obj.object[1]]
            except KeyError:
                return None
        if obj.type_name != b"commit":
            # A blob or a tree is an object like any other: it answers to
            # its full id and to an abbreviated prefix, and a tag can be
            # made to point at one. Handed on as if it were a commit it
            # breaks in a different way at every caller - `read_at`
            # reaches for `.tree` and raises AttributeError, which arrives
            # as a generic failure through the WebSocket and as a bare
            # traceback through `services.py`, and `create_version`
            # accepts it and leaves a tag nobody can ever return to, which
            # nothing can delete again. `None` already means "unknown
            # revision" to every caller here, and every one of them
            # handles it; saying it once, at the only place that knows
            # what the object really is, is the whole fix.
            return None
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
        return None if repo is None else self._read_from(repo, path, revision)

    @classmethod
    def _read_from(cls, repo: Repo, path: str, revision: str) -> str | None:
        """Same, for callers that already hold a repository.

        Opening one costs a file handle and a pack index; comparing fifty
        revisions is a normal thing for the panel to ask.
        """
        resolved = cls._resolve(repo, revision)
        if resolved is None:
            return None
        try:
            tree = repo[repo[resolved.encode()].tree]
            _, blob_id = tree.lookup_path(repo.get_object, path.encode())
        except KeyError:
            return None
        return repo[blob_id].data.decode("utf-8")

    def matching_revisions(
        self, key: str, revisions: Iterable[str], text: str
    ) -> set[str]:
        """Which of these revisions hold exactly this text for this dashboard.

        Answers the question the panel needs to orient itself: *which of
        these entries is the dashboard I am looking at right now?* A history
        that went back and forth holds several states with byte-identical
        content, and because the messages are generated they read alike
        too - seven entries saying "2 moved", every second one identical to
        the live dashboard. Marking them is the difference between a list
        and a wall.

        One repository for the whole comparison. An unknown revision simply
        does not match; it is not an error to ask about one.
        """
        repo = self._repo()
        if repo is None:
            return set()
        path = f"{key}.yaml"
        return {
            revision
            for revision in revisions
            if self._read_from(repo, path, revision) == text
        }

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

    def list_versions(self, key: str | None = None) -> list[Version]:
        """Every named point, newest first. One dashboard's, or all of them.

        Ordered by the time the tag was made, which is the only order this
        class can know. A caller that wants them by version *number* sorts
        them itself - the numbering lives in `versions.py`, and this
        module stays free of it.
        """
        repo = self._repo()
        if repo is None:
            return []
        prefix = None if key is None else f"{key}/"
        found: list[tuple[int, Version]] = []
        for ref in repo.refs.as_dict(b"refs/tags"):
            name = ref.decode()
            if prefix is not None and not name.startswith(prefix):
                continue
            tag = repo[repo.refs[b"refs/tags/" + ref]]
            if hasattr(tag, "object"):
                message = (tag.message or b"").decode("utf-8")
                title, _, description = message.partition("\n\n")
                marked, made = tag.object[1], tag.tag_time
            else:
                # A lightweight tag, made by hand: the ref points straight
                # at the commit and carries no message, so it has no title
                # and no description. Reported all the same, as decision 13
                # of the design record promises - skipping it made
                # `candidates` offer a number that already existed, and the
                # refusal then landed in the middle of the dialog. Ordered
                # by the time of the commit it marks, the only time it has;
                # anything but a commit sorts last rather than crashing.
                title, description = "", ""
                marked, made = tag.id, getattr(tag, "commit_time", 0)
            found.append(
                (
                    made,
                    Version(
                        name=name,
                        revision=_as_text(marked),
                        title=title.strip(),
                        description=description.strip(),
                    ),
                )
            )
        # as_dict has no order of its own; the docstring promises one.
        return [version for _, version in sorted(found, key=lambda p: -p[0])]
