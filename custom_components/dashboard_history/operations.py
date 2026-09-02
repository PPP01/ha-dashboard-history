"""Every operation the integration offers, in one place.

The services and the panel are both thin skins over this module. The panel
is the layer most likely to break, and letting it grow logic of its own
would put the important part exactly there. So it gets none.

Nothing here writes without an explicit `confirm`; without it each
restoring operation answers with a preview and changes nothing.
"""

from __future__ import annotations

import difflib
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .analyze import explain_change, explain_effect, find_removed
from . import versions as versioning
from .keys import is_absent, is_live
from .restore import reinsert
from .snapshot import (
    async_create_dashboard,
    async_get_all_meta,
    async_get_config,
    async_known_keys,
    async_save_config,
)
from .store import HistoryStore
from .yaml_io import dump, load

_LOGGER = logging.getLogger(__name__)


def _diff(old: dict, new: dict, name: str) -> str:
    """A unified diff between two configurations, empty when equal."""
    return "".join(
        difflib.unified_diff(
            dump(old).splitlines(keepends=True),
            dump(new).splitlines(keepends=True),
            fromfile=f"live/{name}",
            tofile=f"restored/{name}",
        )
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
    tracked = set(await hass.async_add_executor_job(store.list_dashboards))
    ever = await hass.async_add_executor_job(store.list_all_dashboards)
    known = await async_known_keys(hass)
    meta = await async_get_all_meta(hass)

    dashboards = []
    for key in ever:
        exists = is_live(key, tracked, known)
        info = meta.get(key)
        if info is None:
            # Gone, so Home Assistant can say nothing about it. Its own last
            # recorded name is better than falling back to the bare key.
            text = await hass.async_add_executor_job(store.last_known_meta, key)
            info = (load(text) if text else None) or {}
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
    hass: HomeAssistant, store: HistoryStore, key: str, limit: int = 50
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
    """
    changes = await hass.async_add_executor_job(store.list_changes, key, limit)
    # Which versions sit on which state. Gathered here rather than in the
    # panel: the panel would need a second call and a join, and a join is
    # logic. Two versions on one commit is allowed, so this is a list.
    marks: dict[str, list[dict]] = {}
    for version in await hass.async_add_executor_job(store.list_versions, key):
        marks.setdefault(version.revision, []).append(
            {
                "name": version.name,
                "title": version.title,
                "description": version.description,
            }
        )
    live = await async_get_config(hass, key)
    same: set[str] = set()
    if live is not None and changes:
        same = await hass.async_add_executor_job(
            store.matching_revisions,
            key,
            [c.revision for c in changes],
            dump(live),
        )
    return {
        "changes": [
            {
                "revision": c.revision,
                "timestamp": c.timestamp,
                "message": c.message,
                "description": c.description,
                "same_as_now": c.revision in same,
                "versions": marks.get(c.revision, []),
            }
            for c in changes
        ]
    }


async def async_deleted_since(
    hass: HomeAssistant, store: HistoryStore, key: str, revision: str
) -> dict:
    """What was present at a revision and is gone now."""
    _, text, error = await _state_at(hass, store, key, revision)
    if error is not None:
        return {"items": [], "error": error}
    current = await async_get_config(hass, key) or {}
    items = find_removed(load(text) or {}, current)
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
    current = await async_get_config(hass, key) or {}
    items = find_removed(load(text) or {}, current)
    if not items:
        return {"applied": False, "error": "nothing is missing since that revision"}
    if not 0 <= position < len(items):
        return {
            "applied": False,
            "error": f"position {position} out of range (0..{len(items) - 1})",
        }
    try:
        restored = reinsert(current, items[position])
    except LookupError as err:
        # The place it belonged to is gone. Every other failure here answers
        # with a message rather than an exception; this one should too, or
        # the caller is handed a bare traceback.
        return {"applied": False, "error": str(err)}
    diff = _diff(current, restored, key)
    explanation = _as_dict(explain_effect(current, restored))
    if not confirm:
        return {"applied": False, "preview": diff, "explanation": explanation}
    await async_save_config(hass, key, restored)
    return {
        "applied": True,
        "preview": diff,
        "explanation": explanation,
        "restored": items[position].label,
    }


async def async_restore_state(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    revision: str,
    confirm: bool = False,
) -> dict:
    """Set a dashboard back to an earlier state, creating it if it is gone."""
    full, text, error = await _state_at(hass, store, key, revision)
    if error is not None:
        return {"applied": False, "error": error}
    target = load(text) or {}

    # A dashboard that is gone entirely is restored, not refused. It is the
    # heaviest loss this tool can witness; refusing exactly there while
    # offering everything for a single card made no sense.
    known = await async_known_keys(hass)
    missing = is_absent(key, known)
    current = {} if missing else (await async_get_config(hass, key) or {})
    diff = _diff(current, target, key)
    if not diff and not missing:
        return {"applied": False, "preview": "", "note": "already identical"}
    explanation = _as_dict(explain_effect(current, target))
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
            # still much better than falling back to the bare key.
            meta_text = await hass.async_add_executor_job(store.last_known_meta, key)
        meta = (load(meta_text) if meta_text else None) or {}
        try:
            note = await async_create_dashboard(hass, key, meta)
        except HomeAssistantError as err:
            # Recreating needs Home Assistant's own dashboard collection,
            # and it refuses rather than write something that only looks
            # like a dashboard. That is an answer, not a crash: the message
            # says what a person can do instead.
            return {"applied": False, "error": str(err)}
        created = True
    await async_save_config(hass, key, target)
    result = {
        "applied": True,
        "preview": diff,
        "explanation": explanation,
        "created": created,
    }
    if note:
        result["note"] = note
    return result


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


async def async_versions(
    hass: HomeAssistant, store: HistoryStore, key: str | None = None
) -> dict:
    """Every named point, newest first. One dashboard's, or all of them."""
    found = await hass.async_add_executor_job(store.list_versions, key)
    if key is not None:
        # By number, not by the time the tag was made. Those differ as
        # soon as somebody goes back and marks an older state: the newer
        # tag then carries the lower number, and ordering by time would
        # put it on top of one that contains it.
        found = sorted(
            found,
            key=lambda v: versioning.parse(key, v.name) or (-1, -1, -1),
            reverse=True,
        )
    return {
        "versions": [
            {
                "name": v.name,
                "revision": v.revision,
                "title": v.title,
                "description": v.description,
            }
            for v in found
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
    # yaml_io.load(None) raises; load("") answers None. Measured.
    return _as_dict(explain_change(load(old or "") or {}, load(new or "") or {}))


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

    changes = await hass.async_add_executor_job(store.list_changes, key, 1000)
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
