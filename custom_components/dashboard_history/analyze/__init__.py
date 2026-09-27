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
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import Any, NamedTuple
from .model import (
    Entry,
    Explanation,
    Matching,
    RemovedItem,
    SectionMatching,
    SectionPair,
    SectionSlot,
    SettingChange,
    Slot,
    Summary,
    UndoPlan,
    UndoStep,
    ViewChanges,
    _ABSENT,
    _LABEL_LIMIT,
    _SectionAnchor,
    _by_position,
    _describe,
    _first_entity,
    _first_line,
    _inner_card,
    _own,
    _place,
    _section_list,
    _section_title,
    _shorten,
    _translated,
    _view_name,
    _views_by_key,
    _weak_key,
    badge_containers,
    card_containers,
    fingerprint,
    same_config,
)
from .matching import (
    _NOT_VIEW_SETTINGS,
    _count_places,
    _match_slots,
    _moved,
    _pair_sections,
    _pair_view_sections,
    _paths_collide,
    _positions_lie,
    _reordered,
    _same,
    _same_marks,
    _section_anchor,
    _section_drift,
    _section_marks,
    _setting_at,
    _setting_leaves,
    _settle_sections,
    _similarity,
    _slots,
    _unpaired,
    _view_type,
    _view_type_changed,
    _whole,
    match_badges,
    match_cards,
    match_sections,
    setting_changes,
)
from .removed import (
    find_removed,
)
from .explain import (
    _COUNT,
    _ENTRY_LIMIT,
    _FUTURE,
    _NOTHING_LOST,
    _NOT_IN_CARDS,
    _PAST,
    _capped,
    _counts,
    _entry,
    _explain,
    _meta_detail,
    _section_name,
    _section_setting_changes,
    _sections_part,
    _setting_entry,
    _value_text,
    _views,
    _where,
    change_message,
    explain_change,
    explain_effect,
    message_adds,
    summarize,
)
from .undo import (
    _DUPLICATE_PATH_REFUSAL,
    _POSITION_REFUSAL,
    _SECTIONS_AND_CARDS_REFUSAL,
    _VIEW_TYPE_REFUSAL,
    _group_by_mark,
    _in_view,
    _plan_sections,
    _present,
    _step,
    plan_undo,
)
