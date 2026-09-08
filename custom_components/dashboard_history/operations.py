"""Every operation the integration offers, in one place.

The services and the panel are both thin skins over this module. The panel
is the layer most likely to break, and letting it grow logic of its own
would put the important part exactly there. So it gets none.

Nothing here writes without an explicit `confirm`; without it each
restoring operation answers with a preview and changes nothing.
"""

from __future__ import annotations

import asyncio
import difflib
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .analyze import (
    explain_change,
    explain_effect,
    find_removed,
    message_adds,
    plan_undo,
)
from . import versions as versioning
from .const import DOMAIN
from .keys import is_absent, is_live
from .restore import apply_undo, reinsert
from .snapshot import (
    async_create_dashboard,
    async_get_all_meta,
    async_get_config,
    async_known_keys,
    async_save_config,
)
from .store import HistoryStore, Version
from .yaml_io import dump, load_state

_LOGGER = logging.getLogger(__name__)


def _preview(old: dict, new: dict, name: str) -> tuple[str, dict, str]:
    """The diff, the plain words for it, and the text of `old`.

    All real work - two YAML dumps and a difflib pass, then a second
    card-matching run - and all of it belongs off the event loop, so it
    is paired here to cost one executor hop. The dump of `old` is handed
    back because `_keep_the_live_state` needs exactly that text, and
    dumping twelve hundred cards a second time is not free.
    """
    old_text, new_text = dump(old), dump(new)
    diff = "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"live/{name}",
            tofile=f"restored/{name}",
        )
    )
    return diff, _as_dict(explain_effect(old, new)), old_text


# Every operation below that reads a state, matches cards or renders a
# diff does so through one of these, in an executor. Found on 2026-09-03:
# only `async_undo_change` kept that work off the event loop; the other
# three parsed YAML and matched cards on it, and `async_history` dumped
# the live dashboard there. Measured at 78 ms per matching pass on twelve
# hundred cards, that is a stalled Home Assistant on every row expanded.


def _removed_since(text: str, current: dict) -> list:
    """What `text` held that `current` no longer does."""
    return find_removed(load_state(text), current)


def _reinsertion(text: str, current: dict, position: int, key: str) -> dict:
    """Everything `restore_deleted` works out, in one hop.

    Answers with an `error` key when there is nothing to put back or the
    place it belonged to is gone, and otherwise with the item, the
    restored configuration and its preview. One shape for both so the
    caller reads it once.
    """
    items = _removed_since(text, current)
    if not items:
        return {"error": "nothing is missing since that revision"}
    if not 0 <= position < len(items):
        return {"error": f"position {position} out of range (0..{len(items) - 1})"}
    try:
        restored = reinsert(current, items[position])
    except LookupError as err:
        # The place it belonged to is gone. Every other failure here
        # answers with a message rather than an exception; so does this.
        return {"error": str(err)}
    diff, explanation, live_text = _preview(current, restored, key)
    return {
        "item": items[position],
        "restored": restored,
        "diff": diff,
        "explanation": explanation,
        "live_text": live_text,
    }


def _target_and_preview(text: str, current: dict, key: str) -> tuple:
    """The recorded state as a configuration, and the preview of going there."""
    target = load_state(text)
    return (target, *_preview(current, target, key))


def _plan_undo(before_text: str, text: str, current: dict):
    """The undo plan for the change from `before_text` to `text`.

    Answers with the parsed `before` as well: the caller compares the
    undone state against it, and parsing the same text twice for that
    was the one piece of double work left on this path.
    """
    before = load_state(before_text)
    return plan_undo(before, load_state(text), current), before


def _same_as_live(store: HistoryStore, key: str, revisions: list, live: dict) -> set:
    """Which of these revisions hold exactly the live configuration."""
    return store.matching_revisions(key, revisions, dump(live))


def _version_dict(version: Version) -> dict:
    """One version as plain data, with its marker read rather than shown.

    Every version that leaves as a *payload* goes through here, so the
    panel sees one shape - and so `automatic` cannot be present in one
    answer and missing from the next, which is the kind of difference a
    frontend quietly renders as False.

    Not quite every reader: `store.search` calls `read_description`
    straight, because it wants the words a person wrote and nothing
    else. That is the one exception, and it is named here because the
    stronger claim used to stand in its place - and under it `search`
    matched the marker itself for a while, so a search for `automatic`
    found every automatically marked change. Anything that hands a
    version to a caller belongs here; anything that only needs the
    words may read them itself.
    """
    description, automatic = versioning.read_description(version.description)
    return {
        "name": version.name,
        "revision": version.revision,
        "title": version.title,
        "description": description,
        "automatic": automatic,
        # Zero where the store has no time to give - a tag made by hand
        # on a repository somebody opened themselves. The panel leaves
        # the place empty then; the reason it is a number and not a
        # missing key is the paragraph above.
        "timestamp": version.timestamp,
        # Whether there are words here to rewrite at all. A lightweight
        # tag is the ref itself and carries no message, so renaming it
        # is refused - and the panel needs to know that before it offers
        # the button, not after. It used to infer it from an empty
        # title, which is a field a person is now allowed to rewrite:
        # a hand-made *annotated* tag with an empty first line read as
        # unrenameable, and the FAQ promises any version can be renamed.
        "annotated": version.annotated,
    }


def _marks_by_revision(versions: list) -> dict[str, list[dict]]:
    """Which versions sit on which state.

    Gathered here rather than in the panel: the panel would need a
    second call and a join, and a join is logic. Two versions on one
    commit is allowed, so this is a list.

    What a version does *not* carry here is how many changes it spans,
    and that is a decision rather than an omission. The simple mode
    would like to say "eleven changes in this version" instead of
    counting the window it happens to have loaded, and working that out
    at read time means walking the dashboard's whole history: measured
    on 2026-09-05 on a throwaway repository of 1002 commits over five
    dashboards, a `history` click costs 120 ms and one full walk of the
    201 that belong to this dashboard costs 468 ms - and the naive form,
    one walk per version, 5.0 s. The gap is other dashboards' commits,
    which dulwich filters out by path but still walks past, so it grows
    with the whole repository while `history` stays flat. If the count
    is ever wanted, it belongs written into the tag body at the moment
    the version is made (`async_create_version`), where it is one number
    against a walk that is happening anyway - not counted again on every
    click for the rest of the repository's life.
    """
    marks: dict[str, list[dict]] = {}
    for version in versions:
        marks.setdefault(version.revision, []).append(_version_dict(version))
    return marks


def _rendered(changes: list, marks: dict, same: set) -> list[dict]:
    """Recorded changes as the rows a panel draws.

    One shape for `history` and for `search`. They differ in which
    changes they hand back and in nothing else, and a row that carried
    different fields depending on how it was found would be a difference
    the panel has to know about - which is logic in the panel.
    """
    return [
        {
            "revision": c.revision,
            "timestamp": c.timestamp,
            "message": c.message,
            "description": c.description,
            # What this row can be compared against and undone towards.
            # Said rather than left to be worked out from the row below:
            # in a page the row below may not exist, and in a search
            # result it is not the predecessor at all.
            "previous": c.previous,
            # Whether this change also *added* something, worked out
            # from the wording by the module that writes the wording.
            # The panel needs it to know that offering a plain put-back
            # would be a trap - put one removed card back and the added
            # one stays - and it used to run a regular expression over
            # the message to find out. The design record forbids exactly
            # that (a panel that reads generated text is a panel with
            # logic in it), and it was wrong besides: a dashboard
            # renamed to `3 added` read as a trap.
            "adds": message_adds(c.message),
            "same_as_now": c.revision in same,
            "versions": marks.get(c.revision, []),
        }
        for c in changes
    ]


async def _keep_the_live_state(
    hass: HomeAssistant, store: HistoryStore, key: str, current: str | None
) -> str | None:
    """Record what is on the dashboard now, before it is overwritten.

    Answers with a note if the state could not be kept, and with None if
    it is safely in the history - it never refuses. The case that
    settles that is a full disk, where reading works and writing does
    not: refusing there would leave somebody unable to restore anything
    at the moment they want it most, in the name of a snapshot that
    could not have been written either way.

    Ordinarily there is nothing to do here. The recorder hears every
    save, and three hours of ordinary use on the test rig produced no
    gap at all - in which case the state is already the newest entry and
    this writes nothing. It exists for the times "ordinarily" does not
    hold: a save made while Home Assistant was starting, a storage file
    edited from outside, a recorder that failed once. Without it the
    state being replaced is gone, with nothing in the history to go back
    to - and going back is the whole point of the tool.

    Announced to nobody, deliberately. The panel reads
    EVENT_HISTORY_UPDATED as "your page is stale, read it again", and
    firing it here would send it to reload in the middle of the
    operation: a page built from a history whose newest entry is the
    state about to be replaced. That page looks right, which is worse
    than looking wrong.

    The result is *checked*, not assumed. `async_capture` swallows its
    own failures by design - nothing in it may raise into Home Assistant
    - so asking it whether it worked answers nothing. Asking the store
    whether the live state is now its newest entry answers exactly the
    question that matters, and stays right no matter how the recording
    failed.
    """
    if current is None:
        # No live configuration at all - the dashboard was never saved -
        # so there is nothing to keep and nothing the recorder could have
        # missed. Saying otherwise here would put a warning on the one
        # case that is already understood. `None`, not "empty": a saved
        # `{}` is a state like any other, and Home Assistant does store
        # one. Found by a second review on 2026-09-04.
        return None
    capture = hass.data.get(DOMAIN, {}).get("capture")
    if capture is not None:
        try:
            await capture.async_capture(
                key=key, reason="before restoring", announce=False
            )
        except Exception:  # noqa: BLE001 - a note, never a refusal
            _LOGGER.exception("Could not record %s before restoring it", key)
    try:
        # `current` is the live state as text, dumped once by `_preview`.
        if await hass.async_add_executor_job(store.read_at, key, "HEAD") == current:
            return None
    except Exception:  # noqa: BLE001 - the check itself must not refuse either
        # A repository that cannot be read is the same disappointment as
        # one that cannot be written, and the answer is the same: the
        # restore goes ahead, and the note says what is missing.
        _LOGGER.exception("Could not check whether %s was recorded", key)
    _LOGGER.warning(
        "The state of %s at the time of the restore is not in the history", key
    )
    return (
        "what was on the dashboard just before this could not be recorded, "
        "so the history does not hold it"
    )


def _as_dict(explanation) -> dict:
    """An Explanation as plain data, for a service result or the panel."""
    return {
        "groups": [
            {
                "view": group.view,
                "entries": [
                    {
                        "kind": entry.kind,
                        "what": entry.what,
                        "label": entry.label,
                        "text": entry.text,
                    }
                    for entry in group.entries
                ],
                "more": group.more,
            }
            for group in explanation.groups
        ],
        "note": explanation.note,
    }


async def _state_at(
    hass: HomeAssistant, store: HistoryStore, key: str, revision: str
) -> tuple[str | None, str | None, str | None]:
    """The dashboard text at a revision, or a message saying why not.

    The two failures are told apart on purpose. "Unknown revision" is a
    statement about the input; "did not exist" is a statement about the
    dashboard's history. Reporting the second when the first is true sends
    people looking for a fault in their dashboard instead of in what they
    typed - and an abbreviated hash, which is what `git log --oneline`
    prints, used to land exactly there.
    """
    full = await hass.async_add_executor_job(store.resolve, revision)
    if full is None:
        return None, None, f"unknown revision: {revision}"
    text = await hass.async_add_executor_job(store.read_at, key, full)
    if text is None:
        return full, None, f"{key} did not exist at {full[:10]}"
    return full, text, None


async def async_dashboards(hass: HomeAssistant, store: HistoryStore) -> dict:
    """Every dashboard the panel can offer, live ones and deleted ones.

    A deleted dashboard is listed too, and marked as such. That is not a
    courtesy: it is the one somebody opens this tool to find.
    """
    # One executor hop for the store's whole answer: every name, which
    # are live, and what each was last called. See `HistoryStore.survey`.
    found = await hass.async_add_executor_job(store.survey)
    known = await async_known_keys(hass)
    meta = await async_get_all_meta(hass)

    dashboards = []
    for key in found.names:
        exists = is_live(key, found.live, known)
        info = meta.get(key)
        if info is None:
            # Gone, or live without a registry entry (the default
            # dashboard): Home Assistant can say nothing about it, and
            # its own last recorded name beats the bare key.
            info = load_state(found.last_meta.get(key))
        dashboards.append(
            {
                "key": key,
                "title": info.get("title") or key,
                "icon": info.get("icon"),
                "exists": exists,
            }
        )
    return {"dashboards": dashboards}


async def async_history(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    limit: int = 50,
    before: str | None = None,
) -> dict:
    """The recorded states of one dashboard, newest first.

    Each entry says whether it holds exactly what the dashboard holds now
    (`same_as_now`). That is worked out rather than assumed, and the
    difference matters: normally the newest entry *is* the current state,
    but after a change made at Home Assistant's back - a restored backup, a
    hand-edited storage file - it is not, and will not be until the next
    start. A panel that simply crowned the top entry would be wrong exactly
    when being right matters.

    It also answers the question a repetitive history raises. Moving a card
    up and down leaves several entries with byte-identical content and, since
    the messages are generated, identical wording: seven reading "2 moved",
    every second one the state in front of you.

    Each entry also names the versions that sit on it, if any. The panel
    builds its sections from that, so it never has to join two calls
    together - a join in the panel is logic in the panel.

    It also says what day it is here, spelled the way an automatic
    version spells it. The dialog in front of a restore offers to keep
    the state being replaced and fills the title in with today's date;
    computed in the browser that is the *browser's* today, and near
    midnight from a laptop in another time zone it is a different day
    from the one this installation would have written. Two names for one
    day in a list that shows nothing but names is precisely the
    confusion the simple mode cannot survive.

    Carried here rather than anywhere else because the panel already has
    this answer in its hand at the moment it needs the string: the
    restore dialog is opened from a history row. `next_versions` is the
    other candidate and would be fresher still, but the keep block of
    the restore dialog does not call it - it needs no numbering, only a
    title. And `history` is re-read whenever the dashboard changes or is
    switched, so the string cannot age past a panel nobody is touching.
    """
    # One more than asked for: its presence answers "is there anything
    # older?", and it costs one commit rather than a second query.
    changes, versions = await asyncio.gather(
        hass.async_add_executor_job(store.list_changes, key, limit + 1, before),
        hass.async_add_executor_job(store.list_versions, key),
    )
    more = len(changes) > limit
    changes = changes[:limit]
    marks = _marks_by_revision(versions)
    live = await async_get_config(hass, key)
    same: set[str] = set()
    if live is not None:
        # Changes *and* versions in one pass: the comparison is by blob
        # id, and a second call would open the same repository again.
        # The versions join in because the badge would otherwise depend
        # on how far somebody has paged - the finding this project is for.
        wanted = [c.revision for c in changes] + [v.revision for v in versions]
        if wanted:
            same = await hass.async_add_executor_job(
                _same_as_live, store, key, wanted, live
            )
    rendered = _rendered(changes, marks, same)
    matching_versions = [
        _version_dict(v)
        for v in versioning.by_number(key, versions)
        if v.revision in same
    ]
    return {
        "changes": rendered,
        # The cursor for the next page: the oldest change handed out.
        # None means there is nothing older - the panel then leaves the
        # button out rather than fetching an empty page.
        "next_cursor": rendered[-1]["revision"] if more and rendered else None,
        "matching_versions": matching_versions,
        # The installation's own today, not the browser's. Read at the
        # moment of answering and through the same function the
        # automatic versions use, so a title somebody accepts unchanged
        # is spelled exactly like the ones already in the list.
        "today": versioning.day_title(
            int(dt_util.utcnow().timestamp()), dt_util.DEFAULT_TIME_ZONE
        ),
    }


async def async_search(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    text: str,
    limit: int = 50,
) -> dict:
    """Recorded changes of one dashboard whose words hold `text`.

    Answers in the same shape as `history`, minus the cursor: a search
    result is not a page, and offering to page through one would invite
    a second search with a different answer. `more` says the limit was
    reached, so the panel can say "the first fifty" rather than "fifty".

    The longest read this integration has - the whole history - so it is
    a command of its own rather than a flag on `history`. That keeps the
    ordinary path, which the panel walks on every click, off it.

    One tag scan, not two, and that is why this does not gather the way
    `history` does. The search matches a version's title, its description
    and its number, so it wants exactly the list this wants to say which
    versions sit on the rows it hands back - and run side by side, the
    two read every tag of the dashboard twice for one answer. Read once
    here and handed down, the second scan is gone; what is left is one
    executor hop after another instead of two at once, and the walk was
    always the expensive half of the pair.
    """
    versions = await hass.async_add_executor_job(store.list_versions, key)
    changes = await hass.async_add_executor_job(
        store.search_changes, key, text, limit + 1, versions
    )
    more = len(changes) > limit
    changes = changes[:limit]
    marks = _marks_by_revision(versions)
    live = await async_get_config(hass, key)
    same: set[str] = set()
    if live is not None and changes:
        same = await hass.async_add_executor_job(
            _same_as_live, store, key, [c.revision for c in changes], live
        )
    return {"changes": _rendered(changes, marks, same), "more": more}


async def async_deleted_since(
    hass: HomeAssistant, store: HistoryStore, key: str, revision: str
) -> dict:
    """What was present at a revision and is gone now."""
    _, text, error = await _state_at(hass, store, key, revision)
    if error is not None:
        return {"items": [], "error": error}
    current = await async_get_config(hass, key) or {}
    items = await hass.async_add_executor_job(_removed_since, text, current)
    return {
        "items": [
            {
                "position": position,
                "kind": item.kind,
                "label": item.label,
                "view": item.view_path,
            }
            for position, item in enumerate(items)
        ]
    }


async def async_restore_deleted(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    revision: str,
    position: int,
    confirm: bool = False,
) -> dict:
    """Put one disappeared card or view back."""
    _, text, error = await _state_at(hass, store, key, revision)
    if error is not None:
        return {"applied": False, "error": error}
    live = await async_get_config(hass, key)
    plan = await hass.async_add_executor_job(_reinsertion, text, live or {}, position, key)
    if "error" in plan:
        return {"applied": False, "error": plan["error"]}
    diff, explanation = plan["diff"], plan["explanation"]
    if not confirm:
        return {"applied": False, "preview": diff, "explanation": explanation}
    lost = await _keep_the_live_state(
        hass, store, key, plan["live_text"] if live is not None else None
    )
    await async_save_config(hass, key, plan["restored"])
    result = {
        "applied": True,
        "preview": diff,
        "explanation": explanation,
        "restored": plan["item"].label,
    }
    if lost:
        result["note"] = lost
    return result


async def _async_keep_as_version(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    wanted: dict,
    gap: str | None,
) -> dict:
    """Mark the state that is about to be replaced, if it can be marked.

    Called after `_keep_the_live_state` and before the write, and that
    is the whole reason it exists here rather than in a caller: only
    between those two is the newest recorded state of this dashboard the
    one that is on the screen. A panel marking it beforehand would tag
    whatever was newest *then*, which after a save the recorder missed
    is the state before it - a tag that points somewhere else and looks
    perfectly right ever after.

    `gap` is what `_keep_the_live_state` reported. When it says
    something, the live state is not in the history at all, so there is
    nothing here that could be marked truthfully. Answered rather than
    raised: the restore itself goes ahead, for the same reason
    `_keep_the_live_state` never refuses either.
    """
    if gap is not None:
        return {"created": None, "error": gap}
    return await async_create_version(
        hass,
        store,
        key,
        level=wanted.get("level") or "patch",
        title=wanted.get("title") or "",
        description=wanted.get("description") or "",
    )


async def async_restore_state(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    revision: str,
    confirm: bool = False,
    keep_as_version: dict | None = None,
) -> dict:
    """Set a dashboard back to an earlier state, creating it if it is gone.

    `keep_as_version` marks the state being replaced, so that going back
    is not a one-way door. Why it is answered here and not by whoever
    asked for the restore is argued in `_async_keep_as_version`.
    """
    full, text, error = await _state_at(hass, store, key, revision)
    if error is not None:
        return {"applied": False, "error": error}
    # A dashboard that is gone entirely is restored, not refused. It is the
    # heaviest loss this tool can witness; refusing exactly there while
    # offering everything for a single card made no sense.
    known = await async_known_keys(hass)
    missing = is_absent(key, known)
    live = None if missing else await async_get_config(hass, key)
    target, diff, explanation, live_text = await hass.async_add_executor_job(
        _target_and_preview, text, live or {}, key
    )
    if not diff and not missing:
        return {"applied": False, "preview": "", "note": "already identical"}
    if not confirm:
        return {
            "applied": False,
            "preview": diff,
            "explanation": explanation,
            "creates_dashboard": missing,
        }

    created = False
    note: str | None = None
    if missing:
        meta_text = await hass.async_add_executor_job(store.read_meta_at, key, full)
        if meta_text is None:
            # Nothing recorded at that exact point; the last name it had is
            # still much better than falling back to the bare key. The same
            # answer the panel lists it under.
            found = await hass.async_add_executor_job(store.survey)
            meta_text = found.last_meta.get(key)
        meta = load_state(meta_text)
        try:
            note = await async_create_dashboard(hass, key, meta)
        except HomeAssistantError as err:
            # Recreating needs Home Assistant's own dashboard collection,
            # and it refuses rather than write something that only looks
            # like a dashboard. That is an answer, not a crash: the message
            # says what a person can do instead.
            return {"applied": False, "error": str(err)}
        created = True
    else:
        # Only when there is a live state to keep. A dashboard that is
        # gone has none, and asking for one would record its absence a
        # second time.
        note = await _keep_the_live_state(
            hass, store, key, live_text if live is not None else None
        )
    kept = None
    if keep_as_version is not None:
        kept = await _async_keep_as_version(
            hass,
            store,
            key,
            keep_as_version,
            # A dashboard that is gone has no live state at all, so there
            # is nothing to keep and nothing to mark. Said in the answer
            # rather than silently skipped: somebody asked for a version.
            "the dashboard was gone, so there was no state to mark"
            if missing
            else note,
        )
    await async_save_config(hass, key, target)
    result = {
        "applied": True,
        "preview": diff,
        "explanation": explanation,
        "created": created,
    }
    if note:
        result["note"] = note
    if kept is not None:
        result["kept_as_version"] = kept
    return result


async def async_undo_change(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    revision: str,
    confirm: bool = False,
) -> dict:
    """Take one change back and keep everything since - if that is exact.

    The difference to `restore_state` is reach, not degree: this writes
    only the cards the change touched, that one replaces the dashboard.
    It is offered only where the plan can prove itself, and the proof is
    remade here on every call - including the confirming one. Somebody
    can save between seeing the preview and pressing the button, and
    writing a preview computed before that would throw their work away
    with a proof that was true a minute ago.
    """
    full, text, error = await _state_at(hass, store, key, revision)
    if error is not None:
        return {"available": False, "reason": error}

    before = await hass.async_add_executor_job(store.previous_change, key, full)
    if before is None:
        return {
            "available": False,
            "reason": "this is the first recorded state, so there is nothing "
            "before it to go back to",
        }
    _, before_text, error = await _state_at(hass, store, key, before)
    if error is not None:
        return {"available": False, "reason": error}

    known = await async_known_keys(hass)
    if is_absent(key, known):
        # Nothing to undo *into*. Bringing the whole dashboard back is a
        # different operation, and `restore_state` already offers it.
        return {"available": False, "reason": f"{key} does not exist right now"}

    live = await async_get_config(hass, key)
    current = live or {}
    plan, before_state = await hass.async_add_executor_job(
        _plan_undo, before_text, text, current
    )
    if plan.blocked is not None:
        return {"available": False, "reason": plan.blocked}
    try:
        result = await hass.async_add_executor_job(apply_undo, current, plan)
    except LookupError as err:
        return {"available": False, "reason": str(err)}

    # In an executor, and not out of habit: since the row itself asks for
    # the undo, this runs on every expansion of a change rather than only
    # on a button click - so a dashboard with a few hundred cards would
    # be dumping YAML and matching cards on the event loop each time.
    diff, explanation, live_text = await hass.async_add_executor_job(
        _preview, current, result, key
    )
    if not diff:
        return {"available": False, "reason": "this change is already taken back"}

    answer = {
        "available": True,
        "applied": False,
        "preview": diff,
        "explanation": explanation,
        # Lets the panel drop the coarse "back to the state before this
        # change" button where it would write exactly the same thing.
        # Worked out here because it is a comparison, and a comparison in
        # the panel is logic in the panel.
        "equals_state_before": result == before_state,
    }
    if not confirm:
        return answer
    # The state about to be overwritten, kept first - the same net the
    # other two writing operations got. It answers with a note rather
    # than a refusal: somebody who cannot be given a snapshot still gets
    # their undo, and is told.
    lost = await _keep_the_live_state(
        hass, store, key, live_text if live is not None else None
    )
    await async_save_config(hass, key, result)
    answer["applied"] = True
    if lost:
        answer["note"] = lost
    return answer


async def async_next_versions(
    hass: HomeAssistant, store: HistoryStore, key: str
) -> dict:
    """The three names the three buttons carry, and the current one.

    A read, so it needs no `confirm`. The panel must not work these out
    itself: the numbering is the one calculation here that can be quietly
    wrong, and it belongs where pytest reaches it.
    """
    found = await hass.async_add_executor_job(store.list_versions, key)
    return {"candidates": versioning.candidates(key, [v.name for v in found])}


async def async_create_version(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    level: str = "patch",
    title: str = "",
    description: str = "",
    revision: str | None = None,
) -> dict:
    """Mark a recorded state of one dashboard as a version.

    No `confirm`, for the same reason `describe` has none: this writes a
    tag, not a dashboard. Nothing anybody can see changes, and removing
    the tag would undo it.

    A version marks a state somebody can come back to, so it is refused
    where there is no state: at a deletion commit the dashboard's file has
    left the tree, and `restore_state` on it can only answer "did not
    exist at". That commit is the topmost row of every deleted dashboard
    and the one the fallback below lands on - which made the case the
    design record calls the most worthwhile one, a version on a dashboard
    that is gone, the only one that could not be returned to. Refused here
    rather than in the panel, so the service is fenced by the same line.
    """
    if level not in versioning.LEVELS:
        return {"created": None, "error": f"unknown level: {level}"}
    if not title.strip():
        # A version is a name for a state, so one without a name is not
        # a version - it is a row somebody cannot pick out of a list
        # again, and this integration has nothing that deletes a tag.
        # `const.KEEP_AS_VERSION` deliberately shapes without judging,
        # and `vol.Required("title"): str` accepts the empty string, so
        # the judgement belongs here - at the fence both ways in pass
        # through, the service and the button alike. Not filled in for:
        # the panel already falls back on the day's own date before it
        # asks, so anything arriving here empty is a caller's mistake,
        # and answering it is worth more than guessing at a name.
        return {"created": None, "error": "a version needs a title"}
    if not revision:
        # Emphatically not HEAD, which is what the store would fall back
        # to. One repository holds every dashboard, so HEAD is whichever
        # dashboard was saved last. Measured: marking `heizung` without a
        # revision just after `solar` was saved tags solar's commit - and
        # the version then never shows up in heizung's history at all,
        # because list_changes walks only the paths that dashboard
        # touched. Wrong, invisible, and impossible to notice later.
        newest = await hass.async_add_executor_job(store.list_changes, key, 1)
        if not newest:
            return {"created": None, "error": f"no recorded state for {key}"}
        revision = newest[0].revision
    # Both ways in end here, so the fence holds for the button and for the
    # service alike. The same separation `_state_at` makes: an unknown
    # revision is a statement about the input, an absent state one about
    # the dashboard's own history.
    full, _, error = await _state_at(hass, store, key, revision)
    if error is not None:
        return {"created": None, "error": error}
    revision = full
    found = await hass.async_add_executor_job(store.list_versions, key)
    name = versioning.candidates(key, [v.name for v in found])[level]
    try:
        await hass.async_add_executor_job(
            store.create_version, name, title, description, revision
        )
    except ValueError as err:
        # A name the store refuses: one git cannot hold beside the others,
        # or one git cannot accept at all - `store.py` turns dulwich's
        # RefFormatError into this same ValueError, so both arrive here.
        # It is an answer, not a crash: the message says what is in the way.
        return {"created": None, "error": str(err)}
    return {"created": name}


async def async_retitle_version(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    name: str,
    title: str,
    description: str = "",
) -> dict:
    """Give a version of one dashboard new words.

    The two fields the create dialog asks for, filled in or corrected
    afterwards - and only those two. The *number* is not among them, and
    that is a decision rather than an omission: decision 13 of the design
    record keeps the number out of anybody's typing on purpose, because a
    tag name is a technical artefact with ref rules behind it, and a
    version name is addressable as a revision - an automation calling
    `restore_state` with `heizung/v1.0.0` would break silently the moment
    the name moved. Whoever wants a different number puts a second
    version beside this one, which is one click and loses nothing. The
    reasoning is in `FAQ.md`, because it is the first question the
    screen provokes.

    No `confirm`, for the same reason `describe` and `create_version`
    have none: this changes a tag's wording. No dashboard changes, and
    nothing anybody can see is different afterwards.

    One executor job, and the store answers with the version it wrote.
    The ownership fence, the refusals and the marker of an automatic
    version all live down there, where the ref is: this used to list a
    dashboard's whole tag namespace first to find one name and read one
    description, which at 365 versions was 35 ms of looking around a
    2 ms write.
    """
    label = title.strip()
    if not label:
        # The same fence `async_create_version` puts up, for the same
        # reason: a version without a name is a row nobody can pick out
        # of a list again. Emptying the field would be a way to *unname*
        # a version, and unlike a description there is nothing that would
        # put a name back.
        return {"applied": False, "error": "a version needs a title"}
    try:
        written = await hass.async_add_executor_job(
            store.retitle_version, key, name, label, description.strip()
        )
    except ValueError as err:
        # Every refusal the store has: not this dashboard's version, no
        # version by that name, or one somebody made by hand that has no
        # message to change. An answer with a sentence in it, like every
        # other refusal here.
        return {"applied": False, "error": str(err)}
    # Through `_version_dict` like every other version that leaves as a
    # payload, so the panel sees one shape and the marker is read rather
    # than shown.
    return {"applied": True, **_version_dict(written)}


async def async_versions(
    hass: HomeAssistant, store: HistoryStore, key: str | None = None
) -> dict:
    """Every named point, newest first. One dashboard's, or all of them.

    With a dashboard, each version also says whether it is the state the
    dashboard holds right now (`same_as_now`). The simple mode of
    decision 17 shows nothing but this list, so the list has to answer
    that on its own - and against every version, not the ones inside a
    window: a version outside the loaded window is exactly the one it
    must still find. Without a dashboard there is no single live state
    to compare against, and the field stays False.
    """
    found = await hass.async_add_executor_job(store.list_versions, key)
    same: set[str] = set()
    if key is not None:
        found = versioning.by_number(key, found)
        if found:
            # Inside the guard, not before it: `async_get_config` loads
            # every storage-mode dashboard there is, and a dashboard that
            # was never tagged has nothing to compare it against.
            live = await async_get_config(hass, key)
            if live is not None:
                same = await hass.async_add_executor_job(
                    _same_as_live, store, key, [v.revision for v in found], live
                )
    return {
        "versions": [
            {**_version_dict(v), "same_as_now": v.revision in same} for v in found
        ]
    }


async def async_describe(
    hass: HomeAssistant, store: HistoryStore, revision: str, text: str
) -> dict:
    """Attach a person's own words to a recorded change.

    No `confirm`, unlike every other writing operation here. The rule in
    the spec protects dashboards from unintended change; a description
    changes no dashboard, is undone by emptying the field, and is read by
    the same person who just wrote it. A dialog in front of it would be
    ceremony without protection - and the opposite of what was asked for.
    """
    ok = await hass.async_add_executor_job(store.set_description, revision, text)
    if not ok:
        return {"applied": False, "error": f"unknown revision: {revision}"}
    return {"applied": True, "description": text.strip()}


async def async_explain(
    hass: HomeAssistant, store: HistoryStore, key: str, revision: str
) -> dict:
    """What one recorded change did, in words.

    `revision` is the change itself, not the state before it - the panel
    must not have to work that out, because working it out wrongly is the
    trap decision 9 of the design record removed rather than signposted.
    """
    full = await hass.async_add_executor_job(store.resolve, revision)
    if full is None:
        return {"groups": [], "note": "", "error": f"unknown revision: {revision}"}
    before = await hass.async_add_executor_job(store.previous_change, key, full)
    if before is None:
        return {"groups": [], "note": "This is the first recorded state."}

    # Deliberately not `_state_at`, which reports an absent state as an
    # error. Here an absent state *is* the answer: at a deletion commit
    # the dashboard's file has left the tree, and comparing against
    # nothing is what says "the whole view was deleted". Reporting "did
    # not exist at" for the one change people most want explained would
    # be the same class of mistake this project has fixed three times.
    old = await hass.async_add_executor_job(store.read_at, key, before)
    new = await hass.async_add_executor_job(store.read_at, key, full)
    return await hass.async_add_executor_job(_explain_texts, old, new)


def _explain_texts(old: str | None, new: str | None) -> dict:
    """The change between two recorded texts, in words. Off the loop."""
    return _as_dict(explain_change(load_state(old), load_state(new)))


async def async_forget(
    hass: HomeAssistant, store: HistoryStore, key: str, confirm: bool = False
) -> dict:
    """Remove a deleted dashboard's history for good.

    The one irreversible operation this integration offers, so it is
    fenced on three sides.

    * **Only a deleted dashboard.** Forgetting a live one would throw away
      the history of something somebody is using. `is_absent` answers
      False when Home Assistant cannot be asked at all, which refuses
      rather than guesses - the right way round for this operation.
    * **`confirm` is required**, and without it the answer is a count of
      what would be lost, not a diff. A diff of a deletion would be the
      whole history.
    * **The rewrite is named, not hidden.** Every revision from the first
      affected commit onwards changes, and the response says so, because
      anyone who wrote a revision down somewhere is about to find it
      stale.
    """
    tracked = set(await hass.async_add_executor_job(store.list_all_dashboards))
    if key not in tracked:
        return {"applied": False, "error": f"no history for dashboard: {key}"}

    known = await async_known_keys(hass)
    if not is_absent(key, known):
        return {
            "applied": False,
            "error": (
                f"{key} is not a deleted dashboard. Only a dashboard Home "
                "Assistant no longer has can be forgotten - delete it first "
                "if that is what you want."
            ),
        }

    changes = await hass.async_add_executor_job(store.list_changes, key, None)
    facts = {
        "states": len(changes),
        "described": sum(1 for c in changes if c.description),
        "first": changes[-1].timestamp if changes else None,
        "last": changes[0].timestamp if changes else None,
        "revisions_change": True,
    }
    if not confirm:
        return {"applied": False, **facts}

    removed = await hass.async_add_executor_job(store.forget, key)
    _LOGGER.warning(
        "Forgot the history of dashboard %s for good: %s commits removed",
        key,
        removed,
    )
    return {"applied": True, "removed": removed, **facts}
