"""Classifying what changed between two dashboard configurations.

Lovelace cards carry no identifier — a card is defined by its position in
a list. Matching them between two states therefore has to work from their
content, and that shapes everything here.

The order matters: an exact content match wins first (that card is
unchanged, possibly moved), then a weak match on type plus the most
identifying field (that card was edited). Only what is left over counts
as removed. Without that ordering an edited card would look like a
deletion plus an addition, and the interface would offer to restore
something that is still there.

The package has five modules in layers, each importing only from those
below it (checked by `lint-imports`): `model` (types, reading and naming
a dashboard), `matching` (pairing two states), `removed` (Put back),
and on top `explain` (the words) and `undo` (the targeted undo). This
file holds no logic; it names what callers reach as `analyze.<name>`.
"""

from __future__ import annotations

from .explain import (
    RECORDED_BY_HAND,
    _ENTRY_LIMIT,
    _counts,
    change_message,
    explain_change,
    explain_effect,
    message_adds,
    summarize,
)
from .matching import (
    _moved,
    _pair_sections,
    match_badges,
    match_cards,
    match_sections,
    setting_changes,
)
from .model import (
    _ABSENT,
    RemovedItem,
    UndoPlan,
    UndoStep,
    _describe,
    _views_by_key,
    card_containers,
    same_config,
)
from .removed import find_removed
from .undo import _POSITION_REFUSAL, _SECTIONS_AND_CARDS_REFUSAL, _plan_sections, plan_undo

__all__ = [
    "RECORDED_BY_HAND",
    "RemovedItem",
    "UndoPlan",
    "UndoStep",
    "_ABSENT",
    "_ENTRY_LIMIT",
    "_POSITION_REFUSAL",
    "_SECTIONS_AND_CARDS_REFUSAL",
    "_counts",
    "_describe",
    "_moved",
    "_pair_sections",
    "_plan_sections",
    "_views_by_key",
    "card_containers",
    "change_message",
    "explain_change",
    "explain_effect",
    "find_removed",
    "match_badges",
    "match_cards",
    "match_sections",
    "message_adds",
    "plan_undo",
    "same_config",
    "setting_changes",
    "summarize",
]
