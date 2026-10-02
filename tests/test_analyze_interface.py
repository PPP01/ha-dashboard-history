"""The names reachable as `analyze.<name>` are a decision, not an accident.

Spec P, section 2: the package exports what code and tests use today,
and nothing else. Every other name keeps its name in its own module
(analyze.model.fingerprint). A name is added here when a caller needs it.
"""

import analyze

INTERFACE = {
    # used by operations.py, capture.py and restore.py
    "RECORDED_BY_HAND", "RemovedItem", "UndoPlan", "UndoStep", "change_message", "explain_change",
    "explain_effect", "find_removed", "message_adds", "plan_undo", "same_config",
    # used by the tests
    "card_containers", "match_badges", "match_cards", "match_sections",
    "setting_changes", "summarize",
    "_ABSENT", "_ENTRY_LIMIT", "_POSITION_REFUSAL", "_SECTIONS_AND_CARDS_REFUSAL",
    "_counts", "_describe", "_moved", "_pair_sections", "_plan_sections", "_views_by_key",
}


def test_the_package_exports_exactly_its_interface():
    assert set(analyze.__all__) == INTERFACE


def test_every_exported_name_resolves():
    for name in INTERFACE:
        assert getattr(analyze, name) is not None, name
