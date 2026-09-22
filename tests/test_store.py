"""Tests for the git-backed history store."""

import threading
from contextlib import contextmanager

import pytest
from dulwich import porcelain
from dulwich.object_store import DiskObjectStore
from dulwich.objects import Blob
from dulwich.repo import Repo
import dulwich.refs
from dulwich.errors import MissingCommitError
import store as store_module
from store import HistoryStore, RevisionIndex, Version, _as_text
import versions
from versions import candidates


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "history")
    s.ensure()
    return s


def test_ensure_clears_stale_lock_files(tmp_path):
    """A lock left by an interrupted `forget` must not disable the next one.

    `ensure()` runs once per Home Assistant start, before this process
    has touched the repository, so a `.lock` file already on disk was
    left by a process that no longer exists — see issue #19.
    """
    history = HistoryStore(tmp_path / "history")
    history.ensure()
    packed_refs_lock = history.path / ".git" / "packed-refs.lock"
    packed_refs_lock.write_bytes(b"stale")
    tag_lock = history.path / ".git" / "refs" / "tags" / "dashboard" / "v1.lock"
    tag_lock.parent.mkdir(parents=True)
    tag_lock.touch()

    history.ensure()

    assert not packed_refs_lock.exists()
    assert not tag_lock.exists()


def test_ensure_does_not_repeat_the_cleanup_within_one_process(tmp_path):
    """A reload must not delete a lock a still-running write is holding.

    A reload builds a fresh `HistoryStore` with its own `threading.Lock`,
    while a write dispatched through `hass.async_create_task` before the
    reload can still be running in the executor - `capture.async_stop`
    does not wait for it. That write holds its own lock file, unrelated
    to the crash `_clear_stale_locks` is for. Clearing it out from under
    the write breaks its rename with `FileNotFoundError`.

    The first `ensure()` in this process is the only one that may ever
    have raced a truly dead process rather than a live one, so it is the
    only one allowed to sweep. Reproduces the finding from the review of
    issue #19's fix.
    """
    first = HistoryStore(tmp_path / "history")
    first.ensure()  # creates the repository - no sweep yet, nothing to sweep
    first.ensure()  # the first sweep for this path in this process

    second = HistoryStore(tmp_path / "history")
    lock = second.path / ".git" / "refs" / "heads" / "master.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.touch()

    second.ensure()

    assert lock.exists()


def test_two_instances_of_the_same_path_share_one_lock(tmp_path):
    """The foundation everything else in decision 21 stands on.

    `HistoryStore.__init__` used to build its own `threading.Lock()`
    per instance. A reload builds a fresh instance for the same path -
    found in review of decision 21 to mean a repair on the new instance
    could race a still-running `forget` on the old one, since neither
    shared anything with the other. Two instances of the same path must
    now get the literal same lock object; two instances of different
    paths must not.
    """
    first = HistoryStore(tmp_path / "history")
    second = HistoryStore(tmp_path / "history")
    other = HistoryStore(tmp_path / "elsewhere")

    assert first._lock is second._lock
    assert first._lock is not other._lock


def test_repair_waits_for_a_live_forget_on_another_instance(tmp_path):
    """A reload's repair must never run concurrently with a live forget.

    Proven with two real threads, not just the identity check above:
    one holds the shared lock - standing in for an in-flight `forget`
    on an old instance - the other calls `repair_pending_forget` on a
    second instance of the same path, which must block until the first
    releases it, not run alongside it.
    """
    import threading

    first = HistoryStore(tmp_path / "history")
    first.ensure()
    second = HistoryStore(tmp_path / "history")

    entered = threading.Event()
    release = threading.Event()

    def hold_the_lock():
        with first._lock:
            entered.set()
            release.wait(timeout=5)

    holder = threading.Thread(target=hold_the_lock)
    holder.start()
    assert entered.wait(timeout=5)

    repaired = threading.Event()

    def try_repair():
        second.repair_pending_forget()
        repaired.set()

    repairer = threading.Thread(target=try_repair)
    repairer.start()

    # If `second._lock` were independent of `first._lock` - the bug
    # this test exists to catch - `repair_pending_forget` would find
    # nothing contended and return almost immediately, regardless of
    # how the OS happens to schedule these two threads: relying on
    # relative ordering of "the main thread's next two statements" and
    # "a freshly started thread's first bytecode" is not deterministic
    # enough to tell the two cases apart (confirmed empirically in
    # review of this plan: that shape of assertion passed 100/100 runs
    # even with two unrelated locks). Giving the repairer thread a
    # generous, fixed window and asserting it did *not* finish in that
    # window is what actually distinguishes "genuinely blocked" from
    # "raced and happened to lose."
    assert not repaired.wait(timeout=0.2)

    release.set()
    assert repaired.wait(timeout=5)
    holder.join(timeout=5)
    repairer.join(timeout=5)


def test_first_snapshot_creates_a_revision(store):
    assert store.write_snapshot("home", "a: 1\n", "first") is not None


def test_unchanged_snapshot_creates_nothing(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.write_snapshot("home", "a: 1\n", "second") is None


def test_changed_snapshot_creates_a_revision(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.write_snapshot("home", "a: 2\n", "second") is not None


def test_history_is_per_dashboard(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("other", "b: 1\n", "other first")
    store.write_snapshot("home", "a: 2\n", "home second")
    assert [c.message for c in store.list_changes("home")] == ["home second", "home first"]
    assert [c.message for c in store.list_changes("other")] == ["other first"]


def test_a_rename_appears_in_the_history(store):
    # A rename touches only meta/<key>.yaml. Filtering the walk on the
    # configuration alone would record it and then never show it - captured
    # and invisible is the worst of both.
    store.write_snapshot("home", "a: 1\n", "first", meta="title: Home\n")
    store.write_snapshot("home", "a: 1\n", "renamed", meta="title: Kitchen\n")
    assert [c.message for c in store.list_changes("home")] == ["renamed", "first"]


def test_metadata_appearing_later_appears_in_the_history(store):
    # What every existing installation does on its first start after the
    # update: same cards, metadata recorded for the first time.
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 1\n", "metadata recorded", meta="title: Home\n")
    assert [c.message for c in store.list_changes("home")] == [
        "metadata recorded",
        "first",
    ]


def test_history_of_unknown_dashboard_is_empty(store):
    assert store.list_changes("nothing") == []


def test_history_of_empty_repository_is_empty(store):
    # No commit at all: there is no HEAD to walk.
    assert store.list_changes("home") == []


def test_read_at_returns_the_old_text(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    assert store.read_at("home", first) == "a: 1\n"


def test_read_at_before_the_file_existed_returns_none(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "other")
    assert store.read_at("other", first) is None


def test_an_abbreviated_revision_is_resolved(store):
    # `git log --oneline` prints exactly this short form, so it is what
    # anyone looking into the repository will copy. dulwich does not
    # resolve it on its own.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    assert store.resolve(first[:7]) == first
    assert store.read_at("home", first[:7]) == "a: 1\n"


def test_a_full_revision_and_head_resolve(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    assert store.resolve(first) == first
    assert store.resolve("HEAD") == first
    assert store.resolve(f"  {first}  ") == first


def test_an_unknown_revision_resolves_to_none(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.resolve("nosuchthing") is None
    assert store.resolve("ffffffff") is None
    assert store.resolve("") is None


def test_a_too_short_revision_is_refused(store):
    # Four characters is git's own minimum. Below that an abbreviation
    # says too little to act on.
    first = store.write_snapshot("home", "a: 1\n", "first")
    assert store.resolve(first[:3]) is None


def test_a_version_resolves_to_the_commit_it_marks(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("v1", "Title", "Text.", first)
    tag = Repo(str(store.path))[b"refs/tags/v1"]
    assert store.resolve(tag.id.decode()) == first


def test_a_version_resolves_by_its_name(store):
    # The claim that a tag name works as a revision stood in the spec and
    # in the README and was never true: dulwich's Repo.__getitem__ does no
    # ref-name expansion, so `repo[b"v1.0.0"]` raises KeyError even when
    # the tag is right there. It went unnoticed because the only test
    # resolved the tag's *object id* instead of its name.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "Title", "Text.", first)
    assert store.resolve("home/v1.0.0") == first


def test_a_version_name_reads_the_state_it_marks(store):
    # This is what makes going back to a version free: read_at takes the
    # name straight through, so restore_state needs no new code at all.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "Title", "Text.", first)
    store.write_snapshot("home", "a: 2\n", "second")
    assert store.read_at("home", "home/v1.0.0") == "a: 1\n"


def test_an_unknown_name_still_resolves_to_nothing(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.resolve("home/v9.9.9") is None


def test_metadata_travels_with_the_state(store):
    first = store.write_snapshot("home", "a: 1\n", "first", meta="title: Home\n")
    assert store.read_meta_at("home", first) == "title: Home\n"
    assert store.read_at("home", first) == "a: 1\n"


def test_changed_metadata_alone_creates_a_revision(store):
    # Renaming a dashboard changes nothing about its cards. Without this it
    # would leave no trace, and a restore would bring back the old name.
    store.write_snapshot("home", "a: 1\n", "first", meta="title: Home\n")
    second = store.write_snapshot("home", "a: 1\n", "renamed", meta="title: Kitchen\n")
    assert second is not None
    assert store.read_meta_at("home", second) == "title: Kitchen\n"


def test_unchanged_state_and_metadata_create_nothing(store):
    store.write_snapshot("home", "a: 1\n", "first", meta="title: Home\n")
    assert store.write_snapshot("home", "a: 1\n", "again", meta="title: Home\n") is None


def test_metadata_is_not_mistaken_for_a_dashboard(store):
    store.write_snapshot("home", "a: 1\n", "first", meta="title: Home\n")
    assert store.list_dashboards() == ["home"]


def test_deleting_a_dashboard_takes_its_metadata_with_it(store):
    first = store.write_snapshot("home", "a: 1\n", "first", meta="title: Home\n")
    store.mark_deleted("home", "home: dashboard deleted")
    assert store.read_meta_at("home", "HEAD") is None
    assert store.read_meta_at("home", first) == "title: Home\n"


def test_a_deleted_dashboard_is_marked_and_stays_readable(store):
    # Deleting a whole dashboard is the heaviest loss there is, and Home
    # Assistant announces it with no event at all. Leaving no trace would
    # make it the only change the history misses.
    first = store.write_snapshot("gone", "a: 1\n", "first")
    store.write_snapshot("stays", "b: 1\n", "other")
    assert store.mark_deleted("gone", "gone: dashboard deleted") is not None
    assert [c.message for c in store.list_changes("gone")] == [
        "gone: dashboard deleted",
        "first",
    ]
    # The state itself is not lost - that is what a history is for.
    assert store.read_at("gone", first) == "a: 1\n"
    assert store.read_at("gone", "HEAD") is None
    assert store.read_at("stays", "HEAD") == "b: 1\n"


def test_marking_an_unknown_dashboard_does_nothing(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.mark_deleted("never-existed", "x: dashboard deleted") is None


def test_a_dashboard_is_marked_deleted_only_once(store):
    store.write_snapshot("gone", "a: 1\n", "first")
    store.mark_deleted("gone", "gone: dashboard deleted")
    assert store.mark_deleted("gone", "gone: dashboard deleted") is None


def test_a_recreated_dashboard_starts_a_fresh_chapter(store):
    # If a *different* dashboard later takes the same url_path, comparing
    # it against its stranger of a predecessor would produce an enormous
    # and meaningless diff.
    store.write_snapshot("reused", "a: 1\n", "first")
    store.mark_deleted("reused", "reused: dashboard deleted")
    assert store.write_snapshot("reused", "totally: different\n", "new") is not None
    assert store.read_at("reused", "HEAD") == "totally: different\n"


def test_list_dashboards_names_what_the_history_tracks(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "first")
    assert store.list_dashboards() == ["home", "other"]
    store.mark_deleted("other", "other: dashboard deleted")
    assert store.list_dashboards() == ["home"]


def test_list_all_dashboards_remembers_deleted_ones(store):
    # The deleted one is the point: it is exactly what somebody comes
    # looking for, so the panel has to be able to offer it.
    store.write_snapshot("stays", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "first")
    store.mark_deleted("gone", "gone: dashboard deleted")
    assert store.list_dashboards() == ["stays"]
    assert store.list_all_dashboards() == ["gone", "stays"]


def test_list_all_dashboards_ignores_metadata(store):
    store.write_snapshot("home", "a: 1\n", "first", meta="title: Home\n")
    assert store.list_all_dashboards() == ["home"]


def test_the_survey_has_no_metadata_for_a_dashboard_that_never_recorded_any(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert "home" not in store.survey().last_meta


def test_list_dashboards_of_an_empty_repository_is_empty(store):
    assert store.list_dashboards() == []


def test_version_marks_a_revision_without_changing_history(store):
    store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("v1", "Kitchen rework", "Two cards moved.", second)
    versions = store.list_versions()
    assert [v.name for v in versions] == ["v1"]
    assert versions[0].title == "Kitchen rework"
    assert versions[0].description == "Two cards moved."
    assert versions[0].revision == second
    # The individual changes are still there and still separate.
    assert len(store.list_changes("home")) == 2


def test_the_temporary_file_is_never_tracked(store, tmp_path):
    # A leftover .tmp must never end up in the repository.
    store.write_snapshot("home", "a: 1\n", "first")
    (tmp_path / "history" / "home.yaml.tmp").write_text("junk", encoding="utf-8")
    store.write_snapshot("home", "a: 2\n", "second")
    repo = Repo(str(tmp_path / "history"))
    assert sorted(path.decode() for path in repo.open_index()) == ["home.yaml"]


def test_a_state_lost_before_the_commit_is_recorded_afterwards(store, tmp_path):
    # A crash between writing the file and committing leaves the file ahead
    # of the repository. Comparing against the file would drop that state
    # from the history for good and without a word; comparing against HEAD
    # picks it up on the next run.
    store.write_snapshot("home", "a: 1\n", "first")
    (tmp_path / "history" / "home.yaml").write_text("a: 2\n", encoding="utf-8")
    assert store.write_snapshot("home", "a: 2\n", "second") is not None
    assert [c.message for c in store.list_changes("home")] == ["second", "first"]


def test_an_unchanged_snapshot_repairs_the_working_tree(store, tmp_path):
    store.write_snapshot("home", "a: 1\n", "first")
    (tmp_path / "history" / "home.yaml").write_text("tampered\n", encoding="utf-8")
    assert store.write_snapshot("home", "a: 1\n", "again") is None
    assert (tmp_path / "history" / "home.yaml").read_text(encoding="utf-8") == "a: 1\n"


def test_parallel_writes_all_arrive(store):
    # dulwich holds an exclusive lock on the git index. Without serialising,
    # eight parallel writes let exactly one commit through.
    def write(number):
        store.write_snapshot(f"d{number}", f"n: {number}\n", f"commit {number}")

    threads = [threading.Thread(target=write, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(store.list_changes(f"d{i}") for i in range(8))


# -- descriptions of one's own -----------------------------------------
#
# The automatic message says what happened. Why it happened is only in
# somebody's head, and "before rebuilding the heating cards" is what you
# find again in a year - "2 removed, 1 edited" is not.
#
# The text is a git note, so the commit itself is untouched. That is not
# tidiness: a rewritten commit invalidates every revision this tool
# hands out, in panel responses, service results and error messages.


def test_a_description_appears_in_the_history(store):
    revision = store.write_snapshot("home", "a: 1\n", "first")
    assert store.set_description(revision, "Before the heating rebuild") is True
    assert store.list_changes("home")[0].description == "Before the heating rebuild"


def test_a_change_without_a_description_has_an_empty_one(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.list_changes("home")[0].description == ""


def test_a_description_does_not_change_the_revision(store):
    # The whole reason for using notes instead of rewriting the commit.
    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(revision, "Something")
    assert store.list_changes("home")[0].revision == revision


def test_a_description_replaces_the_previous_one(store):
    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(revision, "First wording")
    store.set_description(revision, "Second wording")
    assert store.list_changes("home")[0].description == "Second wording"


def test_an_emptied_description_is_gone_not_blank(store):
    # A blank note would leave the row with an invisible headline and the
    # automatic message hidden underneath it.
    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(revision, "Something")
    store.set_description(revision, "   ")
    assert store.list_changes("home")[0].description == ""
    assert store.descriptions() == {}


def test_emptying_a_description_that_was_never_there_is_harmless(store):
    revision = store.write_snapshot("home", "a: 1\n", "first")
    assert store.set_description(revision, "") is True


def test_a_description_survives_umlauts(store):
    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(revision, "Vor dem Umbau der Heizung — äöüß")
    assert store.list_changes("home")[0].description == (
        "Vor dem Umbau der Heizung — äöüß"
    )


def test_an_abbreviated_revision_can_be_described(store):
    # What anyone copies out of the panel, which shows seven characters.
    revision = store.write_snapshot("home", "a: 1\n", "first")
    assert store.set_description(revision[:7], "Short form") is True
    assert store.list_changes("home")[0].description == "Short form"


def test_an_unknown_revision_is_refused(store):
    # dulwich raises KeyError for an unknown object, so this must be
    # resolved first. Refusing is right anyway: a note filed against
    # nothing is a note nobody ever sees again.
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.set_description("f" * 40, "Nowhere") is False
    assert store.descriptions() == {}


def test_descriptions_are_per_revision(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.set_description(first, "The older one")
    store.set_description(second, "The newer one")
    assert [c.description for c in store.list_changes("home")] == [
        "The newer one",
        "The older one",
    ]


def test_the_state_before_a_change_is_the_previous_one_of_that_dashboard(store):
    # Not the commit's parent: another dashboard's commit can sit in
    # between, and its state is no state of this dashboard at all.
    first = store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("other", "b: 1\n", "other first")
    second = store.write_snapshot("home", "a: 2\n", "home second")
    assert store.previous_change("home", second) == first


def test_the_first_change_has_nothing_before_it(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    assert store.previous_change("home", first) is None


def test_the_state_before_an_unknown_revision_is_unknown(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.previous_change("home", "f" * 40) is None


def test_notes_stay_out_of_the_dashboard_history(store):
    # descriptions live on refs/notes/commits, so the commits that carry
    # them must not turn up as dashboards or as changes. Pinned rather
    # than assumed: list_all_dashboards walks every commit there is, and
    # a stray one there would invent a dashboard out of nothing.
    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(revision, "A note of my own")
    assert store.list_all_dashboards() == ["home"]
    assert len(store.list_changes("home")) == 1
    assert store.list_dashboards() == ["home"]


# -- which recorded states are the one in front of you -----------------
#
# A history that goes back and forth - a card moved up, then down, then up
# again - holds several states with byte-identical content and, because the
# messages are generated, identical wording too. Measured on the test
# installation: seven entries reading "2 moved", every second one identical
# to the live dashboard. Without marking, that list cannot be navigated.


def test_the_revision_holding_the_live_text_is_found(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    assert store.matching_revisions("home", [second, first], "a: 2\n") == {second}


def test_every_revision_with_the_same_content_is_found(store):
    # The back-and-forth case, which is the reason this exists.
    up = store.write_snapshot("home", "a: 1\n", "up")
    down = store.write_snapshot("home", "a: 2\n", "down")
    up_again = store.write_snapshot("home", "a: 1\n", "up again")
    assert store.matching_revisions("home", [up_again, down, up], "a: 1\n") == {
        up,
        up_again,
    }


def test_nothing_matches_a_text_that_was_never_recorded(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    assert store.matching_revisions("home", [first], "a: 99\n") == set()


def test_an_unknown_revision_simply_does_not_match(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    assert store.matching_revisions("home", ["f" * 40, first], "a: 1\n") == {first}


def test_matching_reads_only_this_dashboard_s_file(store):
    home = store.write_snapshot("home", "a: 1\n", "home")
    other = store.write_snapshot("other", "b: 2\n", "other")
    # "b: 2" belongs to the other dashboard and was never home's content,
    # at any revision.
    assert store.matching_revisions("home", [other, home], "b: 2\n") == set()
    # And home's own content matches at *both* revisions - including the one
    # whose commit touched another dashboard, because home.yaml still held
    # that text there. That is what "the state at this revision" means, and
    # the caller only ever passes revisions from one dashboard's own history.
    assert store.matching_revisions("home", [other, home], "a: 1\n") == {
        home,
        other,
    }


def test_matching_against_an_empty_repository_is_empty(tmp_path):
    fresh = HistoryStore(tmp_path / "nothing")
    assert fresh.matching_revisions("home", ["abc"], "a: 1\n") == set()


# -- whether two recorded states are the same state ---------------------
#
# Asked when an automatic version is about to be made: the day mark is
# worked out from the calendar, so a dashboard that was changed and
# changed back collects one mark per day all sitting on the same content.
# Those rows offer nothing - the panel leaves the button off them - so the
# mark is not made in the first place.


def test_two_revisions_holding_one_state_are_the_same_state(store):
    up = store.write_snapshot("home", "a: 1\n", "up")
    store.write_snapshot("home", "a: 2\n", "down")
    up_again = store.write_snapshot("home", "a: 1\n", "up again")
    assert store.same_state("home", up_again, up) is True


def test_two_revisions_holding_different_states_are_not(store):
    up = store.write_snapshot("home", "a: 1\n", "up")
    down = store.write_snapshot("home", "a: 2\n", "down")
    assert store.same_state("home", down, up) is False


def test_a_state_is_the_same_as_itself(store):
    only = store.write_snapshot("home", "a: 1\n", "only")
    assert store.same_state("home", only, only) is True


def test_an_unknown_revision_is_never_the_same_state(store):
    # Never an error, and never True: a revision nothing can be read at
    # must not make a caller think it has compared anything.
    only = store.write_snapshot("home", "a: 1\n", "only")
    assert store.same_state("home", "f" * 40, only) is False
    assert store.same_state("home", only, "f" * 40) is False


def test_a_revision_from_before_this_dashboard_existed_is_not_the_same(store):
    other = store.write_snapshot("other", "b: 1\n", "other")
    home = store.write_snapshot("home", "a: 1\n", "home")
    # home.yaml is not in the tree at `other` at all. Answering True there
    # would read "nothing changed" out of "there was nothing".
    assert store.same_state("home", home, other) is False


def test_only_the_dashboard_s_own_file_decides(store):
    # A commit that carries only a metadata change - a dashboard renamed
    # while its cards stay put - holds the same *state* of this dashboard.
    # It is the case the day mark must not spend a version on, because a
    # restore of an existing dashboard writes the configuration and not
    # the metadata.
    named = store.write_snapshot("home", "a: 1\n", "named", "title: Heizung\n")
    renamed = store.write_snapshot("home", "a: 1\n", "renamed", "title: Warmth\n")
    assert renamed is not None
    assert store.same_state("home", renamed, named) is True


def test_comparing_in_an_empty_repository_is_not_the_same(tmp_path):
    fresh = HistoryStore(tmp_path / "nothing")
    assert fresh.same_state("home", "abc", "def") is False


# -- when a recorded state was recorded ---------------------------------
#
# Asked by the day mark, which has to know which calendar day each
# existing automatic version is about. That day is the day its marked
# state was recorded on - not the day its tag was made, which is the
# following one at the earliest.


def test_the_time_of_each_revision_is_reported(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    times = store.commit_times([first, second])
    recorded = {c.revision: c.timestamp for c in store.list_changes("home")}
    assert times == recorded


def test_an_unknown_revision_is_left_out_rather_than_answered(store):
    # Left out, not zero: a caller reading a day out of this must not be
    # handed 1970 for something it could not find.
    only = store.write_snapshot("home", "a: 1\n", "only")
    assert store.commit_times([only, "f" * 40]) == {only: store.list_changes("home")[0].timestamp}


def test_a_version_name_is_a_revision_here_too(store):
    only = store.write_snapshot("home", "a: 1\n", "only")
    store.create_version("home/v1.0.0", "First", "", only)
    # Answered under the name it was asked about, not under the commit
    # it resolves to: a caller looks the answer up by what it handed in.
    assert list(store.commit_times(["home/v1.0.0"])) == ["home/v1.0.0"]


def test_asking_about_nothing_is_empty(store):
    store.write_snapshot("home", "a: 1\n", "only")
    assert store.commit_times([]) == {}


def test_asking_an_empty_repository_is_empty(tmp_path):
    fresh = HistoryStore(tmp_path / "nothing")
    assert fresh.commit_times(["abc"]) == {}


def test_commit_order_gives_a_strict_order_ties_or_not(store):
    # `commit_times` alone cannot always tell two commits apart - two
    # saves inside the same wall-clock second (git's own timestamp
    # resolution) get the same value there, which two calls this close
    # together often do on a fast run. `commit_order` answers from the
    # index's own total order instead, which never ties.
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    order = store.commit_order([first, second])
    assert order[first] > order[second]


def test_commit_order_is_keyed_by_what_was_asked(store):
    only = store.write_snapshot("home", "a: 1\n", "only")
    store.create_version("home/v1.0.0", "First", "", only)
    assert list(store.commit_order(["home/v1.0.0"])) == ["home/v1.0.0"]


def test_commit_order_on_an_unknown_revision_is_empty(store):
    only = store.write_snapshot("home", "a: 1\n", "only")
    assert store.commit_order([only, "f" * 40]) == {only: store.commit_order([only])[only]}


def test_commit_order_asking_an_empty_repository_is_empty(tmp_path):
    fresh = HistoryStore(tmp_path / "nothing")
    assert fresh.commit_order(["abc"]) == {}


# -- forgetting a dashboard for good -----------------------------------
#
# The one operation in this project that rewrites the stored history, in
# a tool built to stop things disappearing. It exists because a deleted
# dashboard stays in the list forever, and after enough years that list
# is mostly gravestones.
#
# git can only really remove something by rewriting history, so every
# revision from the first affected commit onwards changes. Two things hang
# off revisions and would vanish silently: the descriptions people write
# (git notes are keyed by commit sha) and named versions (tags). Carrying
# those across is most of what these tests are about.


def _versions(store):
    return {v.name: v.title for v in store.list_versions()}


def test_forgetting_removes_the_dashboard_from_the_history(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.mark_deleted("gone", "gone: dashboard deleted")
    assert "gone" in store.list_all_dashboards()

    assert store.forget("gone") > 0
    assert "gone" not in store.list_all_dashboards()
    assert store.list_changes("gone") == []


def test_list_changes_retries_a_read_that_raced_forget(store, monkeypatch):
    """A read that hits the known KeyError/MissingCommitError race - a
    concurrent `forget` pruning a commit this read already had a
    revision list for - rebuilds against the moved HEAD instead of
    raising. See decision 24.

    `_each_change` is monkeypatched rather than dulwich itself: the
    real race needs true thread concurrency to reproduce on demand
    (the issue's own report: four instrumented runs did not recur).
    This drives the same two facts a real race would - a `KeyError`
    reaching `list_changes`, and HEAD having genuinely moved by the
    time it does - deterministically, the same way
    `test_forget_writes_a_checkpoint_before_the_first_ref_moves`
    interrupts a real `forget` at an exact point instead of guessing
    at timing.

    "gone" is written *before* "home", not after: `forget` gives every
    commit a fresh sha only if something about its own content or its
    ancestry changed. Commit shas are content hashes - a commit written
    after "gone" is forgotten has nothing to rewrite (nothing pointed
    at it, its own tree never held "gone.yaml"), so writing "gone"
    last would forget it "for free," without a single sha of "home"'s
    ever changing - and the retry this test means to exercise would
    pass even if `list_changes` never rebuilt anything at all.
    """
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")

    real_each_change = HistoryStore._each_change
    calls: list[int] = []

    def flaky_each_change(self, repo, key, limit=50, before=None):
        calls.append(1)
        if len(calls) == 1:
            store.forget("gone")  # moves HEAD for real, out from under this read
            raise KeyError(b"simulated: pruned mid-read")
            yield  # pragma: no cover - unreachable, keeps this a generator
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "_each_change", flaky_each_change)

    changes = store.list_changes("home")

    assert [c.message for c in changes] == ["second", "first"]
    assert len(calls) == 2


def test_list_changes_does_not_retry_when_head_is_unchanged(store, monkeypatch):
    """If HEAD never moved, the known race cannot explain the error -
    something else is broken, and that must stay visible, not get
    silently retried into looking fine. See decision 24."""
    store.write_snapshot("home", "a: 1\n", "first")
    calls: list[int] = []

    def always_fails(self, repo, key, limit=50, before=None):
        calls.append(1)
        raise KeyError(b"simulated: unrelated corruption")
        yield  # pragma: no cover - unreachable, keeps this a generator

    monkeypatch.setattr(HistoryStore, "_each_change", always_fails)

    with pytest.raises(KeyError):
        store.list_changes("home")
    assert len(calls) == 1


def test_list_changes_gives_up_after_the_retry_budget(store, monkeypatch):
    """A read that keeps racing a `forget` on every single attempt still
    terminates - the retry budget is a hard cap, not a promise that a
    third attempt will succeed. See decision 24."""
    store.write_snapshot("home", "a: 1\n", "first")
    for i in range(5):
        store.write_snapshot(f"gone{i}", "b: 1\n", "gone first")
    calls: list[int] = []

    def always_races(self, repo, key, limit=50, before=None):
        calls.append(1)
        store.forget(f"gone{len(calls) - 1}")  # moves HEAD every single time
        raise KeyError(b"simulated: perpetual race")
        yield  # pragma: no cover - unreachable, keeps this a generator

    monkeypatch.setattr(HistoryStore, "_each_change", always_races)

    with pytest.raises(KeyError):
        store.list_changes("home")
    assert len(calls) == 3


def test_list_changes_returns_empty_when_the_watched_dashboard_is_forgotten_mid_read(
    store, monkeypatch
):
    """No special case: if the dashboard being read is itself forgotten
    by the concurrent `forget` racing it, the rebuilt answer is the
    same empty list an unknown key already produces today - confirmed
    during design, not just asserted. See decision 24."""
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")

    real_each_change = HistoryStore._each_change
    calls: list[int] = []

    def flaky_each_change(self, repo, key, limit=50, before=None):
        calls.append(1)
        if len(calls) == 1:
            store.forget("home")
            raise KeyError(b"simulated: pruned mid-read")
            yield  # pragma: no cover - unreachable, keeps this a generator
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "_each_change", flaky_each_change)

    assert store.list_changes("home") == []
    assert len(calls) == 2


def test_list_changes_is_unaffected_when_nothing_races_it(store):
    """The ordinary path - no exception, ever - must produce exactly
    what it did before this change. A guard against the retry
    machinery changing behavior for the overwhelming majority of
    calls that never hit the race at all."""
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")

    changes = store.list_changes("home")

    assert [c.message for c in changes] == ["second", "first"]


def test_list_changes_retries_a_read_that_raced_forget_with_missing_commit_error(
    store, monkeypatch
):
    """The same race can surface as `MissingCommitError` instead of
    `KeyError` - dulwich's walker raises that one, not a subclass of
    `KeyError`, when an object vanishes mid-walk. Decision 24 requires
    both be caught; this is the companion to
    `test_list_changes_retries_a_read_that_raced_forget` that would go
    unnoticed if a future edit narrowed the caught exceptions to just
    `KeyError`."""
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")

    real_each_change = HistoryStore._each_change
    calls: list[int] = []

    def flaky_each_change(self, repo, key, limit=50, before=None):
        calls.append(1)
        if len(calls) == 1:
            store.forget("gone")
            raise MissingCommitError(b"simulated: pruned mid-read")
            yield  # pragma: no cover - unreachable, keeps this a generator
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "_each_change", flaky_each_change)

    changes = store.list_changes("home")

    assert [c.message for c in changes] == ["second", "first"]
    assert len(calls) == 2


def test_list_changes_retries_a_successful_read_if_head_moved_during_it(
    store, monkeypatch
):
    """A `build()` that raises nothing can still be stale: `_each_change`
    reads `descriptions()` and the revision list as two separate steps.
    A `forget` that runs to completion entirely between them leaves the
    notes dict keyed by shas a moment old, while the walk right after
    it returns shas from the new generation - `notes.get(revision, "")`
    then silently misses, with no exception anywhere to say why (a
    fake on `descriptions()` itself, not on `_each_change`, is what
    actually produces that mix - patching `_each_change` to run
    `forget()` before delegating to the real one only delays both
    reads until after the rewrite, so they'd already agree). Trusted
    only if HEAD read the same right after `build()` returns as it did
    right before this attempt began - not just "no exception was
    raised". See decision 24.

    `forget` needs today's descriptions itself, to carry them onto the
    commits it rewrites - so patching `descriptions()` to race exactly
    once, guarded by a flag rather than a call count, matters: without
    the guard, `forget`'s own internal read would re-enter this fake
    and either recurse into a second `forget` call or be miscounted as
    a second `_each_change` attempt. Attempts are counted separately,
    on `_each_change` itself, for exactly that reason.
    """
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.set_description(second, "the current word on it")

    real_descriptions = HistoryStore.descriptions
    real_each_change = HistoryStore._each_change
    attempts: list[int] = []
    raced = False

    def stale_then_fresh_descriptions(self):
        nonlocal raced
        notes = real_descriptions(self)
        if not raced and len(attempts) == 1:
            raced = True
            store.forget("gone")  # completes fully - old notes, new shas
        return notes

    def counting_each_change(self, repo, key, limit=50, before=None):
        attempts.append(1)
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "descriptions", stale_then_fresh_descriptions)
    monkeypatch.setattr(HistoryStore, "_each_change", counting_each_change)

    changes = store.list_changes("home")

    assert [c.message for c in changes] == ["second", "first"]
    assert changes[0].description == "the current word on it"
    assert len(attempts) == 2


def test_list_changes_retries_when_a_checkpoint_is_present_even_if_head_is_stable(
    store, monkeypatch
):
    """HEAD alone cannot catch every case: a read starting after
    `_point_head` already ran, but before `_rewrite_notes`/
    `_rewrite_tags` finish, sees a HEAD that never moves during its
    own execution at all (issue #27). The checkpoint file (decision
    21) is present for the whole span of `_finish_forget`, not just
    the instant HEAD moves, and catches this case instead. No real
    `forget` runs in this test at all - HEAD never moves - only the
    checkpoint's mere presence must be enough to distrust the result.
    See decision 24.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"

    real_each_change = HistoryStore._each_change
    calls: list[int] = []

    def flaky_each_change(self, repo, key, limit=50, before=None):
        calls.append(1)
        if len(calls) == 1:
            checkpoint.write_text("{}", encoding="utf-8")
            yield from real_each_change(self, repo, key, limit, before)
            return
        checkpoint.unlink()
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "_each_change", flaky_each_change)

    changes = store.list_changes("home")

    assert [c.message for c in changes] == ["second", "first"]
    assert len(calls) == 2


def test_list_changes_raises_when_even_the_last_attempt_stays_unstable(
    store, monkeypatch
):
    """A `build()` that never raises can still never settle: if HEAD
    keeps moving on every attempt, including the last, nothing here
    actually validated that last result either - returning it anyway
    would silently undo every check above it. Raises instead of
    handing back a result nothing has confirmed. See decision 24."""
    store.write_snapshot("home", "a: 1\n", "first")
    for i in range(5):
        store.write_snapshot(f"gone{i}", "b: 1\n", "gone first")

    real_each_change = HistoryStore._each_change
    calls: list[int] = []

    def flaky_each_change(self, repo, key, limit=50, before=None):
        calls.append(1)
        store.forget(f"gone{len(calls) - 1}")  # moves HEAD every single time
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "_each_change", flaky_each_change)

    with pytest.raises(RuntimeError, match="kept racing"):
        store.list_changes("home")
    assert len(calls) == 3


def test_current_head_survives_a_key_error_from_resolving_head_itself(
    store, monkeypatch
):
    """`_resolve` dereferences an object internally, unguarded - a
    `forget` that prunes exactly what it is about to read can make
    even the HEAD observation itself fail with the same exceptions
    `_retrying_a_forget_race` exists to survive. A fresh sentinel
    instead of raising, or answering `None`, keeps the retry loop's
    own safety check from crashing, and keeps two failed observations
    from comparing equal to each other. See decision 24."""
    store.write_snapshot("home", "a: 1\n", "first")
    repo = store._repo()

    def always_races(repo, revision):
        raise KeyError(b"simulated: HEAD itself pruned mid-resolve")

    monkeypatch.setattr(HistoryStore, "_resolve", staticmethod(always_races))

    first = store._current_head(repo)
    second = store._current_head(repo)

    assert first != second


def test_current_head_survives_a_missing_commit_error_from_resolving_head_itself(
    store, monkeypatch
):
    """Companion to the `KeyError` case above - dulwich's walker raises
    `MissingCommitError` instead, not a subclass of `KeyError`, for the
    same underlying race. Decision 24 requires both be caught."""
    store.write_snapshot("home", "a: 1\n", "first")
    repo = store._repo()

    def always_races(repo, revision):
        raise MissingCommitError(b"simulated: HEAD itself pruned mid-resolve")

    monkeypatch.setattr(HistoryStore, "_resolve", staticmethod(always_races))

    first = store._current_head(repo)
    second = store._current_head(repo)

    assert first != second


def test_search_changes_retries_when_it_fetches_its_own_versions(store, monkeypatch):
    """search_changes owns `versions` when the caller does not supply
    it - it can safely rebuild everything, the same way list_changes
    does. See decision 24.

    "gone" is written before "home", not after - see
    `test_list_changes_retries_a_read_that_raced_forget`'s docstring
    for why writing it last would let this pass without `home`'s own
    shas ever actually changing.
    """
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 1\n", "first unique-needle")

    real_each_change = HistoryStore._each_change
    calls: list[int] = []

    def flaky_each_change(self, repo, key, limit=None, before=None):
        calls.append(1)
        if len(calls) == 1:
            store.forget("gone")
            raise KeyError(b"simulated: pruned mid-read")
            yield  # pragma: no cover - unreachable, keeps this a generator
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "_each_change", flaky_each_change)

    found = store.search_changes("home", "unique-needle")

    assert [c.message for c in found] == ["first unique-needle"]
    assert len(calls) == 2


def test_search_changes_retries_with_missing_commit_error_too(store, monkeypatch):
    """Companion to `test_search_changes_retries_when_it_fetches_its_own_versions`,
    with `MissingCommitError` instead of `KeyError` - see
    `test_list_changes_retries_a_read_that_raced_forget_with_missing_commit_error`
    in Task 1 for why both need their own coverage."""
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 1\n", "first unique-needle")

    real_each_change = HistoryStore._each_change
    calls: list[int] = []

    def flaky_each_change(self, repo, key, limit=None, before=None):
        calls.append(1)
        if len(calls) == 1:
            store.forget("gone")
            raise MissingCommitError(b"simulated: pruned mid-read")
            yield  # pragma: no cover - unreachable, keeps this a generator
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "_each_change", flaky_each_change)

    found = store.search_changes("home", "unique-needle")

    assert [c.message for c in found] == ["first unique-needle"]
    assert len(calls) == 2


def test_search_changes_does_not_retry_when_the_caller_supplied_versions(
    store, monkeypatch
):
    """search_changes does not own a caller-supplied `versions` list and
    must not silently rebuild around it: a retry here would return
    changes carrying new shas while the caller's own `versions` (and
    anything the caller derives from it, such as
    operations.async_search's `marks`) still names the old ones -
    every version match in the result would fail with no signal that
    anything went wrong. See decision 24 and issue #20's review."""
    revision = store.write_snapshot("home", "a: 1\n", "first unique-needle")
    store.create_version("home/v1.0.0", "Home", "", revision)
    versions = store.list_versions("home")
    calls: list[int] = []

    def always_fails(self, repo, key, limit=None, before=None):
        calls.append(1)
        raise KeyError(b"simulated: pruned mid-read")
        yield  # pragma: no cover - unreachable, keeps this a generator

    monkeypatch.setattr(HistoryStore, "_each_change", always_fails)

    with pytest.raises(KeyError):
        store.search_changes("home", "unique-needle", versions=versions)
    assert len(calls) == 1


def test_search_changes_is_unaffected_when_nothing_races_it(store):
    """The ordinary path - both with and without a caller-supplied
    `versions` - must produce exactly what it did before this
    change."""
    store.write_snapshot("home", "a: 1\n", "first unique-needle")

    assert [c.message for c in store.search_changes("home", "unique-needle")] == [
        "first unique-needle"
    ]
    versions = store.list_versions("home")
    assert [
        c.message for c in store.search_changes("home", "unique-needle", versions=versions)
    ] == ["first unique-needle"]


def test_commit_times_skips_a_revision_pruned_between_resolve_and_read(
    store, monkeypatch
):
    """A concurrent `forget`'s prune can land between `_resolve`
    succeeding and the very next line reading `commit_time` - see
    decision 24. Left out, exactly like a revision that never resolved
    at all (the method's own docstring already promises that)."""
    revision = store.write_snapshot("home", "a: 1\n", "first")
    monkeypatch.setattr(
        HistoryStore, "_resolve", staticmethod(lambda repo, rev: revision)
    )
    real_getitem = Repo.__getitem__

    def broken_getitem(self, name):
        if name == revision.encode():
            raise KeyError(name)
        return real_getitem(self, name)

    monkeypatch.setattr(Repo, "__getitem__", broken_getitem)

    assert store.commit_times([revision]) == {}


def test_list_dashboards_answers_empty_if_head_is_pruned_mid_read(store, monkeypatch):
    """Same race, HEAD's own tree instead of a revision's commit_time -
    see decision 24. Answers the same as no HEAD at all."""
    store.write_snapshot("home", "a: 1\n", "first")
    head = store.resolve("HEAD")
    monkeypatch.setattr(
        HistoryStore, "_resolve", staticmethod(lambda repo, rev: head)
    )
    real_getitem = Repo.__getitem__

    def broken_getitem(self, name):
        if name == head.encode():
            raise KeyError(name)
        return real_getitem(self, name)

    monkeypatch.setattr(Repo, "__getitem__", broken_getitem)

    assert store.list_dashboards() == []


def test_survey_answers_empty_if_head_is_pruned_mid_read(store, monkeypatch):
    """Same race as `list_dashboards`, in `survey`'s own HEAD-tree
    access - the one before its already-guarded blob-reading loop.
    `_revision_index` is faked to a minimal, valid, empty index so
    this reaches the exact line under test without depending on what
    dulwich's walker touches internally while building a real one. See
    decision 24."""
    store.write_snapshot("home", "a: 1\n", "first")
    head = store.resolve("HEAD")
    monkeypatch.setattr(
        HistoryStore, "_resolve", staticmethod(lambda repo, rev: head)
    )
    fake_index = RevisionIndex(head, {}, {}, set(), {})
    monkeypatch.setattr(HistoryStore, "_revision_index", lambda self, repo: fake_index)
    real_getitem = Repo.__getitem__

    def broken_getitem(self, name):
        if name == head.encode():
            raise KeyError(name)
        return real_getitem(self, name)

    monkeypatch.setattr(Repo, "__getitem__", broken_getitem)

    survey = store.survey()
    assert survey.names == []
    assert survey.live == set()


def test_previous_change_answers_none_if_pruned_mid_walk(store, monkeypatch):
    """`previous_change`'s walk branch (an unindexed revision) consumes
    a dulwich `Walker`, which can raise `MissingCommitError` - not a
    `KeyError` - if an object it needs vanishes mid-walk. See decision
    24. Answers `None`, exactly like a revision that is not a change of
    this dashboard at all.

    `_revision_index` is faked to `None` ("index not ready") so
    `previous_change` falls through to its walk branch unconditionally,
    instead of needing a real rewritten-history fixture to construct a
    revision genuinely outside the index's reach.
    """
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    monkeypatch.setattr(
        HistoryStore, "_resolve", staticmethod(lambda repo, rev: first)
    )
    monkeypatch.setattr(HistoryStore, "_revision_index", lambda self, repo: None)

    def broken_get_walker(self, **kwargs):
        raise MissingCommitError(first.encode())

    monkeypatch.setattr(Repo, "get_walker", broken_get_walker)

    assert store.previous_change("home", first) is None


def test_forget_leaves_no_checkpoint_behind(store):
    """A normal, uninterrupted forget must clean up after itself.

    Decision 21: the checkpoint is only meant to outlive `forget` when
    something interrupted it. `_finish_forget` deletes it as its very
    last step, so an ordinary run - the overwhelming majority of them -
    must never leave it lying around.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.forget("gone")

    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    assert not checkpoint.exists()


def test_forget_writes_a_checkpoint_before_the_first_ref_moves(store, monkeypatch):
    """A real interruption must leave a real, usable checkpoint behind.

    `test_forget_leaves_no_checkpoint_behind` alone cannot catch a
    missing `_write_checkpoint` call: it only checks the file is gone
    *after* a normal run, which holds whether or not one was ever
    written in between. A review of this plan's first draft found that
    exact gap. This interrupts a real `forget()` call instead of
    building a checkpoint by hand, and reads back what it actually left
    on disk.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "gone first")

    def boom(self, repo, notes):
        raise RuntimeError("simulated crash between _point_head and _rewrite_notes")

    monkeypatch.setattr(HistoryStore, "_rewrite_notes", boom)

    with pytest.raises(RuntimeError):
        store.forget("gone")

    key, head, notes, tags = store._read_checkpoint()
    assert key == "gone"
    assert head is not None
    assert "gone" not in store.list_all_dashboards()

def test_repair_finishes_an_interrupted_forget(store, monkeypatch):
    """The exact scenario issue #22 reported, fixed end to end.

    Not a hand-built checkpoint: a real `forget("gone")` call is
    interrupted between `_rewrite_notes` and `_rewrite_tags`, on a
    dashboard whose forgetting *rewrites* another, still-living commit
    - "home"'s second save still has "gone.yaml" sitting in its tree,
    so removing "gone" gives that commit a new sha. Both a note and a
    tag sit on exactly that rewritten commit, which a checkpoint built
    from an unchanged sha could never prove correct.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    home_v2 = store.write_snapshot("home", "a: 2\n", "second")
    store.set_description(home_v2, "a note on the commit that gets rewritten")
    store.create_version("home/v1.0.0", "Home", "", home_v2)

    real_rewrite_tags = HistoryStore._rewrite_tags
    calls = []

    def flaky_rewrite_tags(repo, changed):
        calls.append(changed)
        if len(calls) == 1:
            raise RuntimeError("simulated crash before _rewrite_tags")
        return real_rewrite_tags(repo, changed)

    monkeypatch.setattr(HistoryStore, "_rewrite_tags", staticmethod(flaky_rewrite_tags))

    with pytest.raises(RuntimeError):
        store.forget("gone")

    # The crash already happened: HEAD moved to the rewritten "home"
    # commit and the note followed it, but the tag still names the
    # stale, pre-rewrite one - exactly the half-repaired state issue
    # #22 could not recover from.
    assert "gone" not in store.list_all_dashboards()
    rewritten_head = store.resolve("HEAD")
    assert rewritten_head != home_v2
    assert store.read_version("home", "home/v1.0.0").revision == home_v2
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    assert checkpoint.exists()

    # `real_rewrite_tags`, captured from `HistoryStore._rewrite_tags`
    # above, is the plain function a `@staticmethod` descriptor hands
    # back - assigning it to the class directly, without re-wrapping,
    # would make `self._rewrite_tags(...)` bind `self` as an implicit
    # first argument again and raise `TypeError: takes 2 positional
    # arguments but 3 were given`. Re-wrap it.
    monkeypatch.setattr(HistoryStore, "_rewrite_tags", staticmethod(real_rewrite_tags))
    store.repair_pending_forget()

    assert not checkpoint.exists()
    assert store.resolve("HEAD") == rewritten_head
    assert store.read_version("home", "home/v1.0.0").revision == rewritten_head
    assert store.descriptions() == {
        rewritten_head: "a note on the commit that gets rewritten"
    }
    assert store.write_snapshot("home", "a: 3\n", "third") is not None


def test_repair_does_nothing_when_no_checkpoint_exists(store):
    """The ordinary case - nothing to repair - must not touch anything.

    Not literally free: `_clear_stale_object_locks` still walks
    `objects/` before this checks the checkpoint at all, on purpose -
    it is meant to catch a stale object lock left by an unrelated
    crash even when no forget was involved. What this test pins is
    that the *outcome* is a no-op (nothing about "home" changes), not
    that no work happened.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.repair_pending_forget()
    assert store.read_at("home", "HEAD") == "a: 1\n"


def test_repair_clears_a_stale_object_lock(store):
    """A lock under objects/ left by a dead process must not survive repair.

    Decision 21, correction 5: an earlier version of this fix cleared a
    lock like this locally, right where a write met it, and a review
    found that unsafe (a live writer's own rename could break) and
    incomplete (more than one call site writes objects). Swept
    comprehensively here instead, the same way `_clear_stale_locks`
    already sweeps `refs/` and the top level, and safe for the same
    reason: nothing else in this process can be writing while
    `repair_pending_forget` holds the shared lock.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    stale_lock = store.path / ".git" / "objects" / "ab" / "cdef0123456789.lock"
    stale_lock.parent.mkdir(parents=True)
    stale_lock.touch()

    store.repair_pending_forget()

    assert not stale_lock.exists()


def test_repair_recovers_from_truncated_checkpoint_file(store, caplog):
    """A checkpoint truncated by a power loss must not disable writes permanently.

    Issue #23: If power loss leaves a truncated, unparseable checkpoint,
    `_read_checkpoint` used to crash with JSONDecodeError, which was
    swallowed by `_async_open` while leaving the checkpoint on disk.
    Because every write method checks `_refuse_if_forget_pending()`,
    the integration was permanently unable to write across restarts.
    Repair must log loudly with traceback, remove the corrupted
    checkpoint, and allow writes to proceed.
    """
    import logging

    store.write_snapshot("home", "a: 1\n", "first")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text('{"key": "gone", "head":', encoding="utf-8")

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert not checkpoint.exists()
    assert any("unreadable forget checkpoint" in record.message for record in caplog.records)
    assert any(record.exc_info is not None for record in caplog.records)
    assert store.write_snapshot("home", "a: 2\n", "second") is not None


def test_repair_recovers_from_empty_checkpoint_file(store, caplog):
    """A zero-byte checkpoint file must be removed and logged."""
    import logging

    store.write_snapshot("home", "a: 1\n", "first")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text("", encoding="utf-8")

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert not checkpoint.exists()
    assert any("unreadable forget checkpoint" in record.message for record in caplog.records)
    assert store.write_snapshot("home", "a: 2\n", "second") is not None


def test_repair_recovers_from_malformed_checkpoint_shape(store, caplog):
    """A checkpoint with valid JSON but wrong shape must be removed and logged."""
    import logging

    store.write_snapshot("home", "a: 1\n", "first")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text("{}", encoding="utf-8")

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert not checkpoint.exists()
    assert any("unreadable forget checkpoint" in record.message for record in caplog.records)
    assert store.write_snapshot("home", "a: 2\n", "second") is not None


def test_repair_leaves_checkpoint_intact_on_read_os_error(store, monkeypatch, caplog):
    """A transient I/O error must not destroy a potentially valid plan.

    `OSError` (e.g. PermissionError) proves only that the file could
    not be read right now, never that the plan is corrupt. Deleting it
    would lose a pending forget. The file is left in place, an exception
    is logged, and subsequent writes remain guarded.
    """
    import logging
    from pathlib import Path

    store.write_snapshot("home", "a: 1\n", "first")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text('{"key": "gone"}', encoding="utf-8")

    def broken_read(self, *args, **kwargs):
        raise PermissionError("Permission denied: simulated I/O error")

    monkeypatch.setattr(Path, "read_text", broken_read)

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert checkpoint.exists()
    assert any("I/O error" in record.message for record in caplog.records)
    with pytest.raises(ValueError, match="checkpoint"):
        store.write_snapshot("home", "a: 2\n", "second")


def test_repair_rejects_a_checkpoint_with_an_invalid_head(store, caplog):
    """A well-typed but unreal `head` must never reach `_finish_forget`.

    Korrektur 6 only checks that `head` is a string or `None` - never
    that the string is a real sha. `_point_head` sets the branch ref
    to whatever it is handed; a fabricated value would leave HEAD
    pointing at nothing dulwich can resolve. Issue #24, decision 21
    correction 7.
    """
    import logging

    store.write_snapshot("home", "a: 1\n", "first")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        '{"key": "home", "head": "not-a-sha", "notes": {}, "tags": {}}',
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert not checkpoint.exists()
    assert any("head" in record.message for record in caplog.records)
    assert store.write_snapshot("home", "a: 2\n", "second") is not None


def test_repair_rejects_a_checkpoint_with_an_invalid_note_sha_and_keeps_existing_notes(
    store, caplog
):
    """An invalid note sha must not cost a real, unrelated note.

    `_rewrite_notes` deletes `refs/notes/commits` whole before writing
    entries back - without this check, an invalid sha in `notes` would
    let that deletion happen and only then fail with `AssertionError`,
    taking a genuine, unrelated note down with it. Issue #24, decision
    21 correction 7.
    """
    import logging

    first = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(first, "an important, pre-existing note")
    second = store.write_snapshot("home", "a: 2\n", "second")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        '{"key": "home", "head": "%s", '
        '"notes": {"not-a-valid-sha": "hello"}, "tags": {}}' % second,
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert not checkpoint.exists()
    assert any("notes" in record.message for record in caplog.records)
    assert store.descriptions() == {first: "an important, pre-existing note"}
    assert store.write_snapshot("home", "a: 3\n", "third") is not None


def test_repair_rejects_a_checkpoint_with_an_invalid_tag_ref_and_keeps_packed_refs_intact(
    store, caplog
):
    """An invalid ref name must never reach `add_packed_refs`.

    `_rewrite_tags` writes its whole mapping into `packed-refs` before
    an illegal ref name's `PackedRefsException` stops it - reproduced
    against real `dulwich`: the malformed name lands on disk and every
    later `list_versions()` call fails, not just for the dashboard
    being forgotten. Issue #24, decision 21 correction 7.
    """
    import logging

    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "Home", "", revision)
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        '{"key": "home", "head": "%s", "notes": {}, '
        '"tags": {"refs/tags/home/v1.0.0": "%s", '
        '"refs/tags/../../etc/evil": "%s"}}' % (revision, revision, revision),
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert not checkpoint.exists()
    assert any("tags" in record.message for record in caplog.records)
    assert [v.name for v in store.list_versions()] == ["home/v1.0.0"]
    assert store.write_snapshot("home", "a: 2\n", "second") is not None


def test_repair_rejects_a_checkpoint_whose_key_escapes_the_store(store, caplog):
    """A key with a path traversal must never reach `_drop_from_index`.

    `_drop_from_index` builds `f"{key}.yaml"`/`f"meta/{key}.yaml"` and
    unlinks them with no containment check of its own, unlike every
    live write path, which all go through `_file_for`. Reproduced: an
    unguarded `key` of `"../evil-marker"` resolves outside the store
    entirely. Issue #24, decision 21 correction 7.
    """
    import logging

    revision = store.write_snapshot("home", "a: 1\n", "first")
    marker = store.path.parent / "evil-marker.yaml"
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        '{"key": "../evil-marker", "head": "%s", "notes": {}, "tags": {}}'
        % revision,
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert not checkpoint.exists()
    assert any("key" in record.message for record in caplog.records)
    assert not marker.exists()
    assert store.write_snapshot("home", "a: 2\n", "second") is not None


def test_repair_rejects_a_checkpoint_whose_tag_value_is_not_a_commit_or_tag(
    store, caplog
):
    """A tag value must resolve to a commit or a tag object, nothing else.

    A blob or tree sha passing a plain existence check would let
    `_rewrite_tags` create a tag nothing meaningful can ever resolve -
    reproduced by pointing a tag value at a real, existing tree sha.
    Issue #24, decision 21 correction 7.
    """
    import logging

    revision = store.write_snapshot("home", "a: 1\n", "first")
    repo = store._repo()
    tree_sha = repo[revision.encode()].tree.decode()
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        '{"key": "home", "head": "%s", "notes": {}, '
        '"tags": {"refs/tags/home/v1.0.0": "%s"}}' % (revision, tree_sha),
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert not checkpoint.exists()
    assert any("tags" in record.message for record in caplog.records)
    assert store.list_versions() == []
    assert store.write_snapshot("home", "a: 2\n", "second") is not None


def test_repair_reconciles_a_stale_index_after_an_unreadable_checkpoint(store, monkeypatch):
    """The exact scenario issue #24 reported: a forgotten dashboard's own
    self-healing mechanism bringing it back, when the checkpoint is too
    damaged even to say which key it was about.

    `forget("gone")` is interrupted right after `_point_head` - HEAD
    already rewritten to the tree without "gone", `_drop_from_index`
    never ran - and the checkpoint that would let a later repair
    finish the job is then found corrupted, exactly as it would be
    after the same power loss that interrupted the rewrite in the
    first place (`_write_file` never calls `fsync`, so the checkpoint
    written moments earlier is not guaranteed durable either).
    Truncated to 10 bytes, mid-key: even `_best_effort_checkpoint_key`
    cannot recover which dashboard this was about, forcing the
    generic, whole-index fallback. Without it, the next unrelated
    `write_snapshot` would build its commit from the stale index and
    bring "gone" back into HEAD.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "gone first")

    def boom(self, repo, targets):
        raise RuntimeError("crash right after _point_head")

    monkeypatch.setattr(HistoryStore, "_rewrite_notes", boom)
    with pytest.raises(RuntimeError):
        store.forget("gone")
    monkeypatch.undo()

    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_bytes(checkpoint.read_bytes()[:10])  # truncated mid-key

    store.repair_pending_forget()

    assert not checkpoint.exists()
    assert store.write_snapshot("home", "a: 2\n", "second, after repair") is not None
    assert "gone" not in store.list_all_dashboards()


def test_repair_reconciliation_leaves_a_staged_uncommitted_write_untouched(store, caplog):
    """Reconciliation must only ever act on a path HEAD does not have at
    all - never on one that merely differs in content.

    `write_snapshot` calls `porcelain.add` before `porcelain.commit`;
    if the commit step fails transiently, the index is left staged
    with newer content than HEAD for a path HEAD still has, ready to
    be picked up by the next save. That is indistinguishable, by path
    alone, from an ordinary in-flight write - removing it here would
    throw away a real, still-recoverable save.

    The checkpoint used here is for an unrelated key and carries an
    invalid `head`, so Task A's own validation rejects it and
    `_finish_forget` never runs - this isolates reconciliation's own
    precision from `_finish_forget`'s separate `garbage_collect` step
    (issue #25, not this plan's concern).
    """
    import logging
    from dulwich import porcelain
    from dulwich.repo import Repo

    store.write_snapshot("home", "a: 1\n", "first")
    (store.path / "home.yaml").write_text("a: 2 (staged, not committed)\n", encoding="utf-8")
    porcelain.add(str(store.path), [str(store.path / "home.yaml")])
    staged_sha_before = store._repo().open_index()[b"home.yaml"].sha

    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        '{"key": "unrelated", "head": "not-a-sha", "notes": {}, "tags": {}}',
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    after = Repo(str(store.path)).open_index()
    staged_sha_after = after[b"home.yaml"].sha
    assert staged_sha_after == staged_sha_before
    assert staged_sha_after in Repo(str(store.path)).object_store


def test_repair_reconciliation_spares_an_unrelated_new_dashboards_staged_save(
    store, monkeypatch
):
    """A generic sweep is only a fallback when the checkpoint's own key is
    unreadable - never the first choice when it is not.

    A completely unrelated, brand-new dashboard's first save (added,
    not yet committed) has its path in the index and nowhere in HEAD -
    identical, by path alone, to an orphan left by `forget`. The
    checkpoint's `key` survives here even though its `head` does not,
    so reconciliation must stay scoped to that one key and never touch
    the new dashboard's own entry. Issue #24, decision 21 correction 7
    (found in review of this plan's first draft, which used a
    generic, key-independent sweep unconditionally).
    """
    import json as json_module
    from dulwich import porcelain
    from dulwich.repo import Repo

    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "gone first")

    def boom(self, repo, targets):
        raise RuntimeError("crash right after _point_head")

    monkeypatch.setattr(HistoryStore, "_rewrite_notes", boom)
    with pytest.raises(RuntimeError):
        store.forget("gone")
    monkeypatch.undo()

    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    payload = json_module.loads(checkpoint.read_text(encoding="utf-8"))
    payload["head"] = "not-a-sha"  # key stays readable, semantics do not
    checkpoint.write_text(json_module.dumps(payload), encoding="utf-8")

    (store.path / "newdash.yaml").write_text("z: 1\n", encoding="utf-8")
    porcelain.add(str(store.path), [str(store.path / "newdash.yaml")])
    new_blob_sha = store._repo().open_index()[b"newdash.yaml"].sha

    store.repair_pending_forget()

    after = Repo(str(store.path)).open_index()
    assert b"newdash.yaml" in after
    assert new_blob_sha in Repo(str(store.path)).object_store


def test_repair_reconciliation_surfaces_a_corrupted_tree_instead_of_deleting_everything(
    store,
):
    """A missing HEAD commit or tree object is corruption, not "empty".

    Treating every `KeyError` the same way used to mean a corrupted
    repository looked exactly like a fresh one - every index entry
    considered orphaned and removed. Only `repo.head()`'s own
    `KeyError` (a genuinely unborn branch) means "nothing is live"; a
    `KeyError` opening the commit or tree it names must propagate.
    Issue #24, decision 21 correction 7.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "x: 1\n", "other first")
    repo = store._repo()
    tree_sha = repo[repo.head()].tree.decode()
    object_path = store.path / ".git" / "objects" / tree_sha[:2] / tree_sha[2:]
    object_path.unlink()  # simulate a corrupted repository

    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        '{"key": "nonexistent", "head": null, "notes": {}, "tags": {}}',
        encoding="utf-8",
    )

    with pytest.raises(KeyError):
        store.repair_pending_forget()

    assert set(store._repo().open_index().paths()) == {b"home.yaml", b"other.yaml"}


def test_repair_reconciliation_preserves_committed_nested_legacy_dashboards(store):
    """Reconciliation must not remove committed nested legacy dashboards.

    Keys with slashes (e.g. 'foo/bar') produce nested paths like
    'foo/bar.yaml' and 'meta/foo/bar.yaml'. Dulwich commit trees store
    these in subtrees, not at the root tree level. `live` must collect
    all recursive tree paths so a generic index reconciliation (e.g.
    from an unreadable checkpoint `{}`) does not prune existing legacy
    dashboards from the index and working tree. Issue #24.
    """
    store.write_snapshot("foo/bar", "x: 1\n", "nested first")
    store.write_snapshot("home", "a: 1\n", "home first")

    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text("{}", encoding="utf-8")

    store.repair_pending_forget()

    assert not checkpoint.exists()
    assert (store.path / "foo" / "bar.yaml").exists()
    assert b"foo/bar.yaml" in store._repo().open_index()
    assert store.write_snapshot("home", "a: 2\n", "home second") is not None
    assert store.read_at("foo/bar", "HEAD") == "x: 1\n"


def test_repair_recovers_from_corrupted_unicode_key_in_checkpoint(store, caplog):
    """A checkpoint with an unencodable surrogate key must be removed cleanly.

    JSON with `"key": "\\ud800"` yields a Python string containing a
    lone surrogate code point. `_best_effort_checkpoint_key` must catch
    `UnicodeEncodeError` and return `None` rather than crashing during
    `candidates` path encoding, and `_validate_checkpoint_semantics`
    must reject such keys with `ValueError` so repair removes the broken
    checkpoint and leaves writes unblocked. Issue #24.
    """
    import logging

    store.write_snapshot("home", "a: 1\n", "first")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        r'{"key": "\ud800", "head": null, "notes": {}, "tags": {}}',
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert not checkpoint.exists()
    assert any(
        "key" in record.message or "invalid value" in record.message
        for record in caplog.records
    )
    assert store.write_snapshot("home", "a: 2\n", "second") is not None


def test_a_forgotten_dashboard_cannot_be_read_at_any_revision(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    doomed = store.write_snapshot("gone", "b: 1\n", "gone first")
    store.forget("gone")
    # Not merely delisted: the text is not in the repository any more.
    assert store.read_at("gone", "HEAD") is None
    assert store.resolve(doomed) is None


def test_forgetting_leaves_another_dashboard_whole(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 2\n", "home second")
    store.write_snapshot("gone", "b: 2\n", "gone second")
    store.write_snapshot("home", "a: 3\n", "home third")

    store.forget("gone")
    changes = store.list_changes("home")
    assert [c.message for c in changes] == ["home third", "home second", "home first"]
    assert store.read_at("home", changes[0].revision) == "a: 3\n"
    assert store.read_at("home", changes[1].revision) == "a: 2\n"
    assert store.read_at("home", changes[2].revision) == "a: 1\n"


def test_forgetting_removes_the_metadata_too(store):
    store.write_snapshot("home", "a: 1\n", "home", meta="title: Home\n")
    store.write_snapshot("gone", "b: 1\n", "gone", meta="title: Gone\n")
    store.forget("gone")
    assert store.read_meta_at("gone", "HEAD") is None
    assert store.read_meta_at("home", "HEAD") == "title: Home\n"


def test_a_description_survives_the_rewrite(store):
    first = store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    second = store.write_snapshot("home", "a: 2\n", "home second")
    store.set_description(first, "Before the heating rebuild")
    store.set_description(second, "Sonne oben")

    store.forget("gone")
    # The revisions changed - that is unavoidable - so the descriptions are
    # checked against the messages they belong to, not against shas.
    assert {c.message: c.description for c in store.list_changes("home")} == {
        "home second": "Sonne oben",
        "home first": "Before the heating rebuild",
    }


def test_a_description_on_a_forgotten_change_goes_with_it(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    doomed = store.write_snapshot("gone", "b: 1\n", "gone first")
    store.set_description(doomed, "About the one being forgotten")
    store.forget("gone")
    # Not moved onto a surviving commit: it described a state that is gone,
    # and a description on the wrong state is worse than none.
    assert "About the one being forgotten" not in store.descriptions().values()


def test_a_named_version_survives_the_rewrite(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 2\n", "home second")
    store.create_version("v1", "First release", "what it is about")

    store.forget("gone")
    assert _versions(store) == {"v1": "First release"}
    # And it still points at a commit that exists.
    version = store.list_versions()[0]
    assert store.resolve(version.revision) == version.revision


def test_a_version_of_the_forgotten_dashboard_goes_with_it(store):
    # Decision 13 of the design record made a version belong to ONE
    # dashboard. Moving it to the nearest surviving ancestor was right
    # while it marked a moment of the whole history; measured afterwards,
    # `gone/v1.0.0` survived a forget and pointed at `home`'s commit -
    # `read_at` answered None for it, and the numbering for a future
    # `gone` counted up from a version nobody could reach.
    home = store.write_snapshot("home", "a: 1\n", "home first")
    doomed = store.write_snapshot("gone", "b: 1\n", "gone first")
    store.create_version("gone/v1.0.0", "The one being forgotten", "", doomed)
    store.create_version("home/v1.0.0", "The one that stays", "", home)

    store.forget("gone")
    assert _versions(store) == {"home/v1.0.0": "The one that stays"}
    assert store.list_versions("gone") == []
    # And nothing left behind points at a stranger's commit: every
    # surviving version marks a state of the dashboard it names.
    for version in store.list_versions():
        key, _, _ = version.name.partition("/")
        assert store.read_at(key, version.revision) is not None


def test_a_lightweight_tag_is_rewritten_rather_than_left_stale(store):
    # The ref that defeated `forget` entirely. It has no tag object, so
    # the old collection skipped it and left it pointing into the history
    # that was supposed to be gone.
    store.write_snapshot("home", "a: 1\n", "home first")
    doomed = store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 2\n", "home second")
    _lightweight_tag(store, "by-hand", doomed)

    store.forget("gone")
    repo = Repo(str(store.path))
    try:
        left = list(repo.refs.as_dict(b"refs/tags").values())
        alive = {entry.commit.id for entry in repo.get_walker()}
    finally:
        repo.close()
    # Every surviving tag stands on the rewritten history. `resolve` is no
    # test of that: it finds an unreachable commit just as happily, which
    # is precisely why such a ref kept the forgotten objects from being
    # pruned.
    assert left
    for sha in left:
        assert sha in alive, f"{_as_text(sha)} is not in the rewritten history"


def test_forgetting_clears_the_reflog_that_still_named_it(store):
    """`forget` moves refs without passing dulwich a message, so its own
    writes add no reflog line - but every earlier, ordinary commit did,
    and those lines survive the rewrite untouched. See issue #21.
    """
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone: 1 added")

    logs_dir = store.path / ".git" / "logs"
    before = [f for f in logs_dir.rglob("*") if f.is_file()]
    assert before, "expected a reflog before forget"
    assert any("gone" in f.read_text() for f in before)

    store.forget("gone")

    assert not logs_dir.exists()


def test_forgetting_reports_a_reflog_it_could_not_clear(store, monkeypatch, caplog):
    """`ignore_errors=True` treated a permission problem exactly like the
    common, harmless case of no reflog existing yet - only the second is
    safe to stay silent about. A real failure must stay visible, and
    must not turn an otherwise-successful forget into a reported one.
    """
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")

    def refuse(path, *args, **kwargs):
        raise PermissionError("no permission to remove the reflog")

    monkeypatch.setattr(store_module.shutil, "rmtree", refuse)

    with caplog.at_level("WARNING"):
        assert store.forget("gone") > 0

    assert "gone" not in store.list_all_dashboards()
    assert any("reflog" in record.message.lower() for record in caplog.records)


def test_forgetting_an_unknown_dashboard_changes_nothing(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    before = [c.revision for c in store.list_changes("home")]
    assert store.forget("never-existed") == 0
    assert [c.revision for c in store.list_changes("home")] == before


def test_forgetting_the_only_dashboard_empties_the_history(store):
    store.write_snapshot("only", "a: 1\n", "only first")
    store.write_snapshot("only", "a: 2\n", "only second")
    assert store.forget("only") == 2
    assert store.list_all_dashboards() == []
    assert store.list_changes("only") == []
    # And the repository is still usable afterwards.
    assert store.write_snapshot("fresh", "c: 1\n", "fresh") is not None


def test_forgetting_is_refused_for_nothing_and_survives_an_empty_repo(tmp_path):
    fresh = HistoryStore(tmp_path / "nothing")
    assert fresh.forget("home") == 0


def test_forgetting_reports_a_held_lock_plainly(store):
    """A lock left by an earlier, still-uncleared attempt gets a sentence.

    Not the raw `dulwich.file.FileLocked` - its default `str()` is the
    two paths as a bare tuple, exactly the message issue #19 was filed
    over. `ensure()` already clears a lock left by a *dead* process, so
    what reaches here is the one case it cannot: an earlier `forget` in
    this same, still-running process left one behind without crashing.
    This lock sits at `_point_head`'s own ref, so a checkpoint already
    exists by the time it is met - decision 21 promises a real repair
    here, not just a cleared lock, and the message must still name the
    lock and say to restart.
    """
    store.write_snapshot("gone", "a: 1\n", "first")
    lock = store.path / ".git" / "refs" / "heads" / "master.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.touch()

    with pytest.raises(ValueError, match="lock") as excinfo:
        store.forget("gone")

    message = str(excinfo.value)
    assert "master.lock" in message
    assert "restart" in message.lower()
    assert not message.startswith("(")


def test_forgetting_reports_a_lock_hit_after_head_already_moved(store):
    """A lock met after HEAD has already moved must not claim otherwise.

    `_point_head` and `_rewrite_notes` touch loose refs only and do not
    need `packed-refs.lock` at all; `_rewrite_tags` is what calls
    `add_packed_refs`, after both have already succeeded. A lock found
    only there means the forgotten dashboard is already gone from HEAD
    and its notes have already moved - "the history is unaffected"
    would be the exact false reassurance the review of issue #19's
    first fix found. Decision 21 made a *restart* the true remedy
    (`repair_pending_forget` replays the checkpoint `_forget` wrote
    before `_point_head` ever ran) - this test pins that the message
    still says so, still names the dashboard, and still avoids the two
    phrases that used to be the false reassurance.
    """
    revision = store.write_snapshot("vanished", "a: 1\n", "first")
    store.create_version("vanished/v1.0.0", "Vanished", "", revision)
    store.write_snapshot("staying", "b: 1\n", "first")
    lock = store.path / ".git" / "packed-refs.lock"
    lock.touch()

    with pytest.raises(ValueError, match="lock") as excinfo:
        store.forget("vanished")

    assert "vanished" not in store.list_all_dashboards()
    message = str(excinfo.value)
    assert "vanished" in message
    assert "unaffected" not in message.lower()
    assert "nothing was lost" not in message.lower()
    assert "restart" in message.lower()


def test_forgetting_reports_a_lock_hit_before_any_checkpoint_exists(store, monkeypatch):
    """A lock met while preparing objects, before any checkpoint exists.

    Nothing clears an object lock synchronously any more (decision 21,
    correction 5 - only the background sweep in `repair_pending_forget`
    does, once, off the awaited start). A lock met here means nothing
    was written down to repair automatically: unlike the two lock tests
    above, a restart can only promise to clear the lock, not to finish
    the request - that has to be made again.
    """
    from dulwich.file import FileLocked
    from dulwich.object_store import DiskObjectStore

    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "gone first")

    def always_locked(self, obj):
        raise FileLocked("stale.lock", "stale.lock")

    monkeypatch.setattr(DiskObjectStore, "add_object", always_locked)

    with pytest.raises(ValueError, match="forget") as excinfo:
        store.forget("gone")

    message = str(excinfo.value)
    assert "call forget again" in message.lower()
    assert "gone" in store.list_all_dashboards()
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    assert not checkpoint.exists()


def test_a_second_forget_refuses_while_the_first_is_still_pending(store):
    """A crashed forget's checkpoint must not be stomped on by another.

    Decision 21: two forgets racing to write the same checkpoint file
    would let the second one's plan silently replace the first's,
    losing whatever the first one was going to finish. Task 2's guard
    - checked at the very top of `forget`, before anything else - is
    what prevents this.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "other first")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="forget"):
        store.forget("other")

    assert checkpoint.read_text(encoding="utf-8") == "{}"


def test_forget_on_the_checkpoints_own_key_still_refuses(store):
    """Guards the exact issue #22 regression, not just an unrelated one.

    The test above, forgetting a dashboard that is still plainly
    present, cannot tell a correctly-placed guard from one placed
    *after* the "nothing to forget" early returns: `other` being
    present means both placements reach the guard anyway. A guard
    placed after those returns would instead let `forget` on the
    *checkpoint's own key* silently report 0 - because that key
    already looks exactly like one that was never recorded, once a
    checkpoint is pending past `_point_head`. A key that genuinely was
    never written reproduces that same appearance without needing a
    real crash to set it up.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="forget"):
        store.forget("never-written")


def test_writes_refuse_while_a_forget_checkpoint_is_pending(store):
    """Every write path must see a pending checkpoint the same way.

    Decision 21, correction 1: replaying a stale checkpoint after
    something else wrote in the meantime could roll HEAD back over that
    write, or drop a note it added. The guard has to run on every call,
    not once per process, so nothing can slip in between a crash and the
    next restart's repair. The checkpoint's *content* doesn't matter
    here - only that the file exists - so it is faked by hand; Task 3
    is what makes `forget` write a real one.

    A checkpoint that never resolves - exactly what this test fakes -
    also means `list_changes` can never pass decision 24's trust check
    either: every one of its three attempts still finds the file there.
    Unlike a write's immediate refusal, a read only gives up once the
    retry budget is spent, and with `RuntimeError` rather than
    `ValueError` - it was never told to refuse outright, only found
    nothing across the whole budget it could vouch for.
    """
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "Home", "", first)
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="forget"):
        store.write_snapshot("home", "a: 2\n", "second")
    with pytest.raises(ValueError, match="forget"):
        store.mark_deleted("home", "gone")
    with pytest.raises(ValueError, match="forget"):
        store.create_version("home/v1.0.1", "Home", "", first)
    with pytest.raises(ValueError, match="forget"):
        store.retitle_version("home", "home/v1.0.0", "New title", "")
    with pytest.raises(ValueError, match="forget"):
        store.remove_version("home", "home/v1.0.0")
    with pytest.raises(ValueError, match="forget"):
        store.set_description(first, "a note")
    with pytest.raises(ValueError, match="forget"):
        store.forget("home")

    # A read that goes through decision 24's retry helper distrusts a
    # checkpoint that never resolves the same way a write refuses it -
    # just later, after the retry budget is spent, and with a
    # `RuntimeError` rather than an immediate `ValueError`. A read
    # outside that machinery - `read_at`, one known revision, no
    # rebuild-and-compare - is genuinely unaffected, the same as
    # decision 21 always promised.
    with pytest.raises(RuntimeError, match="kept racing"):
        store.list_changes("home")
    assert store.read_at("home", "HEAD") == "a: 1\n"


def _lightweight_tag(store, name: str, revision: str) -> None:
    """A tag made by hand: a ref straight to the commit, no tag object.

    Exactly what somebody gets from `git tag <name>` in the repository the
    README invites them to look inside, and decision 13 of the design
    record says such a tag stays visible.
    """
    repo = Repo(str(store.path))
    try:
        repo.refs[f"refs/tags/{name}".encode()] = revision.encode()
    finally:
        repo.close()


def _blobs(store) -> list[bytes]:
    repo = Repo(str(store.path))
    try:
        return [
            repo[sha].data for sha in repo.object_store if repo[sha].type_name == b"blob"
        ]
    finally:
        repo.close()


def test_the_forgotten_text_is_gone_from_the_object_store(store):
    # The literal reading of "for good". Rewriting refs alone leaves every
    # blob on disk, unreachable but readable by anyone who knows a sha -
    # and `resolve` knows how to find them. This is the check that the
    # promise is kept and not merely made.
    #
    # With a lightweight tag in the way, because that is what defeated it:
    # `_raw_tags` collected only annotated tags, so a hand-made one was
    # neither deleted nor rewritten, went on pointing at a pre-rewrite
    # commit, and kept the whole old history reachable - garbage_collect
    # prunes nothing a ref can still reach. Measured before the fix:
    # `forget` reported success and the text below was still readable.
    store.write_snapshot("home", "a: 1\n", "home")
    doomed = store.write_snapshot("gone", "confidential: yes\n", "gone")
    _lightweight_tag(store, "made-by-hand", doomed)
    store.forget("gone")

    blobs = _blobs(store)
    assert blobs, "the surviving dashboard should still have its blob"
    assert not any(b"confidential" in blob for blob in blobs)


def test_versions_can_be_asked_for_one_dashboard(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("solar", "b: 1\n", "solar first")
    store.create_version("home/v1.0.0", "Home", "", first)
    store.create_version("solar/v1.0.0", "Solar", "", second)
    assert [v.name for v in store.list_versions("home")] == ["home/v1.0.0"]
    assert [v.name for v in store.list_versions("solar")] == ["solar/v1.0.0"]
    assert len(store.list_versions()) == 2


def test_the_same_version_twice_is_refused(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "Home", "", first)
    with pytest.raises(ValueError, match="already exists"):
        store.create_version("home/v1.0.0", "Again", "", first)


def test_a_flat_tag_blocks_the_namespace_below_it(store):
    # git cannot hold a tag `home` and a tag `home/v1.0.0` at once - the
    # ref file and the ref directory are the same path. Measured: dulwich
    # raises IsADirectoryError and leaves a stray .lock behind, so this is
    # refused up front rather than suffered.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home", "Loose", "", first)
    with pytest.raises(ValueError, match="home"):
        store.create_version("home/v1.0.0", "Blocked", "", first)


def test_a_namespace_blocks_the_flat_tag_above_it(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    with pytest.raises(ValueError, match="home/v1.0.0"):
        store.create_version("home", "Loose", "", first)


def test_a_lightweight_tag_in_a_namespace_is_reported(store):
    # `list_versions` used to skip it, so `candidates` never saw it and
    # offered its number again - and `_refuse_colliding_name`, which reads
    # the raw refs, then refused in the middle of the dialog. Decision 13
    # of the design record promises such a tag is shown, not hidden.
    first = store.write_snapshot("heizung", "a: 1\n", "first")
    _lightweight_tag(store, "heizung/v1.0.0", first)

    listed = store.list_versions("heizung")
    assert [v.name for v in listed] == ["heizung/v1.0.0"]
    # No message on a lightweight tag, so nothing to show as title or text.
    assert (listed[0].title, listed[0].description) == ("", "")
    assert listed[0].revision == first

    # And therefore no refusal mid-dialog: what the buttons offer is free.
    offered = candidates("heizung", [v.name for v in listed])
    assert offered["current"] == "heizung/v1.0.0"
    store.create_version(offered["patch"], "Next", "", first)
    assert offered["patch"] in _versions(store)


def test_a_version_says_when_it_was_made(store):
    # The panel's simple mode lists nothing but versions, and versions
    # a routine makes carry the same title over and over - on the test
    # bench a whole screen of them read alike. The time is one of the
    # two marks that tell them apart, and it was read here already, to
    # sort by, then dropped before any caller could see it.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)

    made = store.list_versions("home")[0]
    assert made.timestamp > 0

    # A tag made by hand carries no time of its own. It is reported all
    # the same, with the time of the commit it marks - the one this list
    # is already ordered by, so the panel draws no order of its own.
    _lightweight_tag(store, "home/v1.1.0", first)
    marked = {v.name: v.timestamp for v in store.list_versions("home")}
    assert marked["home/v1.1.0"] == store.list_changes("home")[0].timestamp


# -- giving an existing version new words -------------------------------
#
# The two fields the create dialog asks for, filled in or corrected
# afterwards. A tag object is immutable - its name *is* the hash of its
# contents - so this builds a new one and points the same ref at it. The
# commit it marks and the time it was made come along unchanged, and so
# does the marker of a version nobody asked for.


def test_a_version_can_be_given_new_words(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "the old note", first)

    written = store.retitle_version("home", "home/v1.0.0", "Before the rework", "why")
    # Answered, rather than read back: the caller needs the result in the
    # one shape every version leaves in, and a second read would be a
    # second scan of the whole tag namespace.
    assert (written.title, written.description) == ("Before the rework", "why")
    made = store.list_versions("home")[0]
    assert (made.title, made.description) == ("Before the rework", "why")


def test_new_words_move_neither_the_mark_nor_the_time_it_was_made(store):
    # The condition this was asked for under, in as many words: the
    # order must not change. `list_versions` orders by the time the tag
    # was made, so a rebuilt tag carrying a fresh time would climb to the
    # top of the list the moment somebody corrected a typo in it - and
    # `by_number` is no protection, because the panel shows times too and
    # the all-dashboards list has no numbers to fall back on.
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", first)
    store.create_version("home/v2.0.0", "Second", "", second)
    before = {v.name: (v.revision, v.timestamp) for v in store.list_versions("home")}

    written = store.retitle_version("home", "home/v1.0.0", "Renamed", "")

    after = {v.name: (v.revision, v.timestamp) for v in store.list_versions("home")}
    assert after == before
    # And the answer says the same, so a caller needs no second read to
    # know the version did not move.
    assert (written.revision, written.timestamp) == before["home/v1.0.0"]
    # Nothing but the one named is touched.
    assert {v.name: v.title for v in store.list_versions("home")}["home/v2.0.0"] == (
        "Second"
    )


def test_a_version_nobody_asked_for_stays_marked_as_such(store):
    # The marker is the first line of the stored description, and it is
    # machine-read: the day mark asks it which days already carry an
    # automatic version. Carried over here rather than by the caller, so
    # the next writer of a version's words cannot forget it - a version
    # that lost it on being renamed would let its day be marked twice.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version(
        "home/v1.0.0", "3 September 2026", versions.automatic_description(), first
    )

    written = store.retitle_version("home", "home/v1.0.0", "Before the rework", "why")

    assert versions.read_description(written.description) == ("why", True)
    stored = store.list_versions("home")[0]
    assert versions.read_description(stored.description) == ("why", True)


def test_a_version_somebody_made_gains_no_marker(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "mine", first)
    written = store.retitle_version("home", "home/v1.0.0", "First", "still mine")
    assert versions.read_description(written.description) == ("still mine", False)


def test_a_retitled_version_still_reads_back_by_its_name(store):
    # It has to stay the same *kind* of thing. A ref left pointing at
    # anything but an annotated tag would still list, and `read_at` over
    # the name - which is how going back to a version works - would
    # start answering None.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    store.retitle_version("home", "home/v1.0.0", "Renamed", "")
    assert store.read_at("home", "home/v1.0.0") == "a: 1\n"


def test_everything_the_tag_carried_but_its_words_comes_along(store):
    # Built with `copy()` rather than from a list of fields worth
    # keeping. Measured on dulwich 1.2.14: a hand-written list of the six
    # that seemed to matter dropped `_tag_timezone_neg_utc`, so a tag
    # made at `-0000` came back as `+0000`. What must *not* come along is
    # the signature - one over the old words says nothing about the new.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    repo = Repo(str(store.path))
    try:
        tag = repo[repo.refs[b"refs/tags/home/v1.0.0"]]
        tag._tag_timezone_neg_utc = True
        tag.signature = b"-----BEGIN PGP SIGNATURE-----\nx\n"
        repo.object_store.add_object(tag)
        repo.refs[b"refs/tags/home/v1.0.0"] = tag.id
        was = (tag.tagger, tag.tag_time, tag.tag_timezone)
    finally:
        repo.close()

    store.retitle_version("home", "home/v1.0.0", "Renamed", "")

    repo = Repo(str(store.path))
    try:
        now = repo[repo.refs[b"refs/tags/home/v1.0.0"]]
        assert (now.tagger, now.tag_time, now.tag_timezone) == was
        assert now._tag_timezone_neg_utc is True
        assert now.signature is None
    finally:
        repo.close()


def test_another_dashboards_version_cannot_be_reached(store):
    # The whole ownership fence, and it is `_owns` rather than a
    # `startswith`: a command taking a bare ref name would otherwise
    # rewrite any tag in the repository.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "other")
    store.create_version("other/v1.0.0", "Theirs", "", first)
    with pytest.raises(ValueError, match="not a version of home"):
        store.retitle_version("home", "other/v1.0.0", "Renamed", "")
    assert store.list_versions("other")[0].title == "Theirs"


def test_an_unknown_version_is_refused_with_a_sentence(store):
    # A ValueError like every other refusal `create_version` gives, so
    # the one place that already catches those needs no second branch.
    store.write_snapshot("home", "a: 1\n", "first")
    with pytest.raises(ValueError, match="unknown version"):
        store.retitle_version("home", "home/v9.9.9", "Nothing", "")


def test_a_version_made_by_hand_has_no_words_to_change(store):
    # A lightweight tag is the ref itself and carries no message. Giving
    # it one would hand somebody back a different kind of tag than the
    # one they made - the same line `_rewrite_tags` draws.
    first = store.write_snapshot("home", "a: 1\n", "first")
    _lightweight_tag(store, "home/v1.0.0", first)
    with pytest.raises(ValueError, match="made by hand"):
        store.retitle_version("home", "home/v1.0.0", "Renamed", "")


def test_retitling_in_an_empty_repository_is_refused_not_built(store, tmp_path):
    # And builds no repository on the way. Every other write here calls
    # `_ensure` first; this one cannot need to, because it only ever
    # changes something that already exists. Creating a history in order
    # to report that it holds no such version would leave one behind
    # that nobody asked for.
    fresh = HistoryStore(tmp_path / "nothing")
    with pytest.raises(ValueError, match="unknown version"):
        fresh.retitle_version("home", "home/v1.0.0", "Renamed", "")
    assert not (tmp_path / "nothing").exists()


# -- and which kind of tag a version came from --------------------------


def test_a_version_says_whether_it_has_words_at_all(store):
    # Carried so that nobody has to infer it from an empty title, which
    # is a field a person is now allowed to rewrite. `list_versions` has
    # always branched on this and used to throw the answer away.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    _lightweight_tag(store, "home/v2.0.0", first)
    kinds = {v.name: v.annotated for v in store.list_versions("home")}
    assert kinds == {"home/v1.0.0": True, "home/v2.0.0": False}


def test_a_name_git_cannot_accept_is_refused_as_an_answer(store):
    # dulwich raises RefFormatError, which inherits straight from
    # Exception: `operations.py` catches ValueError, the WebSocket wrapper
    # swallows what escapes and `services.py` does not. A name git cannot
    # accept is the same class of answer as a name that collides, so it
    # leaves this module as the same kind of exception.
    first = store.write_snapshot("home", "a: 1\n", "first")
    with pytest.raises(ValueError, match="git cannot use that as a version name"):
        store.create_version("home/v1 0.0", "Spaces", "", first)
    with pytest.raises(ValueError, match="git cannot use that as a version name"):
        store.create_version("home/v1.0.0^", "Caret", "", first)
    # Nothing half-made left behind.
    assert store.list_versions() == []


def test_a_deletion_commit_holds_no_state_to_return_to(store):
    # The fact under the refusal in `operations.async_create_version`: at
    # the commit that records a deletion the dashboard's file has left the
    # tree, so there is no state there anybody could come back to - and
    # that commit is the newest entry in a deleted dashboard's history,
    # which is exactly where a version without a revision would land.
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.mark_deleted("gone", "gone: dashboard deleted")
    newest = store.list_changes("gone")[0]

    # A known revision - the separation `_state_at` makes matters here:
    # this is a statement about the dashboard, not about the input.
    assert store.resolve(newest.revision) == newest.revision
    assert store.read_at("gone", newest.revision) is None
    # The state before it is still there, and that one can be marked.
    before = store.previous_change("gone", newest.revision)
    assert store.read_at("gone", before) == "b: 1\n"


def _tree_and_blob(store, key: str, revision: str) -> tuple[str, str]:
    """The tree and blob ids behind one recorded state.

    Both are ordinary git objects sitting in the same object store as the
    commits, so both answer to a full id and to an abbreviated prefix.
    """
    repo = Repo(str(store.path))
    try:
        tree = repo[revision.encode()].tree
        _, blob = repo[tree].lookup_path(repo.get_object, f"{key}.yaml".encode())
        return _as_text(tree), _as_text(blob)
    finally:
        repo.close()


def test_an_object_that_is_not_a_commit_resolves_to_nothing(store):
    # A blob and a tree used to resolve to themselves, and every caller
    # then treated the answer as a commit: `read_at` reaches for `.tree`
    # and raised AttributeError - a generic failure through the WebSocket,
    # a bare traceback through `services.py`. Worse, `create_version`
    # accepted one and made a tag that can never be returned to. Such a
    # tag can be taken away since decision 18; the refusal stands on the
    # tag being useless, not on being stuck with it. None already means
    # "unknown revision" to every caller, so that is what these are now.
    first = store.write_snapshot("home", "a: 1\n", "first")
    tree, blob = _tree_and_blob(store, "home", first)

    assert store.resolve(blob) is None
    assert store.resolve(tree) is None
    # The abbreviated form is the one a person is likely to paste.
    assert store.resolve(blob[:8]) is None
    assert store.resolve(tree[:8]) is None
    # And nothing downstream crashes on one.
    assert store.read_at("home", blob) is None
    assert store.read_at("home", tree) is None
    assert store.previous_change("home", blob) is None

    with pytest.raises(ValueError, match="unknown revision"):
        store.create_version("home/v1.0.0", "On a blob", "", blob)
    with pytest.raises(ValueError, match="unknown revision"):
        store.create_version("home/v1.0.1", "On a tree", "", tree)
    # Nothing half-made left behind: a version that cannot be returned to
    # would sit in the list forever.
    assert store.list_versions() == []


def test_a_lightweight_tag_on_a_blob_is_not_a_state_to_return_to(store):
    # The second route to the same fault, and one nobody has to type: a
    # tag made by hand in the repository the README invites people to look
    # inside. `list_versions` reports it, as decision 13 of the design
    # record promises, so its revision travels straight into `read_at`.
    first = store.write_snapshot("home", "a: 1\n", "first")
    _, blob = _tree_and_blob(store, "home", first)
    _lightweight_tag(store, "home/v1.0.0", blob)

    listed = store.list_versions("home")
    assert [v.name for v in listed] == ["home/v1.0.0"]
    # No crash, and no pretence that there is a state there.
    assert store.read_at("home", listed[0].revision) is None
    assert store.resolve("home/v1.0.0") is None
    assert store.read_at("home", "home/v1.0.0") is None


def test_a_tag_blocks_every_namespace_it_stands_in(store):
    # A version *name* may hold more than one segment even though a
    # dashboard *key* may not: a tag made by hand does, and so does every
    # tag written before `keys.is_safe_key` existed. The blocking parent
    # of `dh-slash/check/v1.0.0` is then `dh-slash/check`, not
    # `dh-slash`. Looking only at the first segment let the real collision
    # through, and it then surfaced raw: measured on dulwich 1.2.14 it is
    # a NotADirectoryError here, the deeper cousin of the
    # IsADirectoryError this refusal was written against.
    first = store.write_snapshot("dh-slash", "a: 1\n", "first")
    store.create_version("dh-slash/check", "Loose", "", first)
    with pytest.raises(ValueError, match="dh-slash/check"):
        store.create_version("dh-slash/check/v1.0.0", "Blocked", "", first)


def test_a_tag_in_the_first_segment_still_blocks(store):
    # The other end of the same name: `dh-slash` is a proper prefix too,
    # so it blocks just as it always did for a name of one segment.
    first = store.write_snapshot("dh-slash", "a: 1\n", "first")
    store.create_version("dh-slash", "Loose", "", first)
    with pytest.raises(ValueError, match="dh-slash"):
        store.create_version("dh-slash/check/v1.0.0", "Blocked", "", first)


def test_a_key_that_leaves_the_store_writes_nothing(store, tmp_path):
    """The store refuses rather than writing beside itself.

    Measured before this check existed: a dashboard registered over the
    API under the url_path "../weiter-weg" was recorded to a file next to
    the repository, where nothing reads it back and nothing removes it.
    `keys.is_safe_key` turns such a key away earlier; this is the store
    answering for its own boundary, whoever calls it.
    """
    with pytest.raises(ValueError, match="does not name a file in the store"):
        store.write_snapshot("../weiter-weg", "a: 1\n", "escaped")
    assert not (tmp_path / "weiter-weg.yaml").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["history"]


def test_an_absolute_key_writes_nothing(store, tmp_path):
    with pytest.raises(ValueError, match="does not name a file in the store"):
        store.write_snapshot("/absolut", "a: 1\n", "escaped")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["history"]


def test_a_key_that_leaves_the_store_deletes_nothing(store):
    # Refused earlier than the boundary check, and for a plainer reason:
    # there is no such record to delete. Worth pinning anyway - the answer
    # has to be "nothing happened", not an exception out of dulwich.
    assert store.mark_deleted("../weiter-weg", "gone") is None


def test_a_nested_key_stays_readable_and_deletable(store):
    """A record from before the key rule must not get stuck.

    A key holding a slash makes a nested file. That is wrong, and no new
    one can appear - but one already written has to stay reachable, or
    its history sits where no operation can either read or end it. Which
    is why the boundary check refuses escaping paths and not nested ones.
    """
    first = store.write_snapshot("energie/x", "a: 1\n", "legacy")
    assert first is not None
    assert store.read_at("energie/x", "HEAD") == "a: 1\n"
    assert store.mark_deleted("energie/x", "energie/x: dashboard deleted") is not None
    assert store.read_at("energie/x", "HEAD") is None


# -- taking a version away ---------------------------------------------


def test_a_version_can_be_taken_away(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "a note", first)

    removed = store.remove_version("home", "home/v1.0.0")

    # Answered with what was taken, so a caller can say what is gone
    # without a second read - and the log line is then the only place
    # those words still exist.
    assert (removed.name, removed.title, removed.description) == (
        "home/v1.0.0",
        "First",
        "a note",
    )
    assert store.list_versions("home") == []


def test_the_state_a_taken_version_marked_is_untouched(store):
    # The whole point of decision 18, and the one test that would catch a
    # slip into `forget` territory: the mark goes, the state stays.
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", first)
    head_before = store.list_changes("home")[0].revision

    store.remove_version("home", "home/v1.0.0")

    assert store.read_at("home", first) == "a: 1\n"
    assert [c.revision for c in store.list_changes("home")] == [second, first]
    assert store.list_changes("home")[0].revision == head_before


def test_a_description_on_the_state_survives_the_version_being_taken(store):
    # Notes hang on the commit, versions on a ref beside it. Taking the
    # ref must not go near `refs/notes/commits` - and it is worth its own
    # test because `forget`, the other operation that removes a tag,
    # rewrites the notes as part of its work.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(first, "why I did it")
    store.create_version("home/v1.0.0", "First", "", first)

    store.remove_version("home", "home/v1.0.0")

    assert store.list_changes("home")[0].description == "why I did it"


def test_only_the_named_version_goes(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", first)
    store.create_version("home/v2.0.0", "Second", "", second)

    store.remove_version("home", "home/v1.0.0")

    assert [v.name for v in store.list_versions("home")] == ["home/v2.0.0"]


def test_another_dashboards_version_cannot_be_taken_away(store):
    # The same fence `retitle_version` has, and it has to be `_owns`
    # rather than a `startswith`: a command taking a bare ref name would
    # otherwise delete any tag in the repository.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "other")
    store.create_version("other/v1.0.0", "Theirs", "", first)

    with pytest.raises(ValueError, match="not a version of home"):
        store.remove_version("home", "other/v1.0.0")

    assert [v.name for v in store.list_versions("other")] == ["other/v1.0.0"]


def test_a_nested_key_does_not_reach_into_a_deeper_namespace(store):
    # Measured on 2026-09-04 for `forget`: tested with `startswith`
    # alone, "dh-slash/check/" also claimed the versions of a dashboard
    # whose key holds one more slash. Home Assistant accepts such a
    # url_path, so this is a real dashboard and not a contrivance.
    first = store.write_snapshot("dh-slash/check", "a: 1\n", "first")
    store.create_version("dh-slash/check/deeper/v1.0.0", "Deeper", "", first)

    with pytest.raises(ValueError, match="not a version of dh-slash/check"):
        store.remove_version("dh-slash/check", "dh-slash/check/deeper/v1.0.0")


def test_an_unknown_version_cannot_be_taken_away(store):
    store.write_snapshot("home", "a: 1\n", "first")
    with pytest.raises(ValueError, match="unknown version"):
        store.remove_version("home", "home/v9.9.9")


def test_a_version_made_by_hand_can_be_taken_away(store):
    # The one place this parts company with `retitle_version`, and
    # deliberately. Renaming a lightweight tag would hand back a
    # different kind of tag than the one somebody made; taking it away
    # gives nothing back. And it has to be possible: a lightweight
    # `home/v1.0.0` counts when the next number is worked out, so one
    # that could not be removed would hold a number for ever.
    first = store.write_snapshot("home", "a: 1\n", "first")
    _lightweight_tag(store, "home/v1.0.0", first)

    removed = store.remove_version("home", "home/v1.0.0")

    assert (removed.name, removed.annotated) == ("home/v1.0.0", False)
    assert store.list_versions("home") == []
    assert store.read_at("home", first) == "a: 1\n"


def test_taking_a_version_in_an_empty_repository_is_refused_not_built(tmp_path):
    # As with `retitle_version`: no `_ensure()`, because this can only
    # ever take away something that exists. Building a history in order
    # to report that it holds no such version would leave one behind
    # that nobody asked for.
    fresh = HistoryStore(tmp_path / "nothing")
    with pytest.raises(ValueError, match="unknown version"):
        fresh.remove_version("home", "home/v1.0.0")
    assert not (tmp_path / "nothing").exists()


def test_reading_one_version_gives_what_the_list_gives(store):
    # `read_version` and `list_versions` must not drift: the preview of a
    # removal is built from the first and the panel's list from the
    # second, and a field present in one and missing in the other is the
    # kind of difference a frontend renders as False. One builder for
    # both is the fix, and this is the test that keeps it.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "a note", first)
    _lightweight_tag(store, "home/v2.0.0", first)

    listed = store.list_versions("home")
    assert len(listed) == 2
    for version in listed:
        assert store.read_version("home", version.name) == version


# -- a history longer than any cap ---------------------------------------
#
# Measured on 2026-09-03: `list_all_dashboards` and `previous_change`
# stopped after 1000 commits. A dashboard deleted a thousand saves ago
# vanished from the panel's list and could no longer be forgotten, and
# undo on an old revision claimed "this is the first recorded state" - an
# invisible gap, which the docstrings name as the worst possible failure.
# At one commit per save that is months, not years.


def _pad_history(store, count, path=None):
    """Append `count` commits straight into the object store.

    Through `porcelain.commit` this takes fourteen seconds for a thousand
    commits (the index is rewritten each time); as raw objects it takes
    under a second. `path`, when given, changes that one blob in every
    commit so the walk filtered on it sees every commit too.
    """
    from dulwich.objects import Blob, Commit, Tree

    repo = Repo(str(store.path))
    try:
        # Whatever branch HEAD points at, not a name: dulwich's default
        # is "master" today, and a pad on the wrong branch would leave
        # the noise unreachable and the tests passing for no reason.
        branch = repo.refs.follow(b"HEAD")[0][-1]
        head = repo.refs[branch]
        for number in range(count):
            parent = repo[head]
            tree = repo[parent.tree]
            if path is not None:
                blob = Blob.from_string(f"noise: {number}\n".encode())
                repo.object_store.add_object(blob)
                fresh = Tree()
                for entry in tree.items():
                    fresh.add(entry.path, entry.mode, entry.sha)
                fresh.add(path.encode(), 0o100644, blob.id)
                repo.object_store.add_object(fresh)
                tree = fresh
            commit = Commit()
            commit.tree = tree.id
            commit.parents = [head]
            commit.author = commit.committer = b"noise <noise@localhost>"
            commit.author_time = commit.commit_time = parent.commit_time + 1 + number
            commit.author_timezone = commit.commit_timezone = 0
            commit.message = f"noise {number}".encode()
            repo.object_store.add_object(commit)
            head = commit.id
        repo.refs[branch] = head
    finally:
        repo.close()


def test_a_dashboard_deleted_a_thousand_saves_ago_is_still_listed(store):
    store.write_snapshot("gone", "a: 1\n", "gone first")
    store.mark_deleted("gone", "gone: dashboard deleted")
    store.write_snapshot("busy", "b: 1\n", "busy first")
    _pad_history(store, 1005, path="busy.yaml")
    assert "gone" in store.list_all_dashboards()


def test_the_state_before_a_change_is_found_however_old_it_is(store):
    first = store.write_snapshot("busy", "b: 1\n", "busy first")
    second = store.write_snapshot("busy", "b: 2\n", "busy second")
    _pad_history(store, 1005, path="busy.yaml")
    assert store.previous_change("busy", second) == first


# -- a version that vanishes while the list is being read -----------------


def test_a_version_gone_between_listing_and_reading_is_skipped(store, monkeypatch):
    """Measured on 2026-09-04 against the test bench: `forget` deletes
    every tag and writes it back, and a `history` call that ran at that
    moment saw `busy-board/v0.56.0` in the list and then found no ref
    behind it - KeyError, and the whole history answered with an error.
    dulwich's own `as_dict` skips exactly this; so does this.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "One", "")
    real_repo = store._repo

    def repo_with_a_phantom():
        repo = real_repo()
        listed = repo.refs.as_dict

        def as_dict(base=None):
            found = listed(base)
            if base == b"refs/tags":
                # Listed, but there is no ref behind it any more.
                found[b"home/v9.9.9"] = found[b"home/v1.0.0"]
            return found

        monkeypatch.setattr(repo.refs, "as_dict", as_dict)
        return repo

    monkeypatch.setattr(store, "_repo", repo_with_a_phantom)
    assert [v.name for v in store.list_versions("home")] == ["home/v1.0.0"]


# -- a version belongs to one dashboard, and "foo/" is not "foo/bar/" ------
#
# Found by a second review on 2026-09-04: `forget("foo")` deleted
# `foo/bar/v1.0.0`, the version of a legacy dashboard whose key holds a
# slash, because "belongs to foo" was tested with startswith("foo/").
# `list_versions("foo")` listed it for the same reason. A version's name
# is `<key>/v...`, so what follows the key's own slash is one segment.


def test_forgetting_a_dashboard_keeps_the_versions_of_a_nested_legacy_key(store):
    store.write_snapshot("foo", "a: 1\n", "foo first")
    store.mark_deleted("foo", "foo gone")
    store.write_snapshot("foo/bar", "child: yes\n", "child first")
    store.create_version("foo/bar/v1.0.0", "Child", "")
    store.forget("foo")
    assert [v.name for v in store.list_versions()] == ["foo/bar/v1.0.0"]


def test_a_nested_legacy_key_s_versions_are_not_listed_under_its_prefix(store):
    store.write_snapshot("foo", "a: 1\n", "foo first")
    store.create_version("foo/v1.0.0", "Mine", "")
    store.write_snapshot("foo/bar", "child: yes\n", "child first")
    store.create_version("foo/bar/v1.0.0", "Child", "")
    assert [v.name for v in store.list_versions("foo")] == ["foo/v1.0.0"]


# -- every dashboard, with the name each last had, in one walk -------------
#
# Why one walk and not one per deleted dashboard: `HistoryStore.survey`.


def test_the_survey_names_every_dashboard_and_what_each_was_last_called(store):
    store.write_snapshot("live", "a: 1\n", "live first", meta="title: Live\n")
    store.write_snapshot("gone", "b: 1\n", "gone first", meta="title: Old\n")
    store.write_snapshot("gone", "b: 2\n", "gone renamed", meta="title: Gone\n")
    store.mark_deleted("gone", "gone deleted")
    survey = store.survey()
    assert survey.names == ["gone", "live"]
    assert survey.live == {"live"}
    assert survey.last_meta == {"gone": "title: Gone\n", "live": "title: Live\n"}


def test_the_survey_follows_head(store):
    # Cached by HEAD, so every write has to be seen by the next call.
    store.write_snapshot("one", "a: 1\n", "first")
    assert store.survey().names == ["one"]
    store.write_snapshot("two", "b: 1\n", "first")
    assert store.survey().names == ["one", "two"]
    store.mark_deleted("one", "gone")
    assert store.survey().live == {"two"}


def test_the_state_before_a_change_of_another_dashboard_is_nothing(store):
    # `previous_change` walks from the revision it is given, filtered on
    # the dashboard's own paths. Given a stranger's commit, the first
    # entry that walk yields is some earlier change of the dashboard -
    # which is not the predecessor of anything, and must not be reported.
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("home", "a: 2\n", "home second")
    other = store.write_snapshot("other", "b: 1\n", "other first")
    assert store.previous_change("home", other) is None


def test_the_survey_finds_metadata_a_deletion_left_in_the_tree(store):
    # `mark_deleted` removes meta/<key>.yaml only when it is at HEAD; a
    # meta recorded later than the deletion, or one a deletion missed,
    # is still in the tree and is still that dashboard's last name.
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.mark_deleted("gone", "gone deleted")
    store.write_snapshot("other", "c: 1\n", "other first")
    # Put a meta file for `gone` into the tree by hand, without the dashboard.
    from dulwich import porcelain

    meta = store.path / "meta" / "gone.yaml"
    meta.parent.mkdir(exist_ok=True)
    meta.write_text("title: Left behind\n", encoding="utf-8")
    porcelain.add(str(store.path), [str(meta)])
    porcelain.commit(str(store.path), message=b"stray meta", author=b"x <x@x>", committer=b"x <x@x>")
    assert store.survey().last_meta["gone"] == "title: Left behind\n"


def test_the_survey_of_an_empty_repository_is_empty(tmp_path):
    fresh = HistoryStore(tmp_path / "never")
    assert fresh.survey().names == []
    assert fresh.survey().last_meta == {}


# -- forgetting reaches the index and the working tree ---------------------


def test_forgetting_clears_the_index_and_the_working_tree_too(store):
    """Found on 2026-09-04 on the test bench: `forget` rewrote the commits
    and pruned the blobs, but left the dashboard's two files in the index
    and on disk. The next commit of *any* dashboard built its tree from
    that index and so referenced blobs that no longer existed - a history
    every read of that path fell over on, and a dashboard back from the
    dead in HEAD. It happens whenever `forget` runs before the recorder
    has marked the deletion, which the operations layer does not wait
    for.
    """
    store.write_snapshot("keep", "k: 1\n", "keep", meta="title: K\n")
    store.write_snapshot("gone", "g: 1\n", "gone", meta="title: G\n")
    assert store.forget("gone") == 1
    store.write_snapshot("keep", "k: 2\n", "keep again", meta="title: K\n")
    assert store.list_dashboards() == ["keep"]
    assert not (store.path / "gone.yaml").exists()
    assert not (store.path / "meta" / "gone.yaml").exists()
    assert store.survey().names == ["keep"]


def test_history_can_start_at_an_older_revision(store):
    """Paging means: carry on from here, not from position n."""
    revisions = [
        store.write_snapshot("home", f"a: {i}\n", f"home: change {i}")
        for i in range(6)
    ]
    # revisions[0] is the oldest. Carry on from the fourth-oldest:
    older = store.list_changes("home", limit=2, before=revisions[3])
    assert [c.revision for c in older] == [revisions[2], revisions[1]]


def test_the_cursor_itself_is_not_repeated(store):
    """Otherwise every page would open with the end of the one before."""
    revisions = [
        store.write_snapshot("home", f"a: {i}\n", f"home: change {i}")
        for i in range(4)
    ]
    older = store.list_changes("home", limit=10, before=revisions[2])
    assert revisions[2] not in [c.revision for c in older]


def test_a_cursor_that_is_not_a_change_of_this_dashboard_drops_nothing(store):
    """The walker yields the cursor only if it touches this dashboard.

    If it does not - another dashboard's commit, HEAD - the first entry
    is already a real change, and dropping it blindly would lose one.
    Same guard as `previous_change`.
    """
    revisions = [
        store.write_snapshot("home", f"a: {i}\n", f"home: change {i}")
        for i in range(3)
    ]
    other = store.write_snapshot("other", "b: 1\n", "other: change")
    assert [c.revision for c in store.list_changes("home", before=other)] == list(
        reversed(revisions)
    )
    # And the limit still means what it says.
    assert len(store.list_changes("home", limit=2, before=other)) == 2


def test_an_unknown_cursor_yields_nothing(store):
    """Asking is free - a revision that does not exist is not an error."""
    store.write_snapshot("home", "a: 1\n", "home: first")
    assert store.list_changes("home", before="f" * 40) == []


def test_history_without_a_cursor_is_unchanged(store):
    """The regression that counts: the existing call stays as it was."""
    store.write_snapshot("home", "a: 1\n", "home: first")
    store.write_snapshot("home", "a: 2\n", "home: second")
    assert [c.message for c in store.list_changes("home")] == [
        "home: second",
        "home: first",
    ]


# -- what came before this, said by the row itself -------------------------


def test_a_change_knows_the_state_before_it(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    newest, older = store.list_changes("home")
    assert newest.revision == second and newest.previous == first
    assert older.revision == first


def test_the_oldest_change_has_no_state_before_it(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    assert store.list_changes("home")[-1].previous is None


def test_the_last_row_of_a_page_knows_its_predecessor_too(store):
    # The whole reason this is a field. Worked out from the neighbour in
    # the list, the bottom row of every page answers "there is nothing
    # before this" - and the panel then offers no deleted cards to put
    # back, on a row that has a perfectly good predecessor one commit
    # further down.
    made = [store.write_snapshot("home", f"a: {i}\n", f"change {i}") for i in range(6)]
    page = store.list_changes("home", 3)
    assert [c.revision for c in page] == [made[5], made[4], made[3]]
    assert page[-1].previous == made[2]


def test_the_state_before_is_this_dashboards_own(store):
    # Never the commit's parent: another dashboard's commit sits in
    # between all the time, and its state is no state of this one.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("solar", "b: 1\n", "stranger")
    second = store.write_snapshot("home", "a: 2\n", "second")
    assert store.list_changes("home")[0].previous == first
    assert store.previous_change("home", second) == first


# -- searching the whole history -------------------------------------------


def test_a_search_finds_a_change_by_its_message(store):
    store.write_snapshot("home", "a: 1\n", "home: 1 card added")
    store.write_snapshot("home", "a: 2\n", "home: 2 views removed")
    assert [c.message for c in store.search_changes("home", "views")] == [
        "home: 2 views removed"
    ]


def test_a_search_finds_a_change_by_what_a_person_wrote(store):
    first = store.write_snapshot("home", "a: 1\n", "home: 1 card added")
    store.write_snapshot("home", "a: 2\n", "home: 1 card added")
    store.set_description(first, "The heating page rework")
    assert [c.revision for c in store.search_changes("home", "heating")] == [first]


def test_a_search_finds_a_state_by_the_title_of_a_version_on_it(store):
    store.write_snapshot("home", "a: 1\n", "home: 1 card added")
    marked = store.write_snapshot("home", "a: 2\n", "home: 2 moved")
    store.create_version("home/v1.0.0", "Before the winter rebuild", "", marked)
    assert [c.revision for c in store.search_changes("home", "winter")] == [marked]


def test_a_search_finds_a_state_by_the_description_of_a_version_on_it(store):
    marked = store.write_snapshot("home", "a: 1\n", "home: 1 card added")
    store.create_version("home/v1.0.0", "A title", "the notes I left", marked)
    assert [c.revision for c in store.search_changes("home", "notes")] == [marked]


def test_a_search_finds_a_state_by_the_number_of_a_version_on_it(store):
    marked = store.write_snapshot("home", "a: 1\n", "home: 1 card added")
    store.create_version("home/v1.2.0", "A title", "", marked)
    assert [c.revision for c in store.search_changes("home", "v1.2")] == [marked]


def test_a_search_does_not_match_the_marker_of_an_automatic_version(store):
    # The marker is bookkeeping stored in the description, and it is
    # made of words: `dashboard-history: automatic`. Searched raw, every
    # one of those words returns every automatic version - hits for a
    # sentence nobody wrote and nobody is ever shown. Everywhere else the
    # marker is read out before the description leaves; the search was
    # the one exit that had not been given the same treatment.
    marked = store.write_snapshot("home", "a: 1\n", "home: 1 card added")
    store.create_version(
        "home/v1.0.0", "A title", versions.automatic_description(), marked
    )
    for word in ("automatic", "dashboard", "history", "dash", "auto"):
        assert store.search_changes("home", word) == [], word
    # And a person's own words on an automatic version are still found.
    store.create_version(
        "home/v1.0.1",
        "Another",
        versions.automatic_description("the winter rebuild"),
        marked,
    )
    assert [c.revision for c in store.search_changes("home", "winter")] == [marked]


def test_a_search_does_not_match_the_namespace_of_a_version(store):
    # `home/v1.0.0` is searched as `v1.0.0`. The namespace is the
    # dashboard's own key, which is also the word a person uses for the
    # dashboard - so searching it would make every version of it a hit
    # for a word that says nothing.
    marked = store.write_snapshot("home", "a: 1\n", "home: 1 card added")
    store.create_version("home/v1.0.0", "A title", "", marked)
    assert store.search_changes("home", "home/") == []


def test_a_search_does_not_care_about_capitals(store):
    store.write_snapshot("home", "a: 1\n", "home: 1 Card added")
    assert len(store.search_changes("home", "cARD")) == 1


def test_a_search_stays_inside_one_dashboard(store):
    store.write_snapshot("home", "a: 1\n", "home: rework")
    store.write_snapshot("solar", "b: 1\n", "solar: rework")
    assert [c.message for c in store.search_changes("home", "rework")] == [
        "home: rework"
    ]


def test_a_search_reaches_past_the_window_the_panel_loads(store):
    # The whole reason this exists. The panel holds twenty-five entries;
    # the answer to "is that word anywhere" must not be decided by that.
    for index in range(40):
        store.write_snapshot("home", f"a: {index}\n", f"home: change {index}")
    store.write_snapshot("home", "a: last\n", "home: the needle")
    for index in range(40, 70):
        store.write_snapshot("home", f"a: {index}\n", f"home: change {index}")
    assert [c.message for c in store.search_changes("home", "needle")] == [
        "home: the needle"
    ]


def test_a_hit_carries_the_state_before_it(store):
    # Hits are not neighbours in the list they are drawn into, so the row
    # cannot work this out afterwards. It comes out of the same walk.
    first = store.write_snapshot("home", "a: 1\n", "home: first")
    found = store.write_snapshot("home", "a: 2\n", "home: the needle")
    for index in range(5):
        store.write_snapshot("home", f"a: {index + 3}\n", f"home: change {index}")
    hit = store.search_changes("home", "needle")[0]
    assert hit.revision == found and hit.previous == first


def test_a_search_answers_newest_first_and_stops_at_the_limit(store):
    for index in range(5):
        store.write_snapshot("home", f"a: {index}\n", f"home: match {index}")
    found = store.search_changes("home", "match", limit=2)
    assert [c.message for c in found] == ["home: match 4", "home: match 3"]


def test_a_search_stops_reading_when_it_has_enough(store, monkeypatch):
    # The limit has to bound the work, not only the answer. Built as a
    # list first, the search materialised a `Change` for every commit
    # this dashboard ever touched - and, on a shared repository, walked
    # past every other dashboard's as well - before a single comparison
    # was made. The `break` then stopped the reading of something that
    # was already in memory.
    #
    # Counted where the objects are made: two hits, two `Change`
    # objects. The generator hands one out only once it has seen the
    # entry behind it - that entry is its `previous` - so the walk reads
    # three commits of the thirty and the third is never built.
    for index in range(30):
        store.write_snapshot("home", f"a: {index}\n", f"home: match {index}")
    built = []
    real = store_module._change

    def counting(entry, notes, previous):
        built.append(entry)
        return real(entry, notes, previous)

    monkeypatch.setattr(store_module, "_change", counting)
    found = store.search_changes("home", "match", limit=2)
    assert [c.message for c in found] == ["home: match 29", "home: match 28"]
    assert len(built) == 2, len(built)


def test_a_search_searches_the_tag_list_it_is_handed(store):
    # `operations.async_search` reads this dashboard's versions to say
    # which of them sit on the rows it hands back, and this method reads
    # the same tags to search their titles. Two scans of one namespace
    # for one answer; handed the list, this one does not scan at all.
    marked = store.write_snapshot("home", "a: 1\n", "home: 1 card added")
    store.create_version("home/v1.0.0", "Before the winter rebuild", "", marked)
    # Handed an empty list, the tag that is really there is not read.
    assert store.search_changes("home", "winter", versions=[]) == []
    # And what is handed in is what is searched.
    invented = Version(
        name="home/v9.9.9",
        revision=marked,
        title="The spring plan",
        description="",
    )
    assert [
        c.revision
        for c in store.search_changes("home", "spring", versions=[invented])
    ] == [marked]
    # Left out, it reads them itself, which is what every other caller
    # relies on.
    assert [c.revision for c in store.search_changes("home", "winter")] == [marked]


def test_an_empty_search_finds_nothing_rather_than_everything(store):
    store.write_snapshot("home", "a: 1\n", "home: first")
    assert store.search_changes("home", "") == []
    assert store.search_changes("home", "   ") == []


# -- the cost of a read -------------------------------------------------
#
# Measured as objects read out of the repository, not as seconds. The
# thing being pinned down is how much work a read does, and a second is
# a poor way to say that: it moves with the machine, with the load, and
# on this project with whether dulwich found its C extensions. Counting
# reads says the same thing and says it the same way everywhere.


@contextmanager
def _counting_reads():
    """Count every object read out of any repository inside the block."""
    seen = {"objects": 0}
    original = DiskObjectStore.__getitem__

    def counted(self, sha):
        seen["objects"] += 1
        return original(self, sha)

    DiskObjectStore.__getitem__ = counted
    try:
        yield seen
    finally:
        DiskObjectStore.__getitem__ = original


def test_reading_one_dashboard_does_not_grow_with_the_others(tmp_path):
    """One dashboard's page costs its own history, not everybody's.

    Every dashboard shares one repository, so a walk filtered on one of
    them still steps over every commit the others made. The walk stops
    at `limit` entries - but a dashboard with fewer changes than that
    never reaches it, and those are precisely the ones that end up
    reading the whole history to hand back four rows.

    Two repositories, same two changes to `small`, different amounts of
    other people's history. What `small` costs must not tell them apart.
    """

    def reads_for(noise: int) -> int:
        history = HistoryStore(tmp_path / f"h{noise}")
        history.ensure()
        for i in range(noise):
            history.write_snapshot("noise", f"a: {i}\n", "noise")
        history.write_snapshot("small", "b: 1\n", "small first")
        history.write_snapshot("small", "b: 2\n", "small second")
        # The store may read the history once to get its bearings; what
        # is measured is what a read costs after that.
        history.list_changes("small")
        with _counting_reads() as seen:
            changes = history.list_changes("small")
        assert [c.message for c in changes] == ["small second", "small first"]
        return seen["objects"]

    quiet = reads_for(10)
    busy = reads_for(60)
    assert busy <= quiet + 10, (
        f"reading `small` cost {quiet} objects beside 10 other commits and "
        f"{busy} beside 60: the cost is the other dashboards', not its own"
    )


def test_a_new_change_costs_the_change_and_not_the_history(tmp_path):
    """A recording costs the recording, not the history behind it.

    The index is taken at one HEAD, and every save moves HEAD. Thrown
    away and built again each time it would be no cheaper than the walk
    it replaced - on an installation that records all day, never
    cheaper. What arrived since the last one is what has to be read.

    A ceiling rather than a comparison between two sizes, because what
    a read costs absolutely is not steady: dulwich packs loose objects
    as it goes, and the same repository answers in 22 reads or in 61
    depending on when that happened. What does not move is the order of
    magnitude. Measured on 2026-09-07 behind 240 other commits: 43 reads
    carrying the index forward against 970 rebuilding it, and the same
    at 60 commits was 51 against 250. The ceiling sits between the two
    with room for the packing to breathe.
    """
    history = HistoryStore(tmp_path / "h")
    history.ensure()
    for i in range(120):
        history.write_snapshot("noise", f"a: {i}\n", "noise")
    history.write_snapshot("small", "b: 1\n", "small first")
    history.list_changes("small")

    history.write_snapshot("small", "b: 2\n", "small second")
    with _counting_reads() as seen:
        changes = history.list_changes("small")

    assert [c.message for c in changes] == ["small second", "small first"]
    assert seen["objects"] < 150, (
        f"reading after one save cost {seen['objects']} objects behind 120 "
        "other commits: the index was thrown away and built again, so the "
        "save paid for the whole history"
    )


def test_forgetting_a_dashboard_leaves_no_stale_index_behind(store):
    """A rewrite moves every revision; the index must not survive it.

    `forget` is the one operation that rewrites history, and every
    commit from the first affected one onwards comes out with a new id.
    An index carried across that would hand back revisions that are no
    longer reachable - and `read_at` on one of those is the silent
    half-truth this project exists to prevent.
    """
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 2\n", "home second")
    # Build the index against the history as it stands now.
    assert [c.message for c in store.list_changes("home")] == [
        "home second",
        "home first",
    ]

    store.forget("gone")

    assert [c.message for c in store.list_changes("home")] == [
        "home second",
        "home first",
    ]
    assert store.list_changes("gone") == []
    # And every revision still handed out is one that is really there.
    for change in store.list_changes("home"):
        assert store.read_at("home", change.revision) is not None


def test_a_new_change_does_not_make_the_survey_walk_again(tmp_path):
    """The survey costs what arrived too, not the history behind it.

    `survey` is keyed by HEAD, so it is free until anything is recorded
    - and then it walks the whole history again, which is precisely the
    moment the panel asks for it. An installation that records all day
    never gets the cached one. The walk it needs is the walk the index
    already did.

    A ceiling for the same reason as the test above: the number moves
    with packing, its order of magnitude does not.
    """
    history = HistoryStore(tmp_path / "h")
    history.ensure()
    for i in range(120):
        history.write_snapshot("noise", f"a: {i}\n", "noise")
    history.survey()

    history.write_snapshot("small", "b: 1\n", "small first")
    with _counting_reads() as seen:
        found = history.survey()

    assert "small" in found.names
    assert "small" in found.live
    assert seen["objects"] < 150, (
        f"the survey cost {seen['objects']} objects after one save behind "
        "120 other commits: it walked the whole history again"
    )


def test_an_index_built_across_a_rewrite_is_not_kept(store, monkeypatch):
    """A read that was overtaken by a rewrite must not leave its index.

    `forget` drops the index and takes the write lock; reads take
    neither. So a read that started before the rewrite finishes after
    it, holding an index of a history that no longer exists - and puts
    it back, on top of the empty slot `forget` just cleared. Every read
    after that is served from it.

    The read that was overtaken cannot be saved; it answers from what it
    saw, and that is what any snapshot read means. What must not happen
    is that it becomes the answer for everybody else.

    This passed the first time it was run, which is worth saying plainly:
    the guard is already there, in `_extended_index`. `forget` leaves the
    old HEAD unreadable, so carrying the stale index forward raises
    `MissingCommitError` and the index is built again from what is
    actually in the repository. The test is here to keep that true - the
    guard reads like belt and braces until you see what it is holding
    up.
    """
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 2\n", "home second")

    overtaken = store._built_index
    # Once, and guarded: `forget` asks for the dashboard list, which
    # builds the index, which would call this again.
    already = []

    def build_and_be_overtaken(repo, head):
        found = overtaken(repo, head)
        if not already:
            already.append(True)
            store.forget("gone")
        return found

    monkeypatch.setattr(store, "_built_index", build_and_be_overtaken)
    try:
        list(store.list_changes("home"))
    except KeyError:  # pragma: no cover - the overtaken read may not finish
        pass
    monkeypatch.undo()

    # Everything handed out from here on has to be really there.
    changes = store.list_changes("home")
    assert [c.message for c in changes] == ["home second", "home first"]
    for change in changes:
        assert store.read_at("home", change.revision) is not None


def test_the_predecessor_does_not_grow_with_the_other_dashboards(tmp_path):
    """Finding the entry before this one costs this dashboard's history.

    The neighbour of a change is one step along a list the index already
    holds. Walked for instead, it is filtered on this dashboard's two
    paths and stops after two entries - which is fast only when those
    two are close together. A dashboard with little history of its own
    has them far apart, with everybody else's commits in between, and
    the walk steps over every one of them.

    Measured on the test bench on 2026-09-07, 45 dashboards over 4454
    commits: expanding the current state of `dh-probe` (77 entries of
    its own) waited 2637 ms on this, against 53 ms for a board of 673
    entries. Less history of your own, longer wait - which is
    exactly backwards.
    """

    def reads_for(noise: int) -> int:
        history = HistoryStore(tmp_path / f"p{noise}")
        history.ensure()
        history.write_snapshot("small", "b: 1\n", "small first")
        # In between the two, so the walk has to step over them.
        for i in range(noise):
            history.write_snapshot("noise", f"a: {i}\n", "noise")
        history.write_snapshot("small", "b: 2\n", "small second")
        newest = history.list_changes("small")[0].revision
        with _counting_reads() as seen:
            found = history.previous_change("small", newest)
        assert found is not None
        return seen["objects"]

    quiet = reads_for(10)
    busy = reads_for(60)
    assert busy <= quiet + 20, (
        f"the predecessor cost {quiet} objects with 10 commits in between "
        f"and {busy} with 60: it is the other dashboards being walked past"
    )


def test_forgetting_reports_its_progress(store):
    """`forget` says where it is, so a caller can show more than a spinner.

    Measured on the test bench (7407 commits, 782 versions): the whole
    operation takes 24 s, and 58 % of it sits in rewriting the version
    marks alone. Without a word from here the panel can only draw a
    spinner, and somebody who waits a minute at a spinner presses reload
    - which is what this exists to prevent.

    The callback is a plain callable on purpose: this module stays free
    of Home Assistant, so what it reports is a phase name and two
    numbers. Turning that into an event is the caller's job.
    """
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 2\n", "home second")
    store.create_version("home", "v1.0.0", "a version the rewrite carries")

    seen: list[tuple[str, int, int]] = []
    store.forget("gone", progress=lambda *step: seen.append(step))

    phases = [phase for phase, _done, _total in seen]
    # Each phase is announced before it starts, so a slow one is named
    # while it runs rather than after it finished.
    assert "rewriting" in phases
    # `versions` is deliberately not among them: since the marks are
    # written in one go it lasts 0.3 s, and a phase nobody can read is
    # not worth announcing. See `_rewrite_tags`.
    assert "versions" not in phases
    assert "cleaning" in phases
    assert phases.index("rewriting") < phases.index("cleaning")
    # The counts have to be usable as "x of y" without the caller
    # guessing: never past the total, and the total never zero when
    # there is something to count.
    for phase, done, total in seen:
        assert 0 <= done <= total, f"{phase}: {done} of {total}"


def test_forgetting_without_a_progress_callback_still_works(store):
    """The parameter is optional, and every existing caller passes none."""
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    assert store.forget("gone") > 0
    assert "gone" not in store.list_all_dashboards()


def test_forgetting_does_not_write_packed_refs_once_per_version(
    store, monkeypatch
):
    """One write for all the marks, not one per mark.

    The cost this guards is the largest single part of a `forget`:
    measured on the test bench on 2026-09-18, 782 marks took 12.46 s,
    58 % of the whole operation, because removing a ref rewrites the
    whole `packed-refs` file and renames it into place - 11.1 ms each.

    Counted rather than looked at afterwards. The state at the end
    proves nothing: `garbage_collect` finishes with `pack_refs()`, so
    every `forget` leaves the refs packed whichever way they got there.

    Packed on purpose before the count starts: against loose refs the
    removal never touches `packed-refs` and the number would be zero
    either way.
    """
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    for n in range(20):
        store.write_snapshot("home", f"a: {n + 2}\n", f"home {n}")
        store.create_version(f"home/v1.0.{n}", f"Mark {n}", "kept over the rewrite")
    store.create_version("gone/v1.0.0", "Goes away", "with its dashboard")
    store._repo().refs.pack_refs()

    writes = []
    real = dulwich.refs.GitFile

    def spy(path, mode="rb", *args, **kwargs):
        name = path if isinstance(path, bytes) else str(path).encode()
        if name.endswith(b"packed-refs") and "w" in mode:
            writes.append(name)
        return real(path, mode, *args, **kwargs)

    monkeypatch.setattr(dulwich.refs, "GitFile", spy)
    store.forget("gone")

    # Measured: 22 writes for 21 marks before the change, 2 after - the
    # batch itself and the collection's own `pack_refs`. Five leaves
    # room for a dulwich that writes once more somewhere without
    # letting a per-mark write back in.
    assert len(writes) <= 5, f"{len(writes)} writes for 21 marks"
    # And the marks that survive are still readable, under their full
    # names: `Version.name` carries the dashboard's key.
    kept = {v.name for v in store.list_versions("home")}
    assert kept == {f"home/v1.0.{n}" for n in range(20)}


def _stage_without_committing(store: HistoryStore, key: str, text: str) -> None:
    """Model a `write_snapshot` that reached `porcelain.add` but never
    committed - a transient `FileLocked` between the two, say. Leaves a
    real blob the index names but no ref reaches, exactly as issue #25
    reproduced it by hand against real dulwich.
    """
    target = store.path / f"{key}.yaml"
    target.write_text(text, encoding="utf-8")
    porcelain.add(str(store.path), [str(target)])


def test_forget_does_not_prune_an_unrelated_staged_but_uncommitted_blob(store):
    """Issue #25: `_finish_forget`'s GC must not destroy a staged save.

    `_finish_forget` runs `garbage_collect(..., grace_period=0)`
    unconditionally on every successful `forget`. dulwich's reachability
    walk works from refs only, never the index - a dashboard whose
    `write_snapshot` staged new content but never got to commit it has a
    blob the index still names but no ref reaches. `forget`ting a wholly
    unrelated dashboard must not sweep it away: `porcelain.commit`
    builds its tree from the *whole* index, so the next ordinary commit
    by any key absorbs that still-staged entry - and would silently
    reference a pruned blob if this one destroyed it first.
    """
    store.write_snapshot("a", "a: 1\n", "first")
    store.write_snapshot("c", "c: 1\n", "first")
    _stage_without_committing(store, "b", "b: 1\n")

    store.forget("a")

    new_head = store.write_snapshot("c", "c: 2\n", "second")
    assert new_head is not None
    assert store.read_at("b", new_head) == "b: 1\n"


def test_forget_does_not_prune_a_staged_blob_that_is_already_packed(store):
    """Same as above, once the staged blob has already been packed.

    `_finish_forget`'s GC repacks the whole object store, excluding
    whatever it judged unreachable - loose or not. A fix that only
    guards the loose-object deletion loop and not that `exclude` set
    would still lose this one on the very next repack.
    """
    store.write_snapshot("a", "a: 1\n", "first")
    store.write_snapshot("c", "c: 1\n", "first")
    _stage_without_committing(store, "b", "b: 1\n")
    store._repo().object_store.pack_loose_objects()

    store.forget("a")

    new_head = store.write_snapshot("c", "c: 2\n", "second")
    assert new_head is not None
    assert store.read_at("b", new_head) == "b: 1\n"


def test_forget_still_prunes_its_own_content_despite_the_new_protection(store):
    """The fix for issue #25 must not shield what `forget` itself just
    removed. `_drop_from_index` already takes the forgotten key's own
    two paths out of the index before the protecting GC step ever looks
    at it, so its blob stays exactly as unprotected as it always was.
    """
    store.write_snapshot("keep", "k: 1\n", "keep", meta="title: K\n")
    store.write_snapshot("gone", "g: 1\n", "gone", meta="title: G\n")

    assert store.forget("gone") == 1

    assert not (store.path / "gone.yaml").exists()
    assert not (store.path / "meta" / "gone.yaml").exists()
    assert store.list_dashboards() == ["keep"]
    gone_blob = Blob.from_string(b"g: 1\n").id
    assert gone_blob not in store._repo().object_store


def test_repair_pending_forget_also_protects_a_staged_but_uncommitted_blob(
    store, monkeypatch
):
    """The crash-recovery path must give the same protection as an
    uninterrupted `forget` - it replays the very same `_finish_forget`
    (decision 21), including the new, index-protecting GC step.
    """
    store.write_snapshot("a", "a: 1\n", "first")
    store.write_snapshot("c", "c: 1\n", "first")
    _stage_without_committing(store, "b", "b: 1\n")

    real_rewrite_tags = HistoryStore._rewrite_tags
    calls = []

    def flaky_rewrite_tags(repo, changed):
        calls.append(changed)
        if len(calls) == 1:
            raise RuntimeError("simulated crash before _rewrite_tags")
        return real_rewrite_tags(repo, changed)

    monkeypatch.setattr(HistoryStore, "_rewrite_tags", staticmethod(flaky_rewrite_tags))

    with pytest.raises(RuntimeError):
        store.forget("a")

    monkeypatch.setattr(HistoryStore, "_rewrite_tags", staticmethod(real_rewrite_tags))
    store.repair_pending_forget()

    new_head = store.write_snapshot("c", "c: 2\n", "second")
    assert new_head is not None
    assert store.read_at("b", new_head) == "b: 1\n"

