"""The words for a change: history line, explanation, counts."""

from __future__ import annotations

import re
from typing import Any

from .matching import (
    _setting_leaves,
    _view_type,
    match_badges,
    match_cards,
    setting_changes,
)
from .model import (
    Entry,
    Explanation,
    SectionPair,
    SectionSlot,
    SettingChange,
    Slot,
    Summary,
    ViewChanges,
    _ABSENT,
    _describe,
    _own,
    _place,
    _section_title,
    _shorten,
    _view_name,
    _views_by_key,
    same_config,
)


def summarize(old: dict, new: dict) -> Summary:
    """Count what changed, for the history display."""
    matching = match_cards(old, new)

    # A whole view arriving or leaving is one view, not the sum of its
    # cards. It used to be counted by its cards, on the argument that a
    # count says how much - and the message then contradicted the
    # explanation of the very same commit: "1 removed, 1 added" beside
    # 'the whole view "home" was deleted', or "no card changes" for a
    # renamed view that happened to be empty. One grain for both.
    old_keys = {key for key, _ in _views_by_key(old)}
    new_keys = {key for key, _ in _views_by_key(new)}

    badges = match_badges(old, new)

    section_settings = sum(
        len(_section_setting_changes(pair))
        for pair in matching.sections.pairs
        if pair.how == "settings"
    )

    # One entry per moved card already, so a swap contributes two.
    # Multiplying would count each of them twice.
    return Summary(
        added=len(matching.loose_added()),
        removed=len(matching.loose_removed()),
        edited=len(matching.edited),
        moved=len(matching.moved),
        views_added=len(new_keys - old_keys),
        views_removed=len(old_keys - new_keys),
        settings=len(setting_changes(old, new)) + section_settings,
        badges=len(badges.removed) + len(badges.added) + len(badges.edited) + len(badges.moved),
        sections_moved=len(matching.sections.moved),
        sections_added=len(matching.sections.added),
        sections_removed=len(matching.sections.removed),
    )



# Card labels already carry their type ("tile: light.b"), so they need no
# quotes. A view label is a bare name and does.
_PAST = {
    ("section", "removed"): "{label} was removed",
    ("section", "added"): "{label} was added",
    ("section", "moved"): "{label} was moved",
    ("badge", "removed"): "the badge {label} was deleted",
    ("badge", "added"): "the badge {label} was added",
    ("badge", "edited"): "the badge {label} was changed",
    ("badge", "moved"): "the badge {label} was moved",
    ("badge", "moved_to"): "the badge {label} was moved to {where}",
    ("setting", "added"): 'the setting "{label}" was set to {new}',
    ("setting", "added_bare"): 'the setting "{label}" was set',
    ("setting", "removed"): 'the setting "{label}" was removed',
    ("setting", "edited"): 'the setting "{label}" was changed from {old} to {new}',
    ("setting", "edited_bare"): 'the setting "{label}" was changed',
    ("card", "removed"): "{label} was deleted",
    ("card", "added"): "{label} was added",
    ("card", "edited"): "{label} was changed",
    ("card", "moved"): "{label} was moved",
    ("card", "moved_to"): "{label} was moved to {where}",
    ("view", "removed"): 'the whole view "{label}" was deleted',
    ("view", "added"): 'the whole view "{label}" was added',
    ("view", "type_changed"): 'the view "{label}" was converted from {old_type} to {new_type}',
}



_FUTURE = {
    ("section", "removed"): "{label} will be removed",
    ("section", "added"): "{label} comes back",
    ("section", "moved"): "{label} moves back to where it was",
    ("badge", "removed"): "the badge {label} will be deleted",
    ("badge", "added"): "the badge {label} comes back",
    ("badge", "edited"): "the badge {label} goes back to how it was",
    ("badge", "moved"): "the badge {label} moves back to where it was",
    ("badge", "moved_to"): "the badge {label} moves back to {where}",
    ("setting", "added"): 'the setting "{label}" comes back as {new}',
    ("setting", "added_bare"): 'the setting "{label}" comes back',
    ("setting", "removed"): 'the setting "{label}" will be removed',
    ("setting", "edited"): 'the setting "{label}" goes back to {new}',
    ("setting", "edited_bare"): 'the setting "{label}" goes back to how it was',
    ("card", "removed"): "{label} will be deleted",
    ("card", "added"): "{label} comes back",
    ("card", "edited"): "{label} goes back to how it was",
    ("card", "moved"): "{label} moves back to where it was",
    ("card", "moved_to"): "{label} moves back to {where}",
    ("view", "removed"): 'the whole view "{label}" will be deleted',
    ("view", "added"): 'the whole view "{label}" comes back',
    ("view", "type_changed"): 'the view "{label}" changes layout from {old_type} to {new_type}',
}



# A dashboard restored from nothing would otherwise list every card it
# ever had - 661 of them on the installation this was built against.
_ENTRY_LIMIT = 12



_NOTHING_LOST = "Nothing on this dashboard is deleted."



_NOT_IN_CARDS = (
    "This change cannot be described in terms of cards - see the details below."
)



def _entry(words: dict, kind: str, what: str, label: str) -> Entry:
    return Entry(
        kind=kind,
        what=what,
        label=label,
        text=words[(what, kind)].format(label=label),
    )



def _value_text(value: Any) -> str | None:
    """A setting's value as a sentence can carry it, or None if it cannot.

    Short things only. A list or a block is left to the diff below the
    sentence, which shows it exactly (decision 11).
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{_shorten(value)}"'
    return None



def _setting_entry(words: dict, change: SettingChange) -> Entry:
    label = ".".join(str(key) for key in change.path)
    if change.new is _ABSENT:
        kind, key, values = "removed", "removed", {}
    elif change.old is _ABSENT:
        new = _value_text(change.new)
        kind = "added"
        key, values = ("added", {"new": new}) if new is not None else ("added_bare", {})
    else:
        old, new = _value_text(change.old), _value_text(change.new)
        kind = "edited"
        # Whether `old` has to be there too depends on the wording this
        # tense uses, not on which table this happens to be - the same
        # reason `_explain` takes `reassure` instead of asking `words is
        # _FUTURE`. The future tense's own template never mentions
        # {old}, so a missing one there is nothing to fall back from.
        if new is not None and (old is not None or "{old}" not in words[("setting", "edited")]):
            key, values = "edited", {"old": old, "new": new}
        else:
            key, values = "edited_bare", {}
    return Entry(
        kind=kind,
        what="setting",
        label=label,
        text=words[("setting", key)].format(label=label, **values),
    )



def _section_setting_changes(pair: SectionPair) -> list[SettingChange]:
    """A paired section's own settings that differ, by name like a view's (M)."""
    out: list[SettingChange] = []
    _setting_leaves(pair.old.view_key, _own(pair.old.section), _own(pair.new.section), (), out)
    return out



def _capped(name: str, entries: list[Entry], scope: str = "view") -> ViewChanges:
    """Keep the list readable, and say how much it hides.

    Silently truncating would be the one thing this project must not do:
    a summary that omits without saying so is worse than a long one.
    """
    if len(entries) <= _ENTRY_LIMIT:
        return ViewChanges(view=name, entries=entries, scope=scope)
    return ViewChanges(
        view=name,
        entries=entries[:_ENTRY_LIMIT],
        more=len(entries) - _ENTRY_LIMIT,
        scope=scope,
    )



def _section_name(slot: Slot) -> str:
    """The section a card landed in, named the way Home Assistant names one.

    Not by a `title` field: measured on the installation this was built
    against, 0 of 80 sections carry one. Home Assistant names a section
    with a `heading` card at its top instead, and 51 of those 80 have
    one. Where there is none there is no name to give, and saying so
    beats inventing one. Named by the same rule as every other section
    (`_section_title`).
    """
    if slot.location[:1] != ("sections",):
        if slot.location == ("cards",) and _view_type(slot.view) == "sections":
            # The view's own list, in a sections view, is what Home
            # Assistant shows as "Imported cards" (decision 26).
            return 'the "Imported cards" area'
        return "another place in this view"
    sections = slot.view.get("sections") or []
    index = slot.location[1]
    section = sections[index] if 0 <= index < len(sections) else {}
    title = _section_title(section, index)
    return f"the {title}" if title.startswith('section "') else title



def _where(old_slot: Slot, new_slot: Slot) -> str:
    """Where a card went, said from the place it left."""
    if new_slot.view_key != old_slot.view_key:
        return f'"{_view_name(new_slot.view, new_slot.view_key)}"'
    return _section_name(new_slot)



def _explain(old: dict, new: dict, words: dict, reassure: bool) -> Explanation:
    """The engine behind both tenses.

    `reassure` says whether a "nothing is lost" line is wanted when
    nothing is removed. It is passed rather than inferred from `words`:
    identity of a wording table is not the question being asked.

    Cards are grouped by the view they sat in *before*. A card that left
    for another view is reported in the view it left - that is where
    somebody who misses it looks - and it says where it went instead of
    leaving them to guess.
    """
    matching = match_cards(old, new)
    settings_by_view: dict[Any, list[Entry]] = {}
    for change in setting_changes(old, new):
        settings_by_view.setdefault(change.view_key, []).append(_setting_entry(words, change))
    badges_by_view: dict[Any, list[Entry]] = {}
    badge_matching = match_badges(old, new)

    def badge(key: Any, kind: str, item: Any, where: str | None = None) -> None:
        label = _describe(item, fallback="badge")
        text_key = ("badge", "moved_to" if where else kind)
        badges_by_view.setdefault(key, []).append(
            Entry(
                kind=kind,
                what="badge",
                label=label,
                text=words[text_key].format(label=label, where=where),
            )
        )

    for slot in badge_matching.removed:
        badge(slot.view_key, "removed", slot.card)
    for slot in badge_matching.added:
        badge(slot.view_key, "added", slot.card)
    for _was, now in badge_matching.edited:
        badge(now.view_key, "edited", now.card)
    for was, now in badge_matching.moved:
        where = _where(was, now) if _place(was) != _place(now) else None
        badge(was.view_key, "moved", was.card, where)
    sections_by_view: dict[Any, list[Entry]] = {}

    def section(key: Any, kind: str, slot: SectionSlot) -> None:
        sections_by_view.setdefault(key, []).append(
            _entry(words, kind, "section", _section_title(slot.section, slot.index))
        )

    for slot in matching.sections.removed:
        section(slot.view_key, "removed", slot)
    for slot in matching.sections.added:
        section(slot.view_key, "added", slot)
    for pair in matching.sections.moved:
        section(pair.old.view_key, "moved", pair.old)
    for pair in matching.sections.pairs:
        if pair.how != "settings":
            continue
        title = _section_title(pair.old.section, pair.old.index)
        for change in _section_setting_changes(pair):
            said = _setting_entry(words, change)
            sections_by_view.setdefault(pair.old.view_key, []).append(
                Entry(
                    kind=said.kind,
                    what="section_setting",
                    label=f"{title}: {said.label}",
                    text=f"{title}: {said.text}",
                )
            )
    by_view: dict[Any, list[Entry]] = {}

    def add(key: Any, entry: Entry) -> None:
        by_view.setdefault(key, []).append(entry)

    for slot in matching.loose_removed():
        add(slot.view_key, _entry(words, "removed", "card", _describe(slot.card)))
    for slot in matching.loose_added():
        add(slot.view_key, _entry(words, "added", "card", _describe(slot.card)))
    for _was, now in matching.edited:
        add(now.view_key, _entry(words, "edited", "card", _describe(now.card)))
    for was, now in matching.moved:
        label = _describe(was.card)
        if matching.same_place(was, now):
            add(was.view_key, _entry(words, "moved", "card", label))
        else:
            add(
                was.view_key,
                Entry(
                    kind="moved",
                    what="card",
                    label=label,
                    text=words[("card", "moved_to")].format(
                        label=label, where=_where(was, now)
                    ),
                ),
            )

    new_views = dict(_views_by_key(new))
    old_keys = {key for key, _ in _views_by_key(old)}
    groups: list[ViewChanges] = []
    removed_anything = False

    own = settings_by_view.get(None, [])
    if own:
        # The dashboard's own settings have no view to sit under, and a
        # heading "In the view dashboard" would invent one.
        groups.append(_capped("dashboard", own, scope="dashboard"))
        removed_anything = any(entry.kind == "removed" for entry in own)

    for key, old_view in _views_by_key(old):
        name = _view_name(old_view, key)
        if key not in new_views:
            # One line for the view, not one per card on it.
            groups.append(ViewChanges(name, [_entry(words, "removed", "view", name)]))
            removed_anything = True
            continue
        entries = [
            *settings_by_view.get(key, []),
            *badges_by_view.get(key, []),
            *sections_by_view.get(key, []),
            *by_view.get(key, []),
        ]
        new_view = new_views[key]
        old_type, new_type = _view_type(old_view), _view_type(new_view)
        if old_type != new_type:
            # Ahead of any card entries: the conversion is the actual
            # event, and `type` is not a card - without this, a save that
            # only converts a view has nothing to hang an entry on at all.
            entries.insert(
                0,
                Entry(
                    kind="type_changed",
                    what="view",
                    label=name,
                    text=words[("view", "type_changed")].format(
                        label=name, old_type=old_type, new_type=new_type
                    ),
                ),
            )
        if entries:
            groups.append(_capped(name, entries))
            removed_anything = removed_anything or any(
                entry.kind == "removed" for entry in entries
            )

    for key, new_view in _views_by_key(new):
        if key not in old_keys:
            name = _view_name(new_view, key)
            groups.append(ViewChanges(name, [_entry(words, "added", "view", name)]))

    if not groups:
        # Something changed - the caller only asks when it did - but not
        # anything this can name. Saying "nothing changed" above a diff
        # that shows the difference would be refuted at a glance.
        return Explanation(groups=[], note=_NOT_IN_CARDS)
    if removed_anything or not reassure:
        return Explanation(groups=groups)
    return Explanation(groups=groups, note=_NOTHING_LOST)



def explain_change(old: dict, new: dict) -> Explanation:
    """What one recorded change did, in words. Past tense."""
    return _explain(old, new, _PAST, reassure=False)



def explain_effect(current: dict, target: dict) -> Explanation:
    """What applying a restore would do, in words. Future tense.

    The reassurance matters here and not in the past tense: before
    pressing Apply, the question is not what changed but what is at risk.
    """
    return _explain(current, target, _FUTURE, reassure=True)



def _meta_detail(old_meta: dict | None, new_meta: dict | None) -> str:
    """What changed about a dashboard, as opposed to on it."""
    if not new_meta or old_meta is None or old_meta == new_meta:
        return "metadata recorded"
    if new_meta.get("title") and old_meta.get("title") != new_meta.get("title"):
        return f'renamed to "{new_meta["title"]}"'
    fields = sorted(
        field
        for field in set(old_meta) | set(new_meta)
        if old_meta.get(field) != new_meta.get(field)
    )
    return f"{', '.join(fields)} changed" if fields else "metadata recorded"



def _views(count: int, verb: str) -> str:
    """"1 view removed", "2 views added", or nothing."""
    if not count:
        return ""
    return f"{count} view{'s' if count != 1 else ''} {verb}"



def _sections_part(count: int, verb: str) -> str:
    """"1 section moved", "2 sections added", or nothing."""
    if not count:
        return ""
    return f"{count} section{'s' if count != 1 else ''} {verb}"



def change_message(
    name: str,
    old: dict | None,
    new: dict,
    reason: str,
    old_meta: dict | None = None,
    new_meta: dict | None = None,
) -> str:
    """The one line that will stand in the history for this change.

    People read these while looking for something they lost, so they have
    to be exactly true. A message that claims more than happened is worse
    than a vague one - "changed outside Home Assistant" shown to somebody
    whose dashboard nobody touched is an accusation, not a note.

    `old` is None when nothing was recorded yet. `reason` is "save" for a
    change Home Assistant announced, and anything else for one found by
    comparison, where nobody can say what caused it.
    """
    if old is None:
        return f"{name}: first recorded state"
    # `==` alone says 1 is True; the commit this message goes with does
    # not, and neither does the explanation shown under it.
    if same_config(old, new):
        # Not the cards, then. Something *about* the dashboard changed -
        # its title, its icon - or nothing did and only metadata was
        # recorded for the first time. Either way: no outside change.
        return f"{name}: {_meta_detail(old_meta, new_meta)}"
    if reason != "save":
        # Changed while nobody was listening: a restored backup, a
        # hand-edited storage file, another tool. Recording that as an
        # ordinary save would hide it.
        return f"{name}: changed outside Home Assistant"
    counts = summarize(old, new)
    parts = [
        _views(counts.views_removed, "removed"),
        _views(counts.views_added, "added"),
        _sections_part(counts.sections_removed, "removed"),
        _sections_part(counts.sections_added, "added"),
        _sections_part(counts.sections_moved, "moved"),
        f"{counts.removed} removed" if counts.removed else "",
        f"{counts.added} added" if counts.added else "",
        f"{counts.edited} edited" if counts.edited else "",
        f"{counts.moved} moved" if counts.moved else "",
        f"{counts.settings} setting{'s' if counts.settings != 1 else ''} changed"
        if counts.settings
        else "",
        f"{counts.badges} badge{'s' if counts.badges != 1 else ''} changed"
        if counts.badges
        else "",
    ]
    return f"{name}: " + (", ".join(part for part in parts if part) or "no card changes")



# One count part of a generated message, as a whole part rather than as
# something found inside one. The vocabulary is the one `change_message`
# writes just above and `_views` beside it; the two live next to each
# other on purpose, because a word added there and not here would read
# as "this is not a generated message at all".
_COUNT = re.compile(
    r"^\d+ (?:views? (?:added|removed)|sections? (?:added|removed|moved)"
    r"|added|removed|edited|moved|settings? changed|badges? changed)$"
)



def _counts(message: str) -> list[str] | None:
    """The count parts of a generated message, or None if it is not one.

    A generated count line is made *entirely* of counts, which is what
    makes this a structural reading rather than a search for words. The
    dashboard's own name sits in front of them behind a `": "`, and a
    name may hold one of those itself - "Home: ground floor" is a title
    somebody will write - so the lead-in is peeled off one `": "` at a
    time until what is left parses whole. Nothing parses whole by
    accident: `renamed to "3 added"` does not, because of the quotes;
    "icon, title changed" does not, because "icon" is not a count.
    """
    rest = message
    while True:
        parts = [part.strip() for part in rest.split(",")]
        if parts and all(_COUNT.match(part) for part in parts):
            return parts
        _, found, rest = rest.partition(": ")
        if not found:
            return None



def message_adds(message: str) -> bool:
    r"""Whether the change behind this message added something.

    Read here, where the wording is written, and read as a shape rather
    than sniffed for a substring. The panel used to run
    `/\d+ added/` over the message to decide whether offering a plain
    put-back would be a trap - a change that removed *and* added
    something cannot be undone by putting the removed thing back,
    because the added one stays. That is logic in the panel, which the
    design record rules out; worse, it is wrong on a real message. A
    dashboard renamed to `3 added` produces `home: renamed to "3 added"`
    and reads as a trap, on a change that touched no card at all.

    Views count as well as cards, and that is deliberate: the panel's
    regex missed `2 views added`, because of the word in between, and a
    view that appeared is as much a thing a put-back leaves standing as
    a card that did. The wider reading is the true one.

    False for every message that is not a count line - the first
    recorded state, a rename, a change found by comparison. None of
    those added anything the caller can put back.
    """
    parts = _counts(message)
    return any(part.endswith(" added") for part in parts or [])
