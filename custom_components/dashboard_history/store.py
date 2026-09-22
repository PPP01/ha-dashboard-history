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

import json
import logging
import os
import shutil
import threading
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from itertools import islice
from pathlib import Path

try:  # Two load paths, and this module has to work under both.
    # Home Assistant imports this as part of the package; plain pytest
    # puts the package directory on `sys.path` instead, so that the
    # Home-Assistant-free modules can be reached without executing the
    # `__init__` that imports Home Assistant. Neither spelling works in
    # the other's world. Both modules here are Home-Assistant-free, so
    # nothing about that rule changes.
    from . import versions as versioning
except ImportError:  # pragma: no cover - the flat path, used by pytest
    import versions as versioning

from dulwich import porcelain
from dulwich.errors import MissingCommitError, RefFormatError
from dulwich.file import FileLocked
from dulwich.repo import Repo

_LOGGER = logging.getLogger(__name__)

_IDENTITY = b"Dashboard History <dashboard-history@localhost>"

# The name of the file `forget` leaves behind, inside `.git`, while one
# of its ref-rewrite steps is still outstanding - see decision 21. Every
# write method checks for it before doing anything; `forget` itself
# checks it too, so a crashed attempt cannot be stomped on by a second
# one before a restart gets to repair it.
_FORGET_CHECKPOINT_NAME = "dashboard_history_forget.json"

# Repository paths whose stale locks this process has already swept
# once. Keyed by path rather than held on `HistoryStore` itself, because
# what has to be remembered across a reload is that *this process* has
# done the sweep for *this repository* - not anything an instance that
# a reload throws away could carry forward. See `_clear_stale_locks`.
_swept_paths: set[str] = set()

# Locks shared by every `HistoryStore` for the same resolved path within
# this process - not one lock per instance. A reload builds a fresh
# instance with what would otherwise be its own, unrelated lock, and
# nothing then stops it from running concurrently with whatever an
# older instance is still doing to the same repository. `_swept_paths`
# above solves a related-looking problem for a different operation by
# never repeating it after the first attempt in a process - that works
# there because repeating the lock sweep has no value once it has
# happened once. A repair does not have that property: a checkpoint can
# genuinely appear later in a long-running process, from a real, new
# crash, and must stay safe to repair when it does. A lock shared
# across instances, not a "done once" marker, is what that needs.
_locks_by_path: dict[str, threading.Lock] = {}
_locks_registry_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _locks_registry_guard:
        if key not in _locks_by_path:
            _locks_by_path[key] = threading.Lock()
        return _locks_by_path[key]


@dataclass(frozen=True)
class Change:
    """One recorded state of one dashboard."""

    revision: str
    timestamp: int
    message: str
    description: str = ""  # what a person wrote about it, if anyone did
    # The state of this dashboard just before this change, or None where
    # there is none. A field rather than a sum: a caller that works it
    # out from the neighbour in a list is right only while that list is
    # whole and in order - which a page and a search result are not.
    previous: str | None = None


@dataclass(frozen=True)
class Version:
    """A named point in the history. It groups, it never squashes."""

    name: str
    revision: str
    title: str
    description: str
    # When the tag was made - the time `list_versions` already orders by,
    # now carried rather than dropped. A panel listing nothing but
    # versions needs it: titles repeat, times do not. Zero where there is
    # none to have, and a reader shows nothing rather than 1970.
    timestamp: int = 0
    # Whether this is an annotated tag - the only kind this class makes -
    # or a lightweight one somebody set by hand. Carried because it
    # decides what can be done with the version: a lightweight tag is the
    # ref itself and has no message, so it has no words to rewrite.
    # `list_versions` has always had to branch on this and used to throw
    # the answer away, which left the panel inferring it from an empty
    # title - a field a person is now allowed to rewrite.
    annotated: bool = True


@dataclass(frozen=True)
class Survey:
    """Every dashboard the history has ever held, and what each one is called.

    `live` are the ones at HEAD. `last_meta` holds the last recorded
    metadata text of every dashboard that has one: for a live dashboard
    the text at HEAD, for a gone one the text its deletion removed - the
    name and icon it should be listed under, and would come back with.
    """

    names: list[str]
    live: set[str]
    last_meta: dict[str, str]


@dataclass(frozen=True)
class DashboardFacts:
    """One dashboard's share of the history.

    `bytes` is the length of the newest state that *had content*, which
    for a deleted dashboard is the state before its deletion - the size
    a restore would bring back. `last` is the newest commit that touched
    it at all, which for that same dashboard is the deletion. The two
    fields answer different questions on purpose; tying both to one
    revision would answer one of them wrongly.
    """

    key: str
    revisions: int
    bytes: int
    versions: int
    first: int
    last: int
    gone: bool


@dataclass(frozen=True)
class Measurement:
    """What the history costs and holds, taken at one moment.

    Every field has a defined value on an empty or absent repository, so
    that a fresh installation reads as "nothing recorded yet" rather
    than as a failure - an empty history is an answer, not a fault.

    A history that cannot be *read*, though, is a fault, and `measure`
    raises on one. The coordinator above it keeps the last good
    measurement and marks it stale, which is what a reader needs;
    numbers quietly missing their unreadable half would not be.
    """

    revisions: int = 0
    oldest: int | None = None
    newest: int | None = None
    newest_key: str | None = None
    versions: int = 0
    dashboards: tuple[DashboardFacts, ...] = ()
    bytes_allocated: int | None = None
    bytes_git_logical: int = 0
    bytes_worktree_logical: int = 0
    loose_objects: int = 0
    packs: int = 0

    # Derived rather than stored, all four of them. Each was a field
    # once, and each was computed a second time by a reader that wanted
    # it - `live` and `gone` in both `report.py` and `sensor.py`, from
    # the same list. Two derivations of one number are two chances to
    # disagree, and a check whose whole job is to catch that
    # disagreement is a check that only exists because the number has
    # two homes.

    @property
    def bytes_logical(self) -> int:
        """What the store contains, as opposed to what it occupies."""
        return self.bytes_git_logical + self.bytes_worktree_logical

    @property
    def bytes_on_disk(self) -> int:
        """What it costs, falling back where the platform cannot say.

        `st_blocks` does not exist on Windows, and the logical sum is
        the honest stand-in there - a number that is too small rather
        than one that is made up.
        """
        return (
            self.bytes_allocated if self.bytes_allocated is not None
            else self.bytes_logical
        )

    @property
    def gone(self) -> int:
        """Dashboards the history still holds but the installation lost."""
        return sum(1 for facts in self.dashboards if facts.gone)

    @property
    def live(self) -> int:
        return len(self.dashboards) - self.gone


@dataclass(frozen=True)
class RevisionIndex:
    """Which commits touched which dashboard, taken at one HEAD.

    `by_key` holds each dashboard's own revisions, newest first - the
    same entries, in the same order, that a walk filtered on its two
    paths would hand back. `order` places every commit in that one walk,
    which is what a cursor needs: `before` may name a commit of some
    other dashboard, and "everything older than it" only means anything
    against the whole order.

    Taken at `head`, and worthless at any other: a rewrite moves every
    revision from the first affected commit onwards.
    """

    head: str
    by_key: dict[str, list[str]]
    order: dict[str, int]
    # What `survey` used to walk the history for a second time to learn:
    # every name the history has ever held, and the blob of the
    # `meta/<key>.yaml` a deletion removed - the newest such removal,
    # which is the name and icon a gone dashboard last had.
    names: set[str]
    removed_meta: dict[str, bytes]


def _as_text(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _version_body(title: str, description: str) -> bytes:
    """The message a version's tag carries: title, blank line, the rest.

    One place, with `_version_words` as its other half. Two callers
    write this - a version being made and one being given new words -
    and two read it, and the blank line is the whole format. Copies of a
    wire format drift until a description turns up inside somebody's
    title.
    """
    return f"{title}\n\n{description}".encode("utf-8")


def _version_words(message: bytes | None) -> tuple[str, str]:
    """A version tag's message as `(title, description)`.

    The reading half of `_version_body`. A tag with no message at all -
    a lightweight one, or an annotated one somebody made with an empty
    body - answers two empty strings rather than needing a branch at
    every caller.
    """
    title, _, description = (message or b"").decode("utf-8").partition("\n\n")
    return title.strip(), description.strip()


def _version_from(name: str, target) -> Version:
    """One tag as a `Version`, whichever of the two kinds it is.

    `target` is what the ref points at: a tag object for an annotated
    one, and the commit itself for a lightweight one - which is what a
    lightweight tag *is*, a ref straight to the object.

    One builder because there are two readers. `list_versions` walks the
    namespace, `read_version` looks up one name, and the removal of a
    version is previewed from the second while the panel's list comes
    from the first. A field present in one answer and missing from the
    next is the kind of difference a frontend quietly renders as False -
    the same reason `_version_dict` exists one layer up.

    A lightweight tag carries no message, so it has no title and no
    description, and it is ordered by the time of the commit it marks -
    the only time it has. Anything but a commit (a hand-made tag on a
    blob) answers zero rather than raising: it is reported all the same,
    as decision 13 of the design record promises.
    """
    annotated = hasattr(target, "object")
    if annotated:
        title, description = _version_words(target.message)
        marked, made = target.object[1], target.tag_time
    else:
        title, description = "", ""
        marked, made = target.id, getattr(target, "commit_time", 0)
    return Version(
        name=name,
        revision=_as_text(marked),
        title=title,
        description=description,
        timestamp=made,
        annotated=annotated,
    )


def _change(commit, notes: dict, previous: str | None) -> Change:
    """One commit as a `Change`, with the predecessor handed in.

    A function rather than a method: it knows nothing about the store,
    and the commit it is given is the only thing it reads. The commit
    and not the walk entry it came in, because the index hands over
    commits it looked up by id and never walked to.
    """
    revision = _as_text(commit.id)
    return Change(
        revision=revision,
        timestamp=commit.commit_time,
        message=commit.message.decode("utf-8").strip(),
        description=notes.get(revision, ""),
        previous=previous,
    )


def _key_of(path: bytes) -> str | None:
    """The dashboard a recorded path belongs to, or None.

    The exact inverse of the two paths `_each_change` asks for, and it
    has to stay that way: a key the index spells differently is a
    dashboard whose history silently ends at the last read that walked.
    `meta/` first, so `meta/home.yaml` is home's name and not a
    dashboard of its own - and the rest untouched, so a legacy key with
    a slash in it (see `_owns`) keeps the history it already has.
    """
    if not path.endswith(b".yaml"):
        return None
    if path.startswith(b"meta/"):
        return path[len(b"meta/") : -len(b".yaml")].decode()
    return path[: -len(b".yaml")].decode()


@dataclass(frozen=True)
class _Touched:
    """What one walk entry says about the dashboards it changed."""

    # Every dashboard the entry changed, by either of its two paths -
    # what a walk filtered on those paths would have handed back.
    keys: set[str]
    # Names as `survey` counts them: top level only, so `meta/home.yaml`
    # is home's name and never a dashboard called `meta/home`.
    names: set[str]
    # Where a deletion took `meta/<key>.yaml` away, the blob it took.
    removed_meta: dict[str, bytes]


def _touched(entry) -> _Touched:
    """Read one walk entry once, for everything the index wants.

    Both sides of every change, so a deletion counts as much as a write
    - the removal of `home.yaml` is the most important thing that ever
    happens to home. A merge hands its changes over as a list per
    parent, which is the one shape that has to be unwrapped.

    Three answers out of one pass because the pass is the expensive
    part: `entry.changes()` diffs the commit against its parent, and
    without dulwich's C extensions - which the Home Assistant container
    has never had, see `_revision_index` - that is the whole cost of
    reading this history.
    """
    keys: set[str] = set()
    names: set[str] = set()
    removed_meta: dict[str, bytes] = {}
    for change in entry.changes():
        for one in change if isinstance(change, list) else [change]:
            for side in (one.old, one.new):
                path = getattr(side, "path", None)
                if not path or not path.endswith(b".yaml"):
                    continue
                key = _key_of(path)
                if key is not None:
                    keys.add(key)
                # Top level only: meta/<key>.yaml is not a dashboard.
                if b"/" not in path:
                    names.add(path.decode()[: -len(".yaml")])
            old_path = getattr(one.old, "path", None)
            if (
                old_path
                and old_path.startswith(b"meta/")
                and old_path.endswith(b".yaml")
                and getattr(one.new, "path", None) is None
            ):
                gone = old_path[len("meta/") : -len(".yaml")].decode()
                removed_meta.setdefault(gone, one.old.sha)
    return _Touched(keys, names, removed_meta)


class _Progress:
    """Says how far `forget` has got, without ever getting in its way.

    Two rules, and both are about the operation rather than the report:

    * **A failing listener must not stop a rewrite.** Half a rewritten
      history is the one outcome this module must never produce, and it
      would be absurd to reach it because somebody's progress bar threw.
      So everything here is swallowed - the operation does not depend on
      being watched.
    * **Saying it costs something.** Every call crosses into Home
      Assistant's event loop and out again over a WebSocket. Announced
      per commit it would be 7407 events for one `forget`; `every` thins
      that to one per `step`, which keeps the number moving without the
      report competing with the work it describes.

    No callback at all is the normal case: every caller but the panel's
    passes none, and then this costs one `if` per step.
    """

    __slots__ = ("_report",)

    def __init__(self, report: Callable[[str, int, int], None] | None) -> None:
        self._report = report

    def __call__(self, phase: str, done: int, total: int) -> None:
        if self._report is None:
            return
        try:
            self._report(phase, done, total)
        except Exception:  # noqa: BLE001 - see the class docstring
            _LOGGER.exception("Could not report the progress of forget")

    def every(self, step: int, phase: str, done: int, total: int) -> None:
        """The same, but only on every `step`-th item."""
        if self._report is not None and done and done % step == 0:
            self(phase, done, total)


def _owns(ref: bytes, key: str) -> bool:
    """Whether a tag named `ref` is one of dashboard `key`'s versions.

    A version is `<key>/v<major>.<minor>.<patch>`, so what follows the
    key's own slash is one segment. Tested with startswith alone, "foo/"
    also claimed `foo/bar/v1.0.0` - the version of a legacy dashboard
    whose key holds a slash - and `forget("foo")` deleted it. Measured
    on 2026-09-04.
    """
    namespace = f"{key}/".encode()
    if not ref.startswith(namespace):
        return False
    return b"/" not in ref[len(namespace):]


_FORGET_RACE_RETRIES = 3


class HistoryStore:
    """Stores dashboard states and reads them back."""

    def __init__(self, path) -> None:
        self.path = Path(path)
        # dulwich takes an exclusive lock on the git index while it writes.
        # Two dashboards saved in the same moment run in two executor
        # threads; measured, eight parallel commits let exactly one through
        # and the other seven raised FileLocked. Writes are serialised here
        # rather than left to chance - and, since decision 21, shared with
        # every other `HistoryStore` for this same path in this process,
        # not held by this instance alone: see `_lock_for`.
        self._lock = _lock_for(self.path)
        # The last survey, keyed by the HEAD it was taken at. Names and
        # metadata change only when HEAD does, and `forget` rewrites HEAD,
        # so a stale entry cannot survive. Kept because the panel asks for
        # the survey on every recorded change, and each one is a walk over
        # the whole history.
        self._survey: tuple[str, Survey] | None = None
        # Which commits touched which dashboard, and where each commit
        # sits in the one order the walk hands them back. See
        # `_revision_index` for why this exists at all.
        self._index: RevisionIndex | None = None

    # -- writing -------------------------------------------------------

    def ensure(self) -> None:
        """Create the repository, or clear locks left by a killed process."""
        with self._lock:
            self._ensure()

    def _ensure(self) -> None:
        """Same, for callers that already hold the lock."""
        git_dir = self.path / ".git"
        if git_dir.exists():
            key = str(self.path.resolve())
            if key not in _swept_paths:
                self._clear_stale_locks(git_dir)
                _swept_paths.add(key)
            return
        self.path.mkdir(parents=True, exist_ok=True)
        porcelain.init(str(self.path))
        _LOGGER.info("Created dashboard history repository at %s", self.path)

    def _clear_stale_locks(self, git_dir: Path) -> None:
        """Remove `.lock` files left by a git operation that was killed.

        dulwich writes packed and loose refs atomically through a
        sibling `.lock` file. The *first* `ensure()` this process makes
        for this path runs before this process has written anything, so
        any lock already on disk at that point was left by a process
        that no longer exists - removing it is always safe. Leaving it
        disables `forget` for good, since every later attempt fails
        taking the same lock (issue #19).

        Never repeated after that first call, and that restriction is
        load-bearing, not a minor optimisation: a *reload* builds a new
        `HistoryStore` - a new instance, a new `threading.Lock` - while
        a write dispatched through `hass.async_create_task` before the
        reload can still be running in the executor, unwaited, holding
        a lock of its own. That process is not dead. Sweeping on every
        call raced exactly that write in the review of issue #19's
        first fix, breaking its rename with `FileNotFoundError`. `_ensure`
        already serialises every call to this store instance through
        `self._lock`, but a reload's old and new instances share no
        lock at all - `_swept_paths` is what stands in for one, across
        instances, for the life of this process.

        Restricted to `refs/` rather than the whole `.git` directory:
        that is the only place besides the top level where dulwich
        takes this kind of lock, and the top level is checked directly.
        Objects are written through a rename, not a lock file, and a
        history can hold thousands of them - walking that tree on every
        start would cost what `ensure()` is meant not to.
        """
        locks = list(git_dir.glob("*.lock"))
        refs_dir = git_dir / "refs"
        if refs_dir.is_dir():
            locks.extend(refs_dir.rglob("*.lock"))
        for lock in locks:
            lock.unlink(missing_ok=True)
            _LOGGER.warning(
                "Removed stale lock file left by an interrupted git "
                "operation: %s",
                lock,
            )

    @staticmethod
    def _clear_stale_object_locks(git_dir: Path) -> None:
        """Remove `.lock` files under `objects/` left by a dead process.

        Kept apart from `_clear_stale_locks` (issue #19, `refs/` and the
        top level) because it relies on a different safety argument.
        `_clear_stale_locks` may run only once, at the very first
        `ensure()` call in a process, before that process has written
        anything - the one moment a lock's owner can be assumed dead
        without more to go on. This sweep instead relies on the shared,
        per-path lock `repair_pending_forget` holds while calling it
        (decision 21, correction 4): while that lock is held, nothing
        else in this process can be concurrently writing to this
        repository, so any lock found here is provably not a live
        writer's - a dead, earlier process, or an earlier attempt in
        this same process that already released the lock without
        cleaning up after itself. Safe to repeat on every call, unlike
        `_clear_stale_locks`.

        A first version of this fix cleared a lock like this locally,
        at the one write it would block, and retried that write once -
        a review found that unsafe without this argument (`FileLocked`
        means the lock file exists, never that its owner is dead) and
        incomplete (`_tree_without` writes two more objects a narrow,
        per-call-site fix would have missed). See decision 21,
        correction 5.
        """
        objects_dir = git_dir / "objects"
        if not objects_dir.is_dir():
            return
        for lock in objects_dir.rglob("*.lock"):
            lock.unlink(missing_ok=True)
            _LOGGER.warning(
                "Removed stale object lock left by an interrupted git "
                "operation: %s",
                lock,
            )

    def _checkpoint_path(self) -> Path:
        return self.path / ".git" / _FORGET_CHECKPOINT_NAME

    def _refuse_if_forget_pending(self) -> None:
        """Refuse to write while an earlier `forget` is still unfinished.

        Checked on every call, not once per process the way
        `_clear_stale_locks` is: the checkpoint can sit unrepaired for as
        long as nobody restarts Home Assistant, and every write in that
        window is a chance to advance HEAD, notes or tags past what the
        checkpoint expects - which a later repair would then either
        overwrite or leave stale, either way silently. Refusing costs
        nothing to be wrong about: a paused recording is recoverable, a
        repair that undid somebody else's save is not. See decision 21,
        correction 1.
        """
        if self._checkpoint_path().exists():
            raise ValueError(
                "Dashboard History cannot write right now: an earlier "
                "forget did not finish and left a checkpoint behind "
                f"({self._checkpoint_path()}). Restart Home Assistant - "
                "the interrupted rewrite finishes automatically before "
                "recording resumes."
            )

    def _write_checkpoint(
        self,
        key: str,
        head: bytes | None,
        notes: dict[bytes, bytes],
        tags: dict[bytes, bytes | None],
    ) -> None:
        """Save what `forget` is about to finish, before any ref moves.

        Four fields, not three: `key` has to be in here too, because
        `_drop_from_index` needs it and nothing else remembers which
        dashboard was being forgotten once a crash has happened. Written
        through `_write_file`'s temp-then-`os.replace` so an interrupted
        write of the checkpoint itself is never mistaken for a valid one
        - see decision 21.
        """
        payload = {
            "key": key,
            "head": head.decode() if head is not None else None,
            "notes": {sha.decode(): text.decode("utf-8") for sha, text in notes.items()},
            "tags": {
                ref.decode("utf-8", "surrogateescape"): (
                    sha.decode() if sha is not None else None
                )
                for ref, sha in tags.items()
            },
        }
        self._write_file(self._checkpoint_path(), json.dumps(payload))

    def _read_checkpoint(
        self,
    ) -> tuple[str, bytes | None, dict[bytes, bytes], dict[bytes, bytes | None]] | None:
        """The inverse of `_write_checkpoint`, or `None` if there is none.

        If the checkpoint file exists but cannot be parsed or lacks the
        required shape, it is logged with a traceback and deleted: an
        unreadable plan cannot be finished automatically, and leaving it
        in place would permanently disable all writes across restarts
        (issue #23).

        A pure I/O error (`OSError`, e.g. permission denied) is kept
        strictly apart from content corruption: it does not prove the
        plan is broken, only that it cannot be read right now. In that
        case the file is left untouched so the write guard remains in
        place until the filesystem issue is resolved.
        """
        path = self._checkpoint_path()
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            _LOGGER.exception(
                "Removed corrupt forget checkpoint with invalid encoding %s: %s. "
                "An interrupted forget could not be finished automatically.",
                path,
                exc,
            )
            try:
                path.unlink(missing_ok=True)
            except OSError:
                _LOGGER.exception("Could not remove corrupt checkpoint %s", path)
            return None
        except OSError:
            _LOGGER.exception(
                "Could not read forget checkpoint %s due to an I/O error; "
                "leaving file in place to avoid losing a pending plan",
                path,
            )
            return None

        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError(f"expected dict, got {type(payload).__name__}")
            key = payload["key"]
            if not isinstance(key, str):
                raise ValueError("key must be a string")
            head_val = payload["head"]
            if head_val is not None and not isinstance(head_val, str):
                raise ValueError("head must be a string or None")
            head = head_val.encode() if head_val is not None else None
            notes_val = payload["notes"]
            if not isinstance(notes_val, dict):
                raise ValueError("notes must be a dict")
            notes = {
                sha.encode(): text.encode("utf-8")
                for sha, text in notes_val.items()
            }
            tags_val = payload["tags"]
            if not isinstance(tags_val, dict):
                raise ValueError("tags must be a dict")
            tags = {
                ref.encode("utf-8", "surrogateescape"): (
                    sha.encode() if sha is not None else None
                )
                for ref, sha in tags_val.items()
            }
            return key, head, notes, tags
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            AttributeError,
        ) as exc:
            _LOGGER.exception(
                "Removed unreadable forget checkpoint %s: %s. An "
                "interrupted forget could not be finished automatically.",
                path,
                exc,
            )
            try:
                path.unlink(missing_ok=True)
            except OSError:
                _LOGGER.exception("Could not remove unreadable checkpoint %s", path)
            return None

    @staticmethod
    def _is_valid_commit(repo: Repo, sha: bytes) -> bool:
        """Whether `sha` is a real, existing commit in this repository."""
        from dulwich.objects import valid_hexsha  # noqa: PLC0415

        if not valid_hexsha(sha):
            return False
        try:
            return repo[sha].type_name == b"commit"
        except KeyError:
            return False

    @staticmethod
    def _is_valid_tag_target(repo: Repo, sha: bytes) -> bool:
        """Whether `sha` is a commit or a tag object.

        The only two things a tag in this repository ever points at: a
        lightweight tag directly at a commit, an annotated one at its
        own tag object. A blob or a tree sha existing is not enough -
        see decision 21, correction 7.
        """
        from dulwich.objects import valid_hexsha  # noqa: PLC0415

        if not valid_hexsha(sha):
            return False
        try:
            return repo[sha].type_name in (b"commit", b"tag")
        except KeyError:
            return False

    def _validate_checkpoint_semantics(
        self,
        repo: Repo,
        key: str,
        head: bytes | None,
        notes: dict[bytes, bytes],
        tags: dict[bytes, bytes | None],
    ) -> None:
        """Reject a checkpoint whose values look right but are not.

        `_read_checkpoint` (Korrektur 6) only proves the payload has
        the right shape - strings where strings belong, dicts where
        dicts belong. It cannot prove a string is a real sha, a legal
        ref name, or a key that stays inside the store, because it
        never has `repo` or `_file_for` to check against. A value that
        is well-typed but wrong reaches `_finish_forget` unless
        something stops it here, and letting it through is dangerous,
        not merely wrong: `_rewrite_notes` deletes `refs/notes/commits`
        before writing entries back, so an invalid sha loses a real,
        unrelated note before its own `AssertionError` is even raised;
        `_rewrite_tags` writes partially into `packed-refs` before an
        invalid ref name raises `PackedRefsException`, corrupting tag
        lookups for the whole repository, not just the dashboard being
        forgotten; `_drop_from_index` builds a path straight from
        `key` with no containment check of its own, unlike every live
        write path, which all go through `_file_for`. See decision 21,
        correction 7.

        Raises `ValueError` naming the first offending field on any
        failure; the caller treats that exactly like a checkpoint that
        failed to parse at all.
        """
        try:
            key.encode("utf-8")
            self._file_for(key)
            self._file_for(key, "meta")
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError(f"key {key!r} does not name a file in the store") from exc
        if head is not None and not self._is_valid_commit(repo, head):
            raise ValueError(f"head {head!r} is not a valid, existing commit")
        for sha in notes:
            if not self._is_valid_commit(repo, sha):
                raise ValueError(f"notes key {sha!r} is not a valid, existing commit")
        from dulwich.refs import check_ref_format  # noqa: PLC0415

        for ref, sha in tags.items():
            if not check_ref_format(ref) or not ref.startswith(b"refs/tags/"):
                raise ValueError(f"tags key {ref!r} is not a legal tag ref name")
            if sha is not None and not self._is_valid_tag_target(repo, sha):
                raise ValueError(f"tags value {sha!r} is not a valid commit or tag object")

    def _best_effort_checkpoint_key(self) -> str | None:
        """The checkpoint's `key` field, read as leniently as possible.

        Used only to narrow `_reconcile_index_with_head`'s reach: if
        the checkpoint survived far enough to name which dashboard it
        was about - even if `head`, `notes` or `tags` did not -
        reconciliation only ever touches that dashboard's own two
        paths, with the same precision `_drop_from_index` already has
        for the ordinary case. Returns `None` on any failure
        whatsoever; the caller then falls back to the wider, generic
        sweep, which is the only way to still close a checkpoint too
        damaged to say even this much. See decision 21, correction 7.
        """
        try:
            payload = json.loads(self._checkpoint_path().read_text(encoding="utf-8"))
            key = payload["key"]
            if not isinstance(key, str):
                return None
            key.encode("utf-8")
            return key
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            UnicodeDecodeError,
            UnicodeEncodeError,
            OSError,
        ):
            return None

    def _reconcile_index_with_head(self, repo: Repo, key: str | None) -> None:
        """Drop any index entry whose path HEAD's tree no longer has.

        `_drop_from_index` already does this for one known key, right
        after `_finish_forget`'s other three steps succeed. If `forget`
        is interrupted between `_point_head` and `_drop_from_index` -
        HEAD already rewritten, the index not yet touched - and the
        checkpoint that would have let a later `repair_pending_forget`
        finish the job is itself discarded, nothing else remembers
        which key was being forgotten, unless `key` could still be
        recovered.

        When `key` is available (`_best_effort_checkpoint_key`
        recovered it), only that dashboard's own two paths are ever
        considered - identical precision to `_drop_from_index`, zero
        risk of touching an unrelated dashboard's own, still-legitimate
        index entry (a brand-new dashboard's first save, staged but not
        yet committed, has its path in the index and nowhere in HEAD
        too - indistinguishable from an orphan by path alone). Only
        when even `key` could not be recovered does this fall back to
        every path in the index - the only way to still close a
        checkpoint damaged enough to lose even that, at the cost of the
        same narrow ambiguity. See decision 21, correction 7.

        A path's *presence* in HEAD's tree is what decides its fate,
        never whether its content still matches: an index entry can
        legitimately differ from HEAD if a `porcelain.commit` step
        failed transiently and is waiting for the next save to retry.

        Only `repo.head()`'s own `KeyError` - no commit yet, a genuinely
        empty repository - is treated as "nothing is live". A `KeyError`
        while opening the commit, its tree, or the `meta` subtree HEAD
        already names is a corrupted repository, not an empty one, and
        is left to propagate rather than being read as license to
        remove every index entry.
        """
        index = repo.open_index()
        candidates: list[bytes]
        if key is not None:
            try:
                candidates = [
                    f"{key}.yaml".encode("utf-8"),
                    f"meta/{key}.yaml".encode("utf-8"),
                ]
            except UnicodeEncodeError:
                candidates = list(index.paths())
        else:
            candidates = list(index.paths())

        try:
            head = repo.head()
        except KeyError:
            live: set[bytes] = set()
        else:
            from dulwich.object_store import iter_tree_contents  # noqa: PLC0415

            commit = repo[head]
            live = {
                entry.path
                for entry in iter_tree_contents(repo.object_store, commit.tree)
            }

        changed = False
        for path in candidates:
            if path in index and path not in live:
                del index[path]
                (self.path / path.decode("utf-8", "surrogateescape")).unlink(missing_ok=True)
                changed = True
        if changed:
            index.write()

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
            self._refuse_if_forget_pending()
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
            self._refuse_if_forget_pending()
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
            self._refuse_if_forget_pending()
            self._create_version(name, title, description, revision)

    def _create_version(
        self, name: str, title: str, description: str, revision: str | None
    ) -> None:
        self._refuse_colliding_name(name)
        marked = self._marked_commit(revision)
        body = _version_body(title, description)
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

    def retitle_version(
        self, key: str, name: str, title: str, description: str
    ) -> Version:
        """Give one dashboard's version new words. Answers the result.

        Every refusal is a ValueError carrying a sentence, exactly as
        `create_version` answers all of its own - a name that collides,
        one git will not take, a revision that is not a commit. The
        caller already catches those in one place, so there is nothing
        here for it to learn.

        Three of them, and each is a different thing to say to a person:
        the version is not this dashboard's, there is no version by that
        name, or there is one but somebody made it by hand and it has no
        message to change. `_owns` decides the first, which is the whole
        ownership fence: a command taking a bare ref name would
        otherwise rewrite any tag in the repository.

        The marker of an automatic version is carried over here rather
        than by the caller. It says who *made* the version, which new
        words about it do not change - and it is machine-read: the day
        mark reads it to know which days already carry one, so a version
        that lost it on being renamed would let its day be marked twice.
        Written where the tag body is written, it cannot be forgotten by
        the next caller that wants to change a version's words.

        A tag object cannot be edited. Its name is the hash of its
        contents, so what happens here is a fresh object and the same ref
        pointed at it. `copy()` carries everything across rather than a
        list of fields naming what to keep, which is the difference
        between a rule and an inventory - measured on dulwich 1.2.14, a
        hand-written list of the six fields that seemed to matter already
        dropped `_tag_timezone_neg_utc`, so a tag made at `-0000` came
        back as `+0000`. Three things it therefore keeps, and each was
        wanted:

        * **The commit it marks.** A version names a state; new words
          about it are not a new state. This is what keeps the operation
          outside the hard rule about previews - no dashboard changes,
          and nothing anybody can see is different.
        * **The time it was made.** `list_versions` orders by it, so a
          fresh time would send a corrected typo to the top of the list.
          Asked for explicitly when this was: the order must not change.
        * **The tagger.** Rewriting it would claim the version was made
          by whoever last touched its wording.

        The signature is the one thing deliberately dropped: a signature
        over the old words says nothing about the new ones, and carrying
        it would hand back a tag that claims to be signed and is not.

        The ref is re-pointed rather than deleted and written again.
        `_rewrite_tags` deletes first because it moves names around; here
        the name stays, and one assignment leaves no window in which the
        version does not exist. A version is the protective mark of
        project C - what carries a tag is never touched when the history
        is compacted - so a crash that dropped one would be expensive in
        a way a crash that leaves an old wording is not.

        The old tag object stays behind as a loose object nothing points
        at, a few hundred bytes that `forget`'s `garbage_collect` sweeps
        up. Pruning it here would mean a full object-store walk per typo.
        """
        with self._lock:
            # No `_ensure()`, unlike every other write here. This one can
            # only ever change something that already exists, so a
            # repository that is not there is an answer and not a state
            # to be built: creating one to then report "no such version"
            # would leave a history behind that nobody asked for.
            self._refuse_if_forget_pending()
            repo = self._repo()
            ref, old = self._tag_at_locked(repo, key, name)
            if not hasattr(old, "object"):
                # A lightweight tag: the ref *is* the tag. Giving it a
                # message means handing back a different kind of tag than
                # the one somebody made, which is the line `_rewrite_tags`
                # draws for the same reason.
                raise ValueError(f"version made by hand, it carries no text: {name}")
            _, automatic = versioning.read_description(_version_words(old.message)[1])
            stored = (
                versioning.automatic_description(description)
                if automatic
                else description
            )
            fresh = old.copy()
            fresh.message = _version_body(title, stored)
            fresh.signature = None
            repo.object_store.add_object(fresh)
            repo.refs[ref] = fresh.id
            # Built from what is already in hand. The caller needs the
            # result in the one shape every version leaves in, and
            # reading it back would be a second scan of the namespace -
            # measured at 365 tags: 35 ms of listing around a 2 ms write.
            written_title, written_description = _version_words(fresh.message)
            return Version(
                name=name,
                revision=_as_text(fresh.object[1]),
                title=written_title,
                description=written_description,
                timestamp=fresh.tag_time,
            )

    @staticmethod
    def _tag_at_locked(repo, key: str, name: str):
        """One dashboard's tag by name, already under the lock. Ref and target.

        The two refusals shared by every caller that looks a tag up by
        name - `retitle_version`, `read_version`, `remove_version` - in
        one place rather than three: a ValueError carrying a sentence,
        the version is not this dashboard's or there is none by that
        name. `_owns` decides the first, the whole ownership fence: a
        command taking a bare ref name would otherwise reach any tag in
        the repository.

        Hands back the ref alongside the target, not the target alone.
        `remove_version` deletes exactly the ref this found, and a
        second `b"refs/tags/" + name.encode("utf-8")` at the call site -
        agreeing with this one only because both spell the same rule -
        is the one way its claim that the read and the delete are "one
        move on one ref" could quietly come apart.

        Called `_locked`, not because the lookup itself needs the lock -
        it takes `repo` as an argument and touches no shared state of
        its own - but because every caller of it already holds
        `self._lock` for a reason of its own (a preview that must not
        observe a half-finished write, a delete that must act on what it
        just read). Naming that here is cheaper than a caller
        rediscovering it by deadlocking on `self._lock`, which is a
        plain, non-reentrant `threading.Lock`.
        """
        if not _owns(name.encode("utf-8"), key):
            raise ValueError(f"not a version of {key}: {name}")
        ref = b"refs/tags/" + name.encode("utf-8")
        try:
            target = repo[repo.refs[ref]] if repo is not None else None
        except KeyError:
            target = None
        if target is None:
            raise ValueError(f"unknown version: {name}")
        return ref, target

    def read_version(self, key: str, name: str) -> Version:
        """One version of one dashboard, by name. Raises where there is none.

        The one-name counterpart to `list_versions`, and it exists for
        the *preview* of a removal: it has to show the words that are
        about to go, before anything goes. Read through the namespace
        instead and that is a scan of every tag this dashboard has to
        answer about one - measured at 365 versions, 35 ms of it. The
        second read, the one that answers with what went, is
        `remove_version`'s own and happens under the same lock as the
        delete; nothing here reads a ref twice.

        The lock is held for a read, which `list_versions` does not do.
        Said out loud, because the lock is documented as a serialiser of
        *writes*: what it buys here is that a preview cannot observe a
        half-finished write - a tag mid-rewrite, or a version mid-way
        through being retitled. The price is that a preview can queue
        behind a ~30 ms commit, and a dialog that is opening can afford
        that.

        The refusals are the same two `retitle_version` gives, in the
        same shape - a ValueError carrying a sentence: the version is not
        this dashboard's, or there is none by that name. Not a third for
        a lightweight tag: this only reads, and decision 13 says a
        hand-made tag stays visible.
        """
        # Two lines rather than a helper, and there used to be one here
        # calling itself "the read every locked caller goes through". It
        # had exactly one caller: `remove_version` deliberately does not
        # use it, because it needs the ref as well as the target. A
        # docstring inviting the next locked reader in would have sent
        # them somewhere that cannot give them the ref - and rebuilding
        # `b"refs/tags/" + name.encode(...)` at their own call site is
        # the one thing `_tag_at_locked` exists to prevent.
        with self._lock:
            _, target = self._tag_at_locked(self._repo(), key, name)
            return _version_from(name, target)

    def remove_version(self, key: str, name: str) -> Version:
        """Take one dashboard's version away. Answers what was taken.

        **The mark, never the state.** What goes is a ref. The commit it
        pointed at keeps standing, stays readable through its revision,
        keeps every note on it, and no other revision changes. Decision
        18 of the design record calls this the discard of decision 17
        made afterwards: there, choosing "discard" leaves a state in the
        history without a name, and this leaves it in exactly the same
        condition later on.

        Which is also why `forget` stays the only destructive operation
        in the sense the design record means. The rule it replaced its
        own wording with: what takes a *state* away is called `forget`,
        and it remains the one.

        No `_ensure()`, as `retitle_version` has none and for the same
        reason: this can only ever take away something that already
        exists, so a repository that is not there is an answer rather
        than a state to be built.

        **Both kinds of tag**, unlike renaming. A lightweight one cannot
        be *given* words - that would hand back a different kind of tag
        than the one somebody made - but it can be taken away, and it
        has to be. It counts when the next number is worked out, so one
        that could not be removed would hold a number for ever. The
        older reason is written into `_rewrite_tags` already: a tag
        operation that quietly skips the lightweight kind ends up
        silently ineffective, which is how `forget` once reported
        success while leaving the forgotten text in the object store.

        Neither `_index` nor `_survey` is dropped, and that is checked
        rather than assumed: both are keyed by HEAD and built from the
        commit walk, and neither reads `refs/tags`. `forget` drops them
        because it rewrites commits, which this does not.

        The old tag object stays behind as a loose object nothing points
        at - the same few hundred bytes `retitle_version` leaves, and for
        the same reason: pruning here would mean a full object-store walk
        per removal, and `forget`'s `garbage_collect` sweeps it up.

        Read before the delete and under the same lock, so the answer
        describes what was actually taken rather than what stood there a
        moment earlier. It is the caller's only copy: once the ref is
        gone, nothing in this integration can read those words again.

        The two refusals are `_tag_at_locked`'s, and they reach a caller
        from *this* call rather than from a read before it. That is what
        `operations` catches around the removal itself: between a
        preview and the confirmation the version can be gone - two
        removals at once, or a `forget` in between - and `services.py`
        catches nothing at all.
        """
        with self._lock:
            self._refuse_if_forget_pending()
            repo = self._repo()
            ref, target = self._tag_at_locked(repo, key, name)
            version = _version_from(name, target)
            del repo.refs[ref]
            return version

    def _marked_commit(self, revision: str | None) -> bytes:
        """The commit a version is about to be pinned to.

        Resolved here rather than left to `tag_create`, which takes any
        object at all: a blob id makes a tag that reads back as a version
        and can never be returned to. Such a tag can be taken away since
        decision 18, and it is still refused here - a version somebody
        has to create and then remove again is a fault, not a way of
        working. Refused as a ValueError, the same kind of answer a
        colliding name gives, so the one place that already catches those
        needs no second branch.
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
            self._refuse_if_forget_pending()
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

    def forget(
        self,
        key: str,
        progress: Callable[[str, int, int], None] | None = None,
    ) -> int:
        """Remove a dashboard's history for good. Returns commits removed.

        The only operation here that rewrites the stored history, in a
        tool built to stop things disappearing. It exists because a
        deleted dashboard stays in the list forever: delete one every few
        months and the list is mostly gravestones.

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

        `progress` is told which phase is starting and how far it has
        got, as `(phase, done, total)`. It exists because this operation
        is slow enough to look broken: measured on the test bench (7407
        commits, 782 versions) it takes 24 s, and a spinner that stands
        still that long is indistinguishable from one that is stuck -
        the reason somebody presses reload and finds a half-done
        rewrite. A plain callable rather than anything of Home
        Assistant's, so this module stays testable without it.
        """
        with self._lock:
            repo = self._repo()
            if repo is None:
                return 0
            self._refuse_if_forget_pending()
            if self._resolve(repo, "HEAD") is None:
                return 0
            if key not in set(self.list_all_dashboards()):
                return 0
            # Every revision from the first affected commit onwards is
            # about to change, so what was read at the old ones is worth
            # nothing. The survey would notice by itself - it is keyed by
            # HEAD and rebuilt whole - but the index carries itself
            # forward from the HEAD it knows, and forward is exactly what
            # a rewrite is not. Dropped before the rewrite, not after: a
            # failure halfway through must not leave one behind either.
            self._index = None
            self._survey = None
            try:
                return self._forget(repo, key, _Progress(progress))
            except FileLocked as exc:
                # `ensure()` clears a lock left by a *dead* process before
                # any call can reach here - see issue #19. What can still
                # arrive is the other case: an earlier `forget` in this
                # same, still-running process left one behind without
                # crashing.
                #
                # Which message applies depends on *where* the lock was
                # met, and on one more thing decision 21 added: whether a
                # checkpoint already exists. `_point_head` and
                # `_rewrite_notes` write only loose refs, never
                # `packed-refs.lock`; `_rewrite_tags` is the one call
                # that does, and it runs after both have already
                # succeeded - a lock met there always finds a checkpoint
                # already written (see `_forget`), so a restart finishes
                # the job. A lock met while preparing rewritten objects,
                # before the checkpoint exists, is different: nothing
                # clears an object lock synchronously (decision 21,
                # correction 5 - only `repair_pending_forget`'s sweep
                # does, once, from the background), so reaching here
                # means nothing was ever remembered, and a restart can
                # only promise to clear the lock eventually, not to
                # finish a request that never got far enough to be
                # written down.
                lockfile = os.fsdecode(exc.lockfilename)
                if key in set(self.list_all_dashboards()):
                    if self._checkpoint_path().exists():
                        raise ValueError(
                            "forget could not finish: a lock file from "
                            f"an earlier attempt is still in place "
                            f"({lockfile}). Nothing about {key} has "
                            "changed yet. Restart Home Assistant - the "
                            "interrupted rewrite finishes automatically "
                            "before recording resumes; nothing further "
                            "is required."
                        ) from exc
                    raise ValueError(
                        "forget could not finish: a lock file from an "
                        f"earlier attempt is still in place ({lockfile}). "
                        f"Nothing about {key} has changed yet, and "
                        "nothing was remembered to finish automatically. "
                        "Restart Home Assistant to clear the lock, then "
                        "call forget again."
                    ) from exc
                raise ValueError(
                    "forget could not finish: a lock file from an earlier "
                    f"attempt is still in place ({lockfile}), after {key} "
                    "was already removed from the history. Restart Home "
                    "Assistant - the interrupted rewrite finishes "
                    "automatically before recording resumes; nothing "
                    "further is required."
                ) from exc

    def repair_pending_forget(self) -> None:
        """Finish an interrupted `forget`, if one was left behind.

        Meant to be called from Home Assistant's background task ahead
        of the opening pass - never from the awaited `store.ensure` call
        in `async_setup_entry`, since this can cost several seconds
        (`garbage_collect` alone measured 4.5-6.6 s on the test bench,
        and the object-lock sweep below costs time proportional to the
        whole history's size) and nothing in that awaited path may cost
        Home Assistant's start. See decision 21, corrections 3 and 5.

        No "first attempt only" gate: `self._lock` is shared by every
        `HistoryStore` for this path within this process (decision 21,
        correction 4), so a second call - from a reload's fresh
        instance, or from this same one - simply waits for an earlier
        one to finish instead of racing it, and finds either a
        genuinely new checkpoint to repair or nothing left to do. Safe
        to call as many times as this runs, not just the first.

        A checkpoint that parses but carries an invalid sha, ref name
        or key is rejected the same way a structurally broken one is
        (decision 21, correction 7): `_validate_checkpoint_semantics`
        runs before `_finish_forget` is ever reached, so nothing here
        can apply a value `_rewrite_notes`, `_rewrite_tags` or
        `_drop_from_index` would only reject midway through a
        destructive rewrite.

        Whenever a checkpoint file is found at all - whatever is then
        decided about its contents - `_reconcile_index_with_head` runs
        first, before anything could delete that file, so a discarded
        checkpoint never leaves the index resurrecting a forgotten
        dashboard into HEAD on the next, unrelated write (decision 21,
        correction 7).
        """
        with self._lock:
            self._ensure()
            git_dir = self.path / ".git"
            if git_dir.exists():
                self._clear_stale_object_locks(git_dir)
            repo = self._repo()
            if repo is None:
                return
            if self._checkpoint_path().exists():
                self._reconcile_index_with_head(repo, self._best_effort_checkpoint_key())
            checkpoint = self._read_checkpoint()
            if checkpoint is None:
                return
            key, head, notes, tags = checkpoint
            try:
                self._validate_checkpoint_semantics(repo, key, head, notes, tags)
            except ValueError as exc:
                _LOGGER.exception(
                    "Removed a forget checkpoint with an invalid value: "
                    "%s. An interrupted forget could not be finished "
                    "automatically.",
                    exc,
                )
                try:
                    self._checkpoint_path().unlink(missing_ok=True)
                except OSError:
                    _LOGGER.exception(
                        "Could not remove invalid checkpoint %s",
                        self._checkpoint_path(),
                    )
                return
            self._index = None
            self._survey = None
            self._finish_forget(repo, key, head, notes, tags, _Progress(None))

    def _forget(self, repo: Repo, key: str, say: _Progress) -> int:
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

        say("rewriting", 0, len(order))
        for position, commit in enumerate(order):
            say.every(200, "rewriting", position, len(order))
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

        head = nearest.get(order[-1].id) if order else None
        note_targets = {
            kept[old.encode()]: text.encode("utf-8")
            for old, text in notes.items()
            if kept.get(old.encode()) is not None
        }
        tag_targets = self._planned_tag_changes(repo, versions, nearest, Tag, key)

        # Written before any ref moves - `_point_head` is the first of
        # the three steps below. From here on, `.git/dashboard_history_
        # forget.json` is the one true record of what this call is about
        # to finish, for this call and for any later repair alike. See
        # decision 21.
        self._write_checkpoint(key, head, note_targets, tag_targets)
        self._finish_forget(repo, key, head, note_targets, tag_targets, say)
        return removed

    def _finish_forget(
        self,
        repo: Repo,
        key: str,
        head: bytes | None,
        notes: dict[bytes, bytes],
        tags: dict[bytes, bytes | None],
        say: _Progress,
    ) -> None:
        """Move every ref to its planned target, then clean up.

        Shared by the call that just computed `head`/`notes`/`tags` and
        by `repair_pending_forget`, which reads the same three values
        back from the checkpoint after an interruption - see decision
        21. Every step here is safe to redo: `_point_head` sets a ref
        outright, `_rewrite_notes` rebuilds `refs/notes/commits` whole
        from `notes` every time, `_rewrite_tags` merges `tags` into
        whatever tags exist now, and `_drop_from_index` and
        `garbage_collect` already tolerated being run more than once
        before this existed. The checkpoint is deleted last, deliberately
        - if anything below raises, it stays in place and the next
        attempt starts this method over rather than guessing which
        parts already happened. Callers cannot collide while doing so:
        both the original call and any repair run under the one lock
        `HistoryStore` now shares per repository path (decision 21,
        correction 4).
        """
        self._point_head(repo, head)
        self._rewrite_notes(repo, notes)
        self._rewrite_tags(repo, tags)
        self._drop_from_index(repo, key)

        # Rewriting refs only makes the old objects unreachable; the blobs
        # and commits stay on disk, and `resolve` still finds them. Without
        # this, "forgotten for good" would be a claim the repository
        # contradicts. The grace period is zero on purpose - the usual
        # fourteen days protect objects another writer may be building, and
        # the only other writer here is this class, holding the lock this
        # method runs under. That leaves one gap a grace period cannot
        # close: a *past* writer, no longer holding anything, whose
        # `write_snapshot` staged a blob and then failed before
        # `porcelain.commit` - the index still names it, no ref ever did.
        # `_garbage_collect_protecting_index` closes that one. See issue
        # #25.

        # No counting here: the collection walks the object store on its
        # own and reports nothing back. A phase name without numbers is
        # still worth saying - it is a fifth of the wait.
        say("cleaning", 0, 0)
        self._garbage_collect_protecting_index(repo)

        # The rewrite above moves refs without passing dulwich a message,
        # so none of it adds a reflog line - but every ordinary commit
        # before it did, and those lines outlive the objects they name:
        # the collection just above only prunes what refs and notes point
        # to. Nothing in this project reads `.git/logs` (it exists for
        # git's own tooling, which this integration never shells out to),
        # so there is nothing to preserve - and dulwich recreates whatever
        # reflog file it next needs to write to. See issue #21.
        #
        # Only a missing directory is tolerated here - the ordinary case,
        # since a freshly created repository has no reflog yet. Anything
        # else (no permission, a read-only filesystem) is a real failure
        # and stays visible instead of vanishing behind `ignore_errors`.
        # Decision 21 made this safe to leave as a logged-and-swallowed
        # failure rather than something that must also be resumable: the
        # checkpoint is still deleted below either way, since nothing in
        # this project reads the reflog and there is therefore nothing
        # left to repair.
        try:
            shutil.rmtree(self.path / ".git" / "logs")
        except FileNotFoundError:
            pass
        except OSError:
            _LOGGER.exception("Could not clear the reflog after forgetting %s", key)
        self._checkpoint_path().unlink(missing_ok=True)

    @staticmethod
    def _garbage_collect_protecting_index(repo: Repo) -> None:
        """`garbage_collect(repo, prune=True, grace_period=0)`, except a
        blob the index still stages is never pruned.

        `dulwich.gc.garbage_collect` has no argument for this - its
        reachability walk works from refs alone, exactly like the
        default `grace_period` comment above already relies on. Run
        after `_drop_from_index`, so a key just forgotten is out of the
        index by the time this reads it and stays exactly as unprotected
        as before; run against the *whole* index, not just the key
        being forgotten, since `porcelain.commit` always commits the
        whole index and any dashboard's still-staged, uncommitted save
        can be the one this sweep would otherwise destroy. See issue
        #25.

        Repairs nothing: an index entry whose blob an earlier,
        unprotected run already pruned stays broken. This only stops it
        from happening again.
        """
        from dulwich.gc import find_unreachable_objects  # noqa: PLC0415

        object_store = repo.object_store
        staged = {sha for _path, sha, _mode in repo.open_index().iterobjects()}
        to_prune = find_unreachable_objects(object_store, repo.refs) - staged

        repo.refs.pack_refs()
        for sha in to_prune:
            if object_store.contains_loose(sha):
                try:
                    object_store.delete_loose_object(sha)
                except OSError:
                    pass
        # Same set as the loose deletion above, on purpose: a blob
        # already packed from an earlier, harmless repack is just as
        # unreachable, and `repack`'s own `exclude` is the only place
        # that actually drops it.
        object_store.repack(exclude=to_prune)
        object_store.prune(grace_period=0)

    def _drop_from_index(self, repo: Repo, key: str) -> None:
        """Take the dashboard's two files out of the index and off the disk.

        The rewrite above touches commits, refs and notes - not the index,
        and not the working tree. Left alone, both still name the files
        whenever `forget` runs while the dashboard is in HEAD, which the
        operations layer allows: it asks Home Assistant whether the
        dashboard is gone, not the recorder whether the deletion has been
        written yet. The next commit of any dashboard then builds its tree
        from that index and references blobs the collection below has
        just pruned. Measured on 2026-09-04: a dashboard back from the
        dead in HEAD, and every read of its path a KeyError.
        """
        index = repo.open_index()
        for path in (f"{key}.yaml", f"meta/{key}.yaml"):
            if path.encode() in index:
                del index[path.encode()]
            (self.path / path).unlink(missing_ok=True)
        index.write()

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
    def _each_tag(repo: Repo, key: str | None = None):
        """Every tag ref with the object behind it, as `(ref, object)`.

        A ref listed a moment ago and gone now is skipped. `forget`
        deletes every tag and writes it back, and reads are not held off
        while it does; measured on 2026-09-04, a history request in that
        window failed whole on one vanished ref. Skipping it is what
        dulwich's own `as_dict` does with an unresolvable ref.

        `key` narrows it to one dashboard's versions, and it narrows
        *before* the object is loaded. That order is the whole point:
        the automatic versions of project H put one tag per dashboard
        per day into this repository, without a ceiling, and a caller
        that wanted one dashboard's used to pay for reading every
        object in the namespace. Measured on 2026-09-05 over ten
        dashboards: reading one dashboard's versions cost 1.9 ms at ten
        tags in the repository and 492 ms at 3650 - a year of them -
        rising in a straight line with tags that have nothing to do
        with the question.
        """
        for ref in repo.refs.as_dict(b"refs/tags"):
            if key is not None and not _owns(ref, key):
                continue
            try:
                yield ref, repo[repo.refs[b"refs/tags/" + ref]]
            except KeyError:
                continue

    @classmethod
    def _raw_tags(cls, repo: Repo) -> list:
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
        for ref, tag in cls._each_tag(repo):
            annotated = hasattr(tag, "object")
            found.append((ref, tag if annotated else None,
                          tag.object[1] if annotated else tag.id))
        return found

    def _rewrite_notes(self, repo: Repo, targets: dict[bytes, bytes]) -> None:
        """Put the descriptions back on the commits that survived.

        Takes the already-flattened `{new commit sha: note text}` this
        dashboard's forgetting leaves behind, rather than the raw notes
        and the old-to-new commit mapping separately - the flattening
        used to happen inline here, but decision 21 needs the flattened
        form on its own, to checkpoint it and to hand the exact same
        mapping to a later repair. Deleting the ref first and rebuilding
        it whole makes this safe to call twice: a repair that redoes this
        after a partial first attempt ends at the same content either way.
        """
        if b"refs/notes/commits" in repo.refs:
            del repo.refs[b"refs/notes/commits"]
        for new, text in targets.items():
            porcelain.notes_add(
                str(self.path),
                new,
                text,
                author=_IDENTITY,
                committer=_IDENTITY,
            )

    @staticmethod
    def _planned_tag_changes(
        repo: Repo,
        versions: list,
        nearest: dict[bytes, bytes | None],
        tag_class,
        key: str,
    ) -> dict[bytes, bytes | None]:
        """Decide the final `{ref: sha or None}` this dashboard's tags need.

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

        Stops short of writing the result anywhere: the new tag *objects*
        this creates for annotated tags are written to the object store
        immediately below, since they are content-addressed and harmless
        to write early, but the returned mapping is exactly what decision
        21 checkpoints and what `_rewrite_tags` later applies in one
        `add_packed_refs` call - kept apart so a repair can replay just
        that call without recreating a single object.
        """
        changed: dict[bytes, bytes | None] = {}
        for ref, old, target in versions:
            name = b"refs/tags/" + ref
            if _owns(ref, key):
                # This dashboard's own version, forgotten with it. Since
                # decision 13 a version belongs to one dashboard, and
                # carrying it onto a surviving ancestor left `gone/v1.0.0`
                # sitting on a stranger's commit (measured 2026-09-02).
                changed[name] = None
                continue
            moved = nearest.get(target)
            if moved is None:
                changed[name] = None  # nothing left for it to mark
                continue
            if old is None:
                # A lightweight tag has no object to rebuild - the ref IS
                # the tag - so it is re-pointed. Inventing a tag object
                # would hand somebody back a different kind than the one
                # they made.
                changed[name] = moved
                continue
            fresh = tag_class()
            fresh.object = (old.object[0], moved)
            fresh.name = old.name
            fresh.message = old.message
            fresh.tagger = old.tagger
            fresh.tag_time = old.tag_time
            fresh.tag_timezone = old.tag_timezone
            repo.object_store.add_object(fresh)
            changed[name] = fresh.id
        return changed

    @staticmethod
    def _rewrite_tags(repo: Repo, changed: dict[bytes, bytes | None]) -> None:
        """Apply a plan from `_planned_tag_changes` in one write.

        One write for all of them. `del repo.refs[...]` rewrites the
        whole `packed-refs` file and renames it into place, once per
        mark; the assignment after it writes a loose file and fsyncs
        that. Measured 2026-09-18 on the test bench with 782 packed
        marks: 11.1 ms and 5.5 ms each, 12.46 s together, against
        0.02 s for the single call below.

        `add_packed_refs` takes the whole mapping at once, and a target
        of `None` removes that ref - exactly the two things this method
        does. It also unlinks any loose ref of the same name, so both
        shapes are covered without asking which one a mark has. It also
        merges: any tag *not* named in `changed` is left exactly as it
        stood, which is what makes this safe for `repair_pending_forget`
        to replay even after other tags were created since the plan was
        made.

        Empty is not a special case for `add_packed_refs`; it returns at
        once. Said here because a repository without a single mark is
        the ordinary case for a young installation.
        """
        repo.refs.add_packed_refs(changed)

    # -- reading -------------------------------------------------------

    def _repo(self) -> Repo | None:
        if not (self.path / ".git").exists():
            return None
        return Repo(str(self.path))

    def list_changes(
        self, key: str, limit: int | None = 50, before: str | None = None
    ) -> list[Change]:
        """Every recorded state of one dashboard, newest first.

        `limit=None` walks the whole history. `before` starts the walk one
        step past that revision - the entry it names is not repeated, so a
        caller can page without stitching duplicates together. A cursor
        rather than an offset because an offset drifts: save while somebody
        is paging and every later page shifts by one.

        A `before` that is no change of this dashboard - another
        dashboard's commit, HEAD - starts the walk at the newest change
        older than it. An unknown `before` yields nothing: asking about a
        revision that is gone is not an error, and `matching_revisions`
        takes the same line.

        A list, and the signature says so: every caller here wants one,
        and a page of fifty is a list whatever it is built from. The
        walk underneath is `_each_change`, which hands them over one at
        a time; the slice is what turns the extra look-ahead entry back
        into the page that was asked for.

        Rebuilt whole, up to `_FORGET_RACE_RETRIES` times, if a
        concurrent `forget` pruned a commit this walk already held a
        revision for - see `_retrying_a_forget_race` and decision 24.
        """
        repo = self._repo()
        if repo is None:
            return []

        def build() -> list[Change]:
            found = self._each_change(repo, key, limit, before)
            # Sliced after the walk, so the extra entry did its one job -
            # being the predecessor of the last one - and then goes.
            return list(found) if limit is None else list(islice(found, limit))

        return self._retrying_a_forget_race(repo, build)

    def _each_change(
        self, repo: Repo, key: str, limit: int | None = 50, before: str | None = None
    ) -> Iterator[Change]:
        """The same walk as `list_changes`, one `Change` at a time.

        Every entry the walk produces, including the look-ahead one -
        the caller decides how many it wants. `list_changes` slices;
        `search_changes` stops as soon as it has enough matches, and
        that is the whole reason this is a generator.

        The saving is real because dulwich's walker is lazy too, so
        nothing behind the point a caller stops at is ever read.
        Measured on 2026-09-05 against a repository of 1002 commits over
        five dashboards, 201 of them this dashboard's: walked to the end
        it cost 468 ms as a generator and 481 ms as the list it used to
        build, the same within the noise - the laziness is free even
        when it saves nothing. A search that stops at its first ten
        matches cost 24.5 ms against 470 ms, and one that stops at the
        first, 5.0 ms.

        One entry is held back at a time, and that is what `previous`
        costs: an entry cannot be handed out until the next one is
        known, because the next one *is* its predecessor. The last entry
        of the walk has nobody behind it and answers None, which is what
        "the oldest recorded state" means.

        Takes `repo` from its caller rather than opening its own: both
        callers now need it themselves too, for `_retrying_a_forget_race`
        (decision 24) - a second `Repo(...)` here would only cost an
        extra file handle for nothing.
        """
        notes = self.descriptions()
        revisions = self._indexed_revisions(repo, key, before)
        if revisions is not None:
            for position, revision in enumerate(revisions):
                following = (
                    revisions[position + 1]
                    if position + 1 < len(revisions)
                    else None
                )
                yield _change(repo[revision.encode()], notes, following)
            return
        yield from self._walked_changes(repo, key, notes, limit, before)

    def _current_head(self, repo: Repo) -> object:
        """HEAD right now, or a value that never equals a previous
        observation if reading it itself raced a `forget`.

        `_resolve` dereferences an object internally (`obj = repo[sha]`
        near its end), unguarded - a `forget` that prunes exactly what
        it is about to read can make even this fail with the same two
        exceptions `_retrying_a_forget_race` exists to survive.
        Answering `None` for that would be wrong: two failed
        observations would then compare equal to each other, and a
        real, ongoing race would go undetected. A fresh `object()`
        compares equal to nothing but itself. See decision 24.
        """
        try:
            return self._resolve(repo, "HEAD")
        except (KeyError, MissingCommitError):
            return object()

    def forget_in_progress(self) -> bool:
        """Whether an earlier `forget` has not finished cleaning up yet.

        The same checkpoint file write paths already refuse against
        (`_refuse_if_forget_pending`, decision 21) - reads use it too
        now, to know when a result might mix two generations of the
        repository. Present for the *whole* span of `_finish_forget`,
        from before HEAD moves to after garbage collection - catches
        a read that starts after HEAD already settled but before
        notes/tags catch up, which a HEAD comparison alone cannot see
        (issue #27). Public: `operations.async_search`'s own retry
        (decision 24) reads it too, from outside this module.
        """
        return self._checkpoint_path().exists()

    def _retrying_a_forget_race(
        self, repo: Repo, build: Callable[[], list[Change]]
    ) -> list[Change]:
        """Run `build`, rebuilding it whole if it raced a `forget`.

        `build` must read everything it needs itself, fresh, every time
        it runs - a retry here discards whatever a failed attempt had
        already produced rather than resuming it. Necessary, not just
        cautious: `forget` gives every surviving commit downstream of
        the earliest touched point a new sha (`_forget`, `store.py`),
        so a walk resumed at the point it broke would not even be a
        valid continuation of the same answer, let alone a correct one.

        A result is trusted - whether `build()` raised or returned
        normally - only if, checked right after, HEAD reads the same
        as it did when this attempt began *and* `forget_in_progress()`
        is false. Checking only on failure would miss a `forget` that
        completes entirely between two separate reads inside one
        `build()` (`descriptions()` then the walk, in `_each_change`;
        `list_versions()` then `search_changes()`, one layer up in
        `operations.py`) - neither individually raises, so nothing
        would ever trigger a retry, yet the result quietly mixes two
        generations. The checkpoint check catches what HEAD alone
        cannot: a read that starts after HEAD already moved but before
        notes or tags catch up sees a HEAD that never moves again
        during its own execution at all. See decision 24.

        Commit shas are content hashes over tree and parents, so HEAD
        can never cycle back to a value already seen; combined with
        the fixed budget below, this always terminates regardless of
        how unsettled the repository stays.
        """
        head = self._current_head(repo)
        for _ in range(_FORGET_RACE_RETRIES - 1):
            try:
                found = build()
            except (KeyError, MissingCommitError):
                moved = self._current_head(repo)
                if moved == head and not self.forget_in_progress():
                    raise
                head = moved
                continue
            moved = self._current_head(repo)
            if moved == head and not self.forget_in_progress():
                return found
            head = moved
        return build()

    def _walked_changes(
        self,
        repo: Repo,
        key: str,
        notes: dict,
        limit: int | None,
        before: str | None,
    ) -> Iterator[Change]:
        """`_each_change` the long way, by walking the history itself.

        What this class did everywhere until the index arrived, kept for
        the one question the index cannot answer: a `before` naming a
        commit that is not in the walk at all. A cursor from a history
        that has since been rewritten is such a commit - it still
        resolves, and the walk from it still has ancestors to hand back.
        """
        # Both paths: a rename touches only the metadata, and a change
        # that is recorded but never shown is the worst of both.
        paths = [f"{key}.yaml".encode(), f"meta/{key}.yaml".encode()]
        walk: dict = {"paths": paths}
        cursor: bytes | None = None
        if before is not None:
            resolved = self._resolve(repo, before)
            if resolved is None:
                return
            # `include` walks *from* that commit and hands the commit
            # itself back first - but only if it touches these paths. A
            # cursor from another dashboard is not in the list at all,
            # so the first entry is dropped only when it *is* the cursor.
            # Same guard as `previous_change`.
            cursor = resolved.encode()
            walk["include"] = [cursor]
        if limit is not None:
            # One more than asked for, so the last entry handed out
            # knows its predecessor. With a cursor, two more: the cursor
            # entry is dropped again below, and when the cursor names a
            # commit of some other dashboard there is nothing to drop -
            # one entry more than needed is read, never one too few.
            walk["max_entries"] = limit + 2 if cursor is not None else limit + 1
        try:
            walker = repo.get_walker(**walk)
        except KeyError:
            # No HEAD yet: an empty repository has no history to walk.
            # Measured: dulwich resolves `include` while the walker is
            # built, so this arrives here and not halfway through.
            return
        held = None
        first = True
        for entry in walker:
            if first:
                first = False
                if cursor is not None and entry.commit.id == cursor:
                    continue
            if held is not None:
                # The next entry of this same walk. The walk is already
                # filtered on this dashboard's paths, so it is this
                # dashboard's own predecessor and never the commit's
                # parent, which may belong to somebody else entirely.
                yield _change(held.commit, notes, _as_text(entry.commit.id))
            held = entry
        if held is not None:
            yield _change(held.commit, notes, None)

    def _revision_index(self, repo: Repo) -> RevisionIndex | None:
        """Which commits touched which dashboard, built once per HEAD.

        The reason this exists: every dashboard shares one repository,
        so a walk filtered on one dashboard's paths still steps over
        every commit the others made, diffing each against its parent
        to find out. The filter stops the entries coming out, never the
        work going in. A dashboard with fewer changes than the page asks
        for never reaches `max_entries` either, so it reads the history
        to its very first commit to hand back four rows.

        That cost is the *other* dashboards', and it grows as they are
        added. Measured on the test bench on 2026-09-07, 45 dashboards
        over 4454 commits: one page of `dh-probe` cost 7.2 s inside the
        Home Assistant container, and the panel asks for a page and a
        survey on every switch.

        One walk answers it for every dashboard at once, and the answer
        holds until HEAD moves. Keyed by HEAD like `_survey` and for the
        same reason - a rewrite moves every revision from the first
        affected commit onwards, and a stale index would hand back
        revisions that no longer exist.
        """
        head = self._resolve(repo, "HEAD")
        if head is None:
            return None
        cached = self._index
        if cached is not None and cached.head == head:
            return cached
        found = None
        if cached is not None:
            found = self._extended_index(repo, cached, head)
        if found is None:
            found = self._built_index(repo, head)
        self._index = found
        return found

    @staticmethod
    def _built_index(repo: Repo, head: str) -> RevisionIndex:
        """The index from nothing: one walk over the whole history.

        The whole history, not the newest thousand commits. Capped, a
        dashboard deleted a thousand saves ago would leave the panel's
        list and could no longer be forgotten, silently - the invisible
        gap this module exists to prevent.
        """
        by_key: dict[str, list[str]] = {}
        order: dict[str, int] = {}
        names: set[str] = set()
        removed_meta: dict[str, bytes] = {}
        for position, entry in enumerate(repo.get_walker()):
            revision = _as_text(entry.commit.id)
            order[revision] = position
            touched = _touched(entry)
            for key in touched.keys:
                by_key.setdefault(key, []).append(revision)
            names |= touched.names
            # Newest first, so the first removal seen of a key is the
            # last one that happened - which is the one wanted.
            for key, blob in touched.removed_meta.items():
                removed_meta.setdefault(key, blob)
        return RevisionIndex(head, by_key, order, names, removed_meta)

    @staticmethod
    def _extended_index(
        repo: Repo, cached: RevisionIndex, head: str
    ) -> RevisionIndex | None:
        """The cached index carried forward to `head`, or None.

        None means "cannot be carried forward, build it again". Every
        save moves HEAD, so without this the index would be rebuilt on
        every recording and cost more than the walk it replaced.

        Two ways to end up with None, and both have to stay: the old
        HEAD may be gone entirely, and it may still be there without
        being an ancestor - `forget` rewrites history, and then what is
        cached describes commits that no longer exist. The second is
        caught by the commit that arrives already known, because
        `exclude` prunes nothing on a branch it is not on.
        """
        fresh: list[tuple[str, _Touched]] = []
        try:
            walker = repo.get_walker(
                include=[head.encode()], exclude=[cached.head.encode()]
            )
            for entry in walker:
                revision = _as_text(entry.commit.id)
                if revision in cached.order:
                    return None
                fresh.append((revision, _touched(entry)))
        except (KeyError, MissingCommitError):
            # The old HEAD is not there any more. dulwich raises this
            # while the walker is built or while it runs, depending on
            # where the missing commit is reached, so both are caught in
            # one place. `forget` drops the index before it rewrites and
            # never gets here; this is for whatever else takes a commit
            # out from under a running store - a repository somebody
            # tidied by hand, most likely.
            return None
        if not fresh:
            # HEAD moved without adding anything ahead of the old one:
            # it went backwards, or sideways. Neither is an extension.
            return None
        # Everything already indexed slides back by what arrived in
        # front of it, so position keeps meaning "how far from newest".
        order = {
            revision: position + len(fresh)
            for revision, position in cached.order.items()
        }
        arrived: dict[str, list[str]] = {}
        names = set(cached.names)
        removed_meta: dict[str, bytes] = {}
        for position, (revision, touched) in enumerate(fresh):
            order[revision] = position
            for key in touched.keys:
                # `fresh` is newest first, so appending here keeps these
                # in that order and they go in front as a block.
                arrived.setdefault(key, []).append(revision)
            names |= touched.names
            for key, blob in touched.removed_meta.items():
                removed_meta.setdefault(key, blob)
        by_key = dict(cached.by_key)
        for key, revisions in arrived.items():
            by_key[key] = revisions + by_key.get(key, [])
        # What arrived is newer than what was cached, so it wins - a
        # dashboard deleted twice is remembered by its second deletion.
        return RevisionIndex(
            head, by_key, order, names, {**cached.removed_meta, **removed_meta}
        )

    def _indexed_revisions(
        self, repo: Repo, key: str, before: str | None
    ) -> list[str] | None:
        """One dashboard's revisions from the index, newest first.

        Three answers, and the difference between two of them matters:
        a list is what to hand out, the empty list is "nothing to hand
        out", and None is "the index cannot answer this" - only then
        does the caller walk.
        """
        index = self._revision_index(repo)
        if index is None:
            return None
        revisions = index.by_key.get(key, [])
        if before is None:
            return revisions
        resolved = self._resolve(repo, before)
        if resolved is None:
            # An unknown `before` yields nothing, as the docstring of
            # `list_changes` promises - not a walk that finds plenty.
            return []
        at = index.order.get(resolved)
        if at is None:
            # Resolves, but is not in this walk: outside the index's
            # reach, so let the walk answer it.
            return None
        return [r for r in revisions if index.order[r] > at]

    def search_changes(
        self,
        key: str,
        text: str,
        limit: int = 50,
        versions: list[Version] | None = None,
    ) -> list[Change]:
        """Recorded states of one dashboard whose words hold `text`.

        The whole history, not the page a caller happens to hold, and
        that is the entire point. The panel searches what it has loaded
        first because that answers without a round trip; it asks this
        only when that found nothing, and at that moment "nothing" has
        to mean nothing - not "nothing among the newest twenty-five".

        Matched against four things, ignoring case: the generated
        message, a person's own description, and the title, description
        and number of every version sitting on that state. One word
        finds either kind, because somebody searching for words they
        remember writing does not remember which of the two places they
        wrote them in.

        Of a version's name only the number counts - `home/v1.0.0` is
        searched as `v1.0.0`. The namespace is the dashboard's own key,
        and that is also the word a person uses for the dashboard, so
        searching it would make every version of it a hit for a word
        that says nothing.

        The panel matches the same four things over what it has already
        loaded, so that the common search costs no round trip, and asks
        this only when that found nothing. Two copies of one rule:
        `tests/test_panel_assets.py` reads both sides and compares the
        fields, so adding one here alone goes red rather than quiet.

        One difference between the copies is real. Case is folded here
        and only lowercased there, because JavaScript has no casefold:
        `strasse` finds a row saying `Straße` in this method and misses
        it in the panel. That is the harmless direction - a miss up
        there escalates and arrives here, which then finds it - and it
        is the only harmless one, because a hit up there that this
        method would not have made stands as the whole answer with
        nothing to correct it.

        An empty search finds nothing rather than everything. It is the
        state of a search box somebody has just cleared, and answering
        it with the whole history is the opposite of what that means.

        `versions` is this dashboard's tag list, for a caller that has
        already read it. `operations.async_search` has: it needs the
        same list to say which versions sit on the rows it hands back,
        and without this it read it once and this method read it again,
        two scans of the same tags for one answer. Left out, the list is
        read here as before, which is what every test and every other
        caller relies on.

        Retried whole, like `list_changes`, when this method fetched
        `versions` itself - it owns every input and a rebuild is safe.
        When `versions` came from the caller, retrying here would not
        be: `operations.async_search` also derives its own `marks` from
        that same list, outside this method's reach, and a rebuild here
        would hand back new shas against `marks` still naming the old
        ones - every version match failing with nothing to say why. The
        error propagates unhandled in that case instead; the one caller
        that supplies `versions` retries its own whole sequence around
        this call. See decision 24.
        """
        needle = text.strip().casefold()
        if not needle:
            return []
        repo = self._repo()
        if repo is None:
            return []
        given_versions = versions is not None

        def build() -> list[Change]:
            active_versions = versions if given_versions else self.list_versions(key)
            marks: dict[str, list[Version]] = {}
            for version in active_versions:
                marks.setdefault(version.revision, []).append(version)
            found: list[Change] = []
            # The walk is unbounded and is the expensive part: measured at
            # roughly half a second per thousand commits. It runs in an
            # executor, and only after a local search found nothing.
            #
            # `_each_change` rather than `list_changes(key, None)`, so the
            # limit bounds the work and not only the answer. Built as a list
            # first, the whole history of the dashboard was materialised
            # before the first comparison was made - the `break` below then
            # only stopped the reading of something already in memory.
            for change in self._each_change(repo, key, None):
                words = [change.message, change.description]
                for version in marks.get(change.revision, []):
                    # The description as a reader sees it. Stored, it can
                    # carry the marker that says a version was made
                    # automatically, and that marker is words: searching
                    # `automatic`, `history` or `dashboard` would otherwise
                    # return every automatically versioned state, for a
                    # sentence nobody wrote and nobody is shown. Every other
                    # way out of here strips it; this was the one that did
                    # not.
                    said, _ = versioning.read_description(version.description)
                    words += [
                        version.name.rsplit("/", 1)[-1],
                        version.title,
                        said,
                    ]
                if needle in "\n".join(words).casefold():
                    found.append(change)
                    if len(found) >= limit:
                        break
            return found

        if given_versions:
            return build()
        return self._retrying_a_forget_race(repo, build)

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

        One step along the list the index already holds, which is what
        the question actually is. It used to be walked from the change
        itself, filtered on the dashboard's paths and two entries deep -
        fast only while those two entries sit close together. A
        dashboard with little history of its own has them far apart,
        with every other dashboard's commits in between, and the walk
        steps over all of them. Measured on the test bench on
        2026-09-07, 45 dashboards over 4454 commits: the current state
        of `dh-probe` (77 entries) took 2637 ms, a long-running board of
        673 entries 53 ms. Less history of your own meant a longer wait.

        The walk is kept for the one case the index cannot answer: a
        revision that resolves but is not in this walk at all.

        None when `revision` is not a change of this dashboard at all:
        the entry before it is then some earlier change of it, and
        calling that the predecessor of a stranger would be wrong.
        """
        repo = self._repo()
        if repo is None:
            return None
        full = self._resolve(repo, revision)
        if full is None:
            return None
        index = self._revision_index(repo)
        if index is not None and full in index.order:
            revisions = index.by_key.get(key, [])
            try:
                at = revisions.index(full)
            except ValueError:
                return None
            return revisions[at + 1] if at + 1 < len(revisions) else None
        try:
            walker = repo.get_walker(
                include=[full.encode()],
                paths=[f"{key}.yaml".encode(), f"meta/{key}.yaml".encode()],
                max_entries=2,
            )
            found = [_as_text(entry.commit.id) for entry in walker]
        except (KeyError, MissingCommitError):
            # `full` resolved a moment ago, pruned by a concurrent
            # `forget` since - see decision 24. Same answer as a
            # revision the walk never reaches.
            return None
        if len(found) == 2 and found[0] == full:
            return found[1]
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
            # accepts it and leaves a tag nobody can ever return to.
            # (That clause used to end "which nothing can delete
            # again"; since decision 18 something does, and the refusal
            # stands on such a tag being useless rather than on being
            # stuck with it.) `None` already means "unknown revision"
            # to every caller here, and every one of them
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
        blob_id = cls._blob_at(repo, path, revision)
        if blob_id is None:
            return None
        return repo[blob_id].data.decode("utf-8")

    @classmethod
    def _blob_at(cls, repo: Repo, path: str, revision: str) -> bytes | None:
        """The id of the blob one path holds at one revision, or None.

        The id, not the content. git names a blob by its bytes, so two
        revisions hold the same file exactly when this answers the same
        id twice - and that is one tree lookup against reading, decoding
        and comparing two whole dashboards.

        None has three meanings and none of them is an error: the
        revision is unknown, it is not a commit, or the path is not in
        its tree. The last is the ordinary case for a dashboard that did
        not exist yet.

        Takes the path as text like `_read_from` does, rather than as the
        bytes git wants: two sibling helpers that disagree about that are
        an encode a caller forgets, and `lookup_path` answers a forgotten
        one with a KeyError that reads like a missing file.
        """
        resolved = cls._resolve(repo, revision)
        if resolved is None:
            return None
        try:
            tree = repo[repo[resolved.encode()].tree]
            _, blob_id = tree.lookup_path(repo.get_object, path.encode())
        except KeyError:
            return None
        return blob_id

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
        # By blob id, not by content: git names a blob by its bytes, so
        # the id of `text` is the id every matching revision points at.
        # Reading and decoding fifty blobs of a large dashboard to compare
        # them was the alternative.
        from dulwich.objects import Blob  # noqa: PLC0415

        wanted = Blob.from_string(text.encode("utf-8")).id
        path = f"{key}.yaml"
        same: set[str] = set()
        # Deduplicated: two versions may sit on one commit, and a version
        # may sit on a change that is loaded beside it, so the same
        # revision can arrive several times. Each repeat costs a resolve
        # and a tree read for an answer the set already holds. `fromkeys`
        # rather than `set` because it keeps the caller's order, and an
        # answer that depends on dict ordering is a bad answer to debug.
        for revision in dict.fromkeys(revisions):
            if self._blob_at(repo, path, revision) == wanted:
                same.add(revision)
        return same

    def same_state(self, key: str, one: str, other: str) -> bool:
        """Whether two revisions hold exactly the same state of a dashboard.

        Asked before an automatic version is made. A day mark is worked
        out from the calendar, so a dashboard that is changed and changed
        back collects one mark per day all sitting on the same content -
        rows the panel cannot even offer a button on, because going back
        to them would change nothing.

        The question is a general one, and older than that caller:
        decision 13 of the design record names "a comparison the panel
        does not have" as the reason the create dialog can only say
        "identical in content" about the *live* state. This is that
        comparison. Anything that wants the same answer belongs here
        rather than in a second method beside it.

        This dashboard's configuration decides and nothing else. The
        metadata travels in the same commit, so a dashboard renamed with
        its cards left alone is the *same state* by this answer - which
        is right for the caller it has: restoring an existing dashboard
        writes the configuration and never the metadata, so a version
        marking such a commit could not put the old name back either.

        False where either revision cannot be read, and deliberately so.
        An unknown revision has nothing to compare, and "nothing to
        compare" must not arrive at a caller as "nothing changed".
        """
        repo = self._repo()
        if repo is None:
            return False
        path = f"{key}.yaml"
        first = self._blob_at(repo, path, one)
        return first is not None and first == self._blob_at(repo, path, other)

    def commit_times(self, revisions: Iterable[str]) -> dict[str, int]:
        """When each of these revisions was recorded, by the name asked for.

        Keyed by what the caller handed in rather than by what it
        resolves to, so a caller can look its own answer up: a version
        name and the commit behind it are the same state under two
        names, and only one of them is on the caller's list.

        A revision that cannot be read is left out rather than answered
        with a zero. The caller reads a calendar day out of this, and a
        zero would arrive there as the first of January 1970 - a day
        like any other to a comparison, and one no state was ever
        recorded on.

        Its caller is the day mark, which has to know which day each
        automatic version is about. Not folded into `list_versions`,
        which every panel click runs: this loads one commit object per
        entry, and paying for that on the hot path to serve a check that
        happens once a day is the trade `_marks_by_revision` warns about.
        """
        repo = self._repo()
        if repo is None:
            return {}
        found: dict[str, int] = {}
        for revision in dict.fromkeys(revisions):
            resolved = self._resolve(repo, revision)
            if resolved is None:
                continue
            try:
                found[revision] = repo[resolved.encode()].commit_time
            except KeyError:
                # Resolved a moment ago, pruned by a concurrent `forget`
                # since - see decision 24. Left out, same as a revision
                # that never resolved: the docstring above already
                # promises that.
                continue
        return found

    def commit_order(self, revisions: Iterable[str]) -> dict[str, int]:
        """Where each of these revisions sits in the repository's own
        commit order. Lower is newer.

        Breaks the tie `commit_times` cannot: two commits made in the
        same wall-clock second carry the same value there - git's own
        timestamp resolution is one second, and a fast save or a fast
        test rig hits it regularly - but never the same position here.
        This is the same total order `_revision_index` walks once and
        `_indexed_revisions`/`previous_change` already trust for
        exactness, read instead of recomputed.

        Keyed by what the caller handed in, same convention as
        `commit_times`, so the two answers can be looked up side by
        side. Left out where the index does not reach a revision (see
        `_indexed_revisions`'s own docstring for when that is) rather
        than a guessed position - a caller that needs an answer for
        every revision, indexed or not, should fall back to
        `commit_times` for the ones missing here.
        """
        repo = self._repo()
        if repo is None:
            return {}
        index = self._revision_index(repo)
        if index is None:
            return {}
        found: dict[str, int] = {}
        for revision in dict.fromkeys(revisions):
            resolved = self._resolve(repo, revision)
            if resolved is not None and resolved in index.order:
                found[revision] = index.order[resolved]
        return found

    def list_dashboards(self) -> list[str]:
        """Every dashboard the history currently tracks."""
        repo = self._repo()
        if repo is None:
            return []
        head = self._resolve(repo, "HEAD")
        if head is None:
            return []
        try:
            tree = repo[repo[head.encode()].tree]
        except KeyError:
            # HEAD resolved a moment ago, pruned by a concurrent
            # `forget` since - see decision 24. Same answer as having
            # no HEAD at all.
            return []
        return sorted(
            entry.path.decode()[: -len(".yaml")]
            for entry in tree.items()
            if entry.path.endswith(b".yaml")
        )

    def list_all_dashboards(self) -> list[str]:
        """Every dashboard the history has ever held, deleted ones included.

        The deleted ones are the whole point of the method: a dashboard
        that is gone is exactly the one somebody comes looking for, and it
        is no longer in HEAD to be found. The names half of `survey`,
        without its reads: the callers only ask whether a key is known.
        """
        repo = self._repo()
        if repo is None or self._resolve(repo, "HEAD") is None:
            return []
        index = self._revision_index(repo)
        return sorted(index.names) if index is not None else []

    def survey(self) -> Survey:
        """Every dashboard ever, which are live, and what each is called.

        One walk and one look at HEAD for all of it. Asking each deleted
        dashboard on its own for its last name cost a path-filtered walk
        apiece: measured on 2026-09-04, 0.67 s for the walk against 8.27 s
        for twenty-two of those.

        Metadata still in the tree at HEAD wins over what a deletion
        removed: it is more recent, whether the dashboard is live or a
        deletion missed it.

        Cached by HEAD. The panel asks on every recorded change, and the
        answer cannot change until HEAD does.
        """
        repo = self._repo()
        if repo is None:
            return Survey([], set(), {})
        head = self._resolve(repo, "HEAD")
        if head is None:
            return Survey([], set(), {})
        cached = self._survey
        if cached is not None and cached[0] == head:
            return cached[1]

        # From the index, which walked for this as well. Kept apart from
        # the index all the same: this reads blobs at HEAD, and those
        # change under a HEAD the index carries itself forward across.
        index = self._revision_index(repo)
        if index is None:
            return Survey([], set(), {})
        names, removed_meta = index.names, index.removed_meta
        try:
            tree = repo[repo[head.encode()].tree]
        except KeyError:
            # HEAD resolved a moment ago, pruned by a concurrent
            # `forget` since - see decision 24. Same answer as the
            # index-not-ready case just above.
            return Survey([], set(), {})
        live = {
            entry.path.decode()[: -len(".yaml")]
            for entry in tree.items()
            if entry.path.endswith(b".yaml")
        }
        at_head: dict[str, bytes] = {}
        try:
            _, meta_id = tree.lookup_path(repo.get_object, b"meta")
            for entry in repo[meta_id].items():
                if entry.path.endswith(b".yaml"):
                    at_head[entry.path.decode()[: -len(".yaml")]] = entry.sha
        except KeyError:
            pass  # no meta/ directory yet
        last_meta: dict[str, str] = {}
        for key in names:
            blob = at_head.get(key)
            if blob is None and key not in live:
                blob = removed_meta.get(key)
            if blob is None:
                continue
            try:
                last_meta[key] = repo[blob].data.decode("utf-8")
            except KeyError:
                # Seen by the walk, pruned before the read: a `forget` ran
                # in between, and reads are not held off while it does.
                # A name without its title beats no list at all.
                continue
        found = Survey(sorted(names), live, last_meta)
        self._survey = (head, found)
        return found

    def measure(self) -> Measurement:
        """Everything the sensors show and the report carries, in one pass.

        Deliberately not behind `self._lock`: every other read here -
        `list_changes`, `survey`, `read_at` - runs without it, and a
        measurement that waits for a running `forget` would block a
        sensor for fifteen seconds. What it can catch instead is a
        half-rewritten history, and every step below survives that by
        skipping rather than raising.
        """
        repo = self._repo()
        sizes = self._measure_disk(repo)
        # One exit for both, because they are one answer: there is
        # nothing indexed to describe. Sizes are still real - a folder
        # can hold bytes before it holds a commit.
        index = self._revision_index(repo) if repo is not None else None
        if index is None:
            return Measurement(**sizes)

        # Filtered once here rather than guarded at each of the three
        # places below that read it.
        by_key = {key: revs for key, revs in index.by_key.items() if revs}

        by_position = {position: revision for revision, position in index.order.items()}
        newest_revision = by_position.get(0)
        oldest_revision = by_position.get(max(by_position)) if by_position else None

        # One lookup for the two ends of every dashboard *and* the two
        # ends of the whole history. They overlap almost entirely, and
        # asking twice used to open a second repository to learn two
        # timestamps it already had.
        wanted = {r for revs in by_key.values() for r in (revs[0], revs[-1])}
        wanted.update(r for r in (newest_revision, oldest_revision) if r is not None)
        times = self._commit_times_at(repo, wanted)

        newest_key = next(
            (key for key, revs in by_key.items() if revs[0] == newest_revision), None
        )

        live = self.survey().live
        marks, total_marks = self._versions_by_key(repo)
        at_head = self._blob_sizes_at_head(repo)

        rows = [
            DashboardFacts(
                key=key,
                revisions=len(revs),
                bytes=(
                    at_head[key]
                    if key in at_head
                    else self._bytes_of_newest_content(repo, key, revs)
                ),
                versions=marks.get(key, 0),
                first=times.get(revs[-1], 0),
                last=times.get(revs[0], 0),
                gone=key not in live,
            )
            for key, revs in by_key.items()
        ]
        rows.sort(key=lambda row: (-row.revisions, row.key))

        return Measurement(
            revisions=len(index.order),
            oldest=times.get(oldest_revision),
            newest=times.get(newest_revision),
            newest_key=newest_key,
            versions=total_marks,
            dashboards=tuple(rows),
            **sizes,
        )

    @staticmethod
    def _commit_times_at(repo: Repo, revisions) -> dict[str, int]:
        """When each of these commits was made, straight from an open repo.

        Not `commit_times`, although it answers the same question. That
        one puts every revision through `_resolve` first, because its
        callers hand it whatever a person typed - an abbreviation, a
        version name, `HEAD`. These revisions come out of the index and
        are full commit hashes by construction, so the resolving is
        three object loads apiece to learn what was already known.
        Measured on 2026-09-20 over 122 revisions: 29.9 ms against
        10.3 ms.
        """
        found: dict[str, int] = {}
        for revision in revisions:
            try:
                found[revision] = repo[revision.encode()].commit_time
            except KeyError:
                # Pruned by a `forget` between the walk and this read.
                continue
        return found

    @staticmethod
    def _blob_sizes_at_head(repo: Repo) -> dict[str, int]:
        """Every live dashboard's length, out of one tree.

        The alternative is asking `_blob_at` per dashboard, and that is
        where this measurement used to spend most of its time: measured
        on 2026-09-20, finding 68 blob ids that way cost 33.9 ms against
        0.3 ms for reading them all out of the tree at HEAD once.

        `get_raw` rather than `repo[sha].data`: the latter rebuilds the
        object through `ShaFile.from_raw_string`, which recomputes the
        SHA-1 over the whole inflated blob to verify it. For a few
        hundred kilobytes apiece that is about a third of the read, and
        nothing here needs the check - the id came out of the tree a
        line ago.

        Deleted dashboards are absent from HEAD by definition and are
        not in the answer; `_bytes_of_newest_content` covers those, and
        that is the only case it is needed for now.
        """
        head = HistoryStore._resolve(repo, "HEAD")
        if head is None:
            return {}
        try:
            entries = repo[repo[head.encode()].tree].items()
        except KeyError:
            return {}
        found: dict[str, int] = {}
        for entry in entries:
            if not entry.path.endswith(b".yaml"):
                continue
            try:
                found[entry.path.decode()[: -len(".yaml")]] = len(
                    repo.object_store.get_raw(entry.sha)[1]
                )
            except KeyError:
                # Pruned between the tree read and this one.
                continue
        return found

    def _measure_disk(self, repo: Repo | None) -> dict:
        """Walk the store once and weigh it in two ways.

        Two numbers rather than one, and that is the point of this
        method. `st_size` is what a file contains; `st_blocks * 512` is
        what it costs. For a packed repository the two are within a
        percent of each other - measured on 2026-09-19 against the test
        bench, 0.1 % across the pack. Across the *loose* objects of the
        same repository it was 689.5 %: a loose git object is a few
        hundred bytes and still occupies a whole 4 KiB block. The loose
        count is precisely the number initiative C decides on, so
        reporting only the logical size would be reporting the wrong one.

        Both numbers come out of one `lstat` per file. It is one walk,
        not two, and the allocated figure costs nothing on top.

        `st_blocks` does not exist on Windows, and that is a property of
        the platform, asked once here rather than of every file. There
        the allocated sum stays `None` rather than being estimated
        against a guessed block size: a missing number is honest, an
        invented one spoils the very analysis it was invented for.

        The loose and pack counts come from `dulwich`, not from this
        walk. Recognising them by their place - `objects/xx/` for the
        loose ones, `objects/pack/*.pack` for the others - meant
        rebuilding git's layout inside an `os.walk`, in a project whose
        first hard rule is that only `dulwich` may know such things.
        Its own counters are better than the guess as well:
        `count_loose_objects` checks the name length against the hash
        format, so a temporary file being written is not counted, and
        `count_pack_files` leaves out packs marked `.keep`.

        Only a *vanished* file is skipped. A permission error or a bad
        disk is not skipped, it is raised: the coordinator turns that
        into a failed refresh, keeps the last good numbers and says
        `stale`. Swallowing every `OSError` would publish a measurement
        that is silently too small and flag it as fresh, which is worse
        than no measurement at all. `os.walk` is given `onerror` for the
        same reason - without it, it hides directory errors by design.
        """

        def _raise(error: OSError) -> None:
            raise error

        # Built like the walk's own roots rather than taken from
        # `repo.controldir()`: the comparison below is between paths,
        # and one absolute path against one relative path is a
        # comparison that quietly answers no.
        git = self.path / ".git"
        have_blocks = hasattr(os.stat_result, "st_blocks")
        git_logical = worktree_logical = allocated = 0

        if self.path.exists():
            for root, _dirs, files in os.walk(self.path, onerror=_raise):
                here = Path(root)
                in_git = here == git or git in here.parents
                for name in files:
                    try:
                        stat = os.lstat(here / name)
                    except FileNotFoundError:
                        # A `garbage_collect` is pruning while we count.
                        # One file missing from a size is nothing. Every
                        # other OSError travels on - see the docstring.
                        continue
                    if in_git:
                        git_logical += stat.st_size
                    else:
                        worktree_logical += stat.st_size
                    if have_blocks:
                        allocated += stat.st_blocks * 512

        return {
            "bytes_allocated": allocated if have_blocks else None,
            "bytes_git_logical": git_logical,
            "bytes_worktree_logical": worktree_logical,
            "loose_objects": repo.object_store.count_loose_objects() if repo else 0,
            "packs": repo.object_store.count_pack_files() if repo else 0,
        }

    @staticmethod
    def _versions_by_key(repo: Repo) -> tuple[dict[str, int], int]:
        """How many version marks each dashboard has, and how many there are.

        Counted from the ref *names* alone - `refs/tags/<key>/vX.Y.Z` -
        without loading a single tag object. `list_versions` would read
        every object in the namespace, and measured on 2026-09-05 that
        cost 492 ms at 3650 tags. A count needs none of it.

        Split from the right, because a key may hold a slash itself: a
        dashboard recorded before the key rule existed can be named
        `foo/bar`, and splitting from the left would file its versions
        under `foo`.

        The total comes out of the same pass, and it is not the sum of
        the per-key counts: a mark without a slash - `refs/tags/v1` -
        belongs to no dashboard, so it appears in the total and in no
        row. `as_dict` caches nothing, and scanning `packed-refs` twice
        cost 17.9 ms a second time on the bench for a number this loop
        already had.
        """
        counted: dict[str, int] = {}
        total = 0
        for ref in repo.refs.as_dict(b"refs/tags"):
            total += 1
            if b"/" not in ref:
                continue
            key = ref.rsplit(b"/", 1)[0].decode()
            counted[key] = counted.get(key, 0) + 1
        return counted, total

    def _bytes_of_newest_content(self, repo: Repo, key: str, revisions: list) -> int:
        """The length of the newest state of `key` that had any.

        For **deleted** dashboards only. The live ones come out of
        `_blob_sizes_at_head` in one tree read; this walks back one
        revision at a time, which is the right shape for a dashboard
        whose newest commit is its deletion - that commit's tree no
        longer holds the file, so the loop steps back to the state
        before it, which is exactly what a restore would bring back.

        `get_raw` rather than `repo[blob_id].data`, for the reason given
        in `_blob_sizes_at_head`: the verifying path recomputes SHA-1
        over the whole inflated blob, and the id came from a tree.

        Zero where nothing is found. A dashboard that never held content
        cannot occur through `write_snapshot`, but a history rewritten by
        an interrupted `forget` is not worth an exception here.
        """
        path = f"{key}.yaml"
        for revision in revisions:
            blob_id = self._blob_at(repo, path, revision)
            if blob_id is None:
                continue
            try:
                return len(repo.object_store.get_raw(blob_id)[1])
            except KeyError:
                # Pruned between the tree lookup and the read.
                return 0
        return 0

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
        found: list[tuple[int, Version]] = []
        for ref, tag in self._each_tag(repo, key):
            version = _version_from(ref.decode(), tag)
            found.append((version.timestamp, version))
        # as_dict has no order of its own; the docstring promises one.
        return [version for _, version in sorted(found, key=lambda p: -p[0])]
