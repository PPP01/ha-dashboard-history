"""Compare plan_undo as it was after P2 with the working tree (spec P, section 4).

A temporary tool for the duration of P3; the last commit of P removes
it. It loads the analyze package from BASE_COMMIT with dulwich (no git
binary, per the hard rule), under the name analyze_before_p3, next to
the package in the working tree, and feeds both the same inputs: cases
built on purpose, generated histories, and - if one is configured the
way conftest.py finds it - the real dashboards of a .storage directory.
It compares plan_undo and the effect of restore.apply_undo in a strict
canonical form, measures plan_undo's time, and prints a summary that
contains numbers and refusal templates only, never a dashboard.

Run from the repository root: python3 tests/equivalence/compare_undo.py
"""

from __future__ import annotations

import copy
import dataclasses
import importlib
import itertools
import json
import os
import pathlib
import random
import re
import sys
import tempfile
import time
import traceback

from dulwich.object_store import tree_lookup_path
from dulwich.repo import Repo

BASE_COMMIT = "37472532a1d9e54031a16e370bd828ad39daf025"
SEEDS = (1, 2, 3, 4, 5)
TRIPLES_PER_SEED = 2000

ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_DIR = ROOT / "custom_components" / "dashboard_history"


def _load_old():
    """The analyze package of BASE_COMMIT, importable as analyze_before_p3."""
    target = pathlib.Path(tempfile.mkdtemp()) / "analyze_before_p3"
    target.mkdir()
    with Repo(str(ROOT)) as repo:
        commit = repo[BASE_COMMIT.encode()]
        _mode, sha = tree_lookup_path(
            repo.__getitem__, commit.tree, b"custom_components/dashboard_history/analyze"
        )
        for entry in repo[sha].items():
            name = entry.path.decode()
            if name.endswith(".py"):
                (target / name).write_bytes(repo[entry.sha].data)
        # Both versions run through the working tree's restore.py. That is
        # only fair while it is the restore.py of BASE_COMMIT - P changes
        # nothing there, and this holds it to that (Gemini, plan review).
        _mode, restore_sha = tree_lookup_path(
            repo.__getitem__, commit.tree, b"custom_components/dashboard_history/restore.py"
        )
        if repo[restore_sha].data != (PACKAGE_DIR / "restore.py").read_bytes():
            sys.exit("restore.py differs from BASE_COMMIT; P must not change it")
    sys.path.insert(0, str(target.parent))
    return importlib.import_module("analyze_before_p3")


sys.path.insert(0, str(PACKAGE_DIR))
OLD = _load_old()
import analyze as NEW  # noqa: E402
import restore  # noqa: E402
from analyze import undo as NEW_UNDO  # noqa: E402

# Every refusal plan_undo can give, as it reads in the source; `{…}` is
# whatever gets filled in. Each refusal must match exactly one of them.
TEMPLATES = (
    'the sections of the view "{…}" changed in a way this undo cannot account for, so it refuses rather than guess',
    'the view "{…}" is no longer on the dashboard, so its sections cannot be taken back',
    'the sections of the view "{…}" are not a plain list in every state, so an exact undo cannot write them back',
    'the other sections of the view "{…}" were rearranged since, so there is no telling where these go back',
    'more than one section of the view "{…}" was changed since, so which is which can no longer be proven',
    "the {…} was changed again after this, so there is no exact version left to take back",
    "{…} sections now look exactly like {…}, so an exact undo cannot tell them apart",
    "this change did not alter any cards",
    "__DUPLICATE_PATH__",
    "__POSITION__",
    "__VIEW_TYPE__",
    'the view "{…}" is no longer on the dashboard, so its setting "{…}" cannot be taken back',
    'the setting "{…}" no longer has the "{…}" block it belonged to',
    'the setting "{…}" was changed again after this',
    "{…} was changed again after this, so there is no exact version left to put back",
    "{…} cards now look exactly like {…}, so an exact undo cannot tell them apart",
    "only some of the copies of {…} this change deleted are back, so an exact undo cannot tell which are missing",
    "{…} badges now look exactly like {…}, so an exact undo cannot tell them apart",
    '{…} views now look exactly like "{…}", so an exact undo cannot tell them apart',
    'the view "{…}" was changed again after this',
    'the view "{…}" is no longer on the dashboard as this change left it, so an exact undo cannot take it away',
    'a different view now sits at "{…}", so the view "{…}" cannot be put back there',
    "__SECTIONS_AND_CARDS__",
)
_FIXED = {
    "__DUPLICATE_PATH__": OLD.undo._DUPLICATE_PATH_REFUSAL,
    "__POSITION__": OLD._POSITION_REFUSAL,
    "__VIEW_TYPE__": OLD.undo._VIEW_TYPE_REFUSAL,
    "__SECTIONS_AND_CARDS__": OLD._SECTIONS_AND_CARDS_REFUSAL,
}


def _pattern(template: str) -> re.Pattern:
    if template in _FIXED:
        return re.compile(re.escape(_FIXED[template]))
    return re.compile(".+?".join(re.escape(part) for part in template.split("{…}")), re.S)


PATTERNS = [(t, _pattern(t)) for t in TEMPLATES]


def template_of(text: str) -> str:
    hits = [t for t, p in PATTERNS if p.fullmatch(text)]
    if len(hits) != 1:
        raise AssertionError(f"a refusal matches {len(hits)} templates: {hits}")
    return hits[0]


# -- canonical form -------------------------------------------------------


def canon(value):
    """A form in which True is not 1 and the old and new classes compare."""
    if value is OLD._ABSENT or value is NEW._ABSENT:
        return ("<absent>",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float, str)) or value is None:
        return (type(value).__name__, value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = {f.name: canon(getattr(value, f.name)) for f in dataclasses.fields(value)}
        if type(value).__name__ == "UndoPlan":
            fields["parked"] = canon(value.parked)
        return (type(value).__name__, fields)
    if isinstance(value, dict):
        return ("dict", tuple((canon(k), canon(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(canon(v) for v in value))
    raise TypeError(f"no canonical form for {type(value).__name__}")


def outcome(module, before, after, current):
    """What plan_undo answers, what applying it does, and how long planning took."""
    start = time.perf_counter()
    try:
        plan = module.plan_undo(before, after, current)
    except Exception as exc:  # compared, not hidden
        return ("raised", *_where_raised(exc)), None, time.perf_counter() - start
    took = time.perf_counter() - start
    try:
        effect = ("applied", canon(restore.apply_undo(current, plan)))
    except Exception as exc:  # LookupError is the expected one; any other is compared too
        effect = ("apply raised", *_where_raised(exc))
    return (canon(plan), effect), plan, took


def _where_raised(exc: Exception) -> tuple:
    """Type, text, and the function and source line that raised.

    The innermost frame sits in code both versions share unchanged (the
    helpers moved in P2, restore.py), so the same failure names the same
    function and line in both - and a different one does not (Gemini,
    plan review).
    """
    frame = traceback.extract_tb(exc.__traceback__)[-1]
    return type(exc).__name__, str(exc), frame.name, (frame.line or "").strip()


# -- inputs ---------------------------------------------------------------


def _card(kind, **extra):
    return {"type": kind, **extra}


BASES = [
    {
        "title": "Home",
        "views": [
            {
                "path": "home",
                "title": "Home",
                "icon": "mdi:home",
                "cards": [
                    _card("entities", entities=["light.a", "light.b"]),
                    _card("button", entity="switch.c"),
                    _card("markdown", content="Hello"),
                    _card("entities", entities=["light.a", "light.b"]),
                ],
                "badges": [
                    {"type": "entity", "entity": "sensor.t"},
                    {"type": "entity", "entity": "sensor.h"},
                ],
            },
            {"title": "Zwei", "cards": [_card("tile", entity="light.d")]},
        ],
    },
    {
        "views": [
            {
                "path": "sec",
                "type": "sections",
                "max_columns": 3,
                "sections": [
                    {"type": "grid", "cards": [_card("heading", heading="One"), _card("tile", entity="light.a"), _card("tile", entity="light.b")]},
                    {"type": "grid", "column_span": 2, "cards": [_card("heading", heading="Two"), _card("tile", entity="light.c")]},
                    {"type": "grid", "cards": [_card("tile", entity="light.a")]},
                ],
                "badges": [{"type": "entity", "entity": "sensor.t"}],
            },
            {"path": "other", "cards": [_card("markdown", content="x")], "badges": [{"type": "entity", "entity": "sensor.t"}]},
        ],
    },
    {"strategy": {"type": "original-states", "hide_energy": True}},
    # A stray non-dict entry in views - a known open finding (status.md),
    # kept here so its current answer is pinned, right or wrong.
    {"views": ["junk", {"cards": [_card("tile", entity="light.a")]}, {"path": "p", "cards": [_card("tile", entity="light.b")]}]},
    {
        "views": [
            {"cards": [_card("tile", entity="light.a")]},
            {"cards": [_card("tile", entity="light.a"), _card("tile", entity="light.b")]},
        ],
    },
]


def _real_storage() -> str:
    configured = os.environ.get("DASHBOARD_HISTORY_REAL_STORAGE", "")
    local = ROOT / "tests" / ".real-storage"
    if not configured and local.exists():
        for line in local.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                return line.strip()
    return configured


def real_bases() -> list[dict]:
    storage = _real_storage()
    out = []
    for path in sorted(pathlib.Path(storage).glob("lovelace.*")) if storage else []:
        try:
            config = json.loads(path.read_text(encoding="utf-8"))["data"]["config"]
        except (KeyError, ValueError, TypeError):
            continue
        if isinstance(config, dict):
            out.append(config)
    return out


def _views(config):
    return [v for v in config.get("views", []) if isinstance(v, dict)]


def _containers(config, badges=False):
    out = []
    for view in _views(config):
        if badges:
            out.append(view.setdefault("badges", []))
            continue
        if isinstance(view.get("cards"), list):
            out.append(view["cards"])
        for section in view.get("sections", []) if isinstance(view.get("sections"), list) else []:
            if isinstance(section, dict) and isinstance(section.get("cards"), list):
                out.append(section["cards"])
    return out


def _any_item(config, rng, badges=False):
    lists = [lst for lst in _containers(config, badges) if lst]
    if not lists:
        return None, None
    lst = rng.choice(lists)
    return lst, rng.randrange(len(lst))


def m_delete(config, rng, badges=False):
    lst, i = _any_item(config, rng, badges)
    if lst is not None:
        lst.pop(i)


def m_add(config, rng, badges=False):
    lists = _containers(config, badges)
    if not lists:
        return
    lst = rng.choice(lists)
    src, i = _any_item(config, rng, badges)
    if src is not None and rng.random() < 0.4:
        item = copy.deepcopy(src[i])  # an identical copy
    elif badges:
        item = {"type": "entity", "entity": f"sensor.n{rng.randrange(99)}"}
    else:
        item = _card("markdown", content=f"n{rng.randrange(99)}")
    lst.insert(rng.randrange(len(lst) + 1), item)


def m_edit(config, rng, badges=False):
    lst, i = _any_item(config, rng, badges)
    if lst is not None and isinstance(lst[i], dict):
        lst[i] = {**lst[i], "name": f"e{rng.randrange(9)}"}


def m_move(config, rng):
    src, i = _any_item(config, rng)
    if src is None:
        return
    card = src.pop(i)
    dst = rng.choice(_containers(config))
    dst.insert(rng.randrange(len(dst) + 1), card)


def _section_views(config):
    return [v for v in _views(config) if isinstance(v.get("sections"), list) and v["sections"]]


def m_swap_sections(config, rng):
    views = [v for v in _section_views(config) if len(v["sections"]) > 1]
    if views:
        s = rng.choice(views)["sections"]
        a, b = rng.sample(range(len(s)), 2)
        s[a], s[b] = s[b], s[a]


def m_section_add_remove(config, rng):
    views = _section_views(config)
    if not views:
        return
    s = rng.choice(views)["sections"]
    if rng.random() < 0.5 and s:
        s.pop(rng.randrange(len(s)))
    else:
        s.insert(rng.randrange(len(s) + 1), {"type": "grid", "cards": [_card("heading", heading=f"S{rng.randrange(9)}")]})


def m_section_setting(config, rng):
    views = _section_views(config)
    if views:
        section = rng.choice(rng.choice(views)["sections"])
        if isinstance(section, dict):
            section["column_span"] = rng.choice([1, 2, True])


def m_view_setting(config, rng):
    views = _views(config)
    if views:
        view = rng.choice(views)
        key = rng.choice(["icon", "theme", "title", "visible"])
        if key in view and rng.random() < 0.5:
            del view[key]
        else:
            view[key] = rng.choice(["mdi:a", "dark", "T", False, 1])


def m_dashboard_setting(config, rng):
    if "strategy" in config and rng.random() < 0.5:
        config["strategy"] = {**config["strategy"], "hide_energy": rng.choice([True, 1, False])}
    elif "title" in config and rng.random() < 0.5:
        del config["title"]
    else:
        config["title"] = rng.choice(["A", "B"])


def m_view_add_remove(config, rng):
    views = config.setdefault("views", [])
    if views and rng.random() < 0.5:
        views.pop(rng.randrange(len(views)))
    else:
        dicts = _views(config)
        new = copy.deepcopy(rng.choice(dicts)) if dicts and rng.random() < 0.3 else {"path": f"v{rng.randrange(9)}", "cards": []}
        views.insert(rng.randrange(len(views) + 1), new)


def m_view_path(config, rng):
    views = _views(config)
    if len(views) > 1 and rng.random() < 0.5:
        a, b = rng.sample(views, 2)
        if b.get("path") is not None:
            a["path"] = b["path"]  # a collision
    elif views:
        rng.choice(views)["path"] = f"p{rng.randrange(9)}"


def m_convert(config, rng):
    views = [v for v in _views(config) if v.get("type") != "sections"]
    if views:
        view = rng.choice(views)
        view["type"] = "sections"
        view.setdefault("sections", []).append({"type": "grid", "cards": []})


MUTATIONS = [
    m_delete, m_add, m_edit, m_move,
    lambda c, r: m_delete(c, r, badges=True),
    lambda c, r: m_add(c, r, badges=True),
    lambda c, r: m_edit(c, r, badges=True),
    m_swap_sections, m_section_add_remove, m_section_setting,
    m_view_setting, m_dashboard_setting, m_view_add_remove, m_view_path, m_convert,
]


def mutate(config, rng, times):
    out = copy.deepcopy(config)
    for _ in range(times):
        rng.choice(MUTATIONS)(out, rng)
    return out


def generated(seed: int, bases: list[dict]):
    rng = random.Random(seed)
    for _ in range(TRIPLES_PER_SEED):
        before = copy.deepcopy(rng.choice(bases))
        after = mutate(before, rng, rng.randint(1, 3))
        current = before if rng.random() < 0.1 else mutate(after, rng, rng.choice([0, 0, 1, 2]))
        yield before, after, current


def _sections(*sections):
    return {"views": [{"path": "s", "type": "sections", "sections": list(sections)}]}


def constructed():
    """Cases built on purpose: refusals the generator does not reach, and V2 against V4."""
    heading = lambda text: {"type": "heading", "heading": text}  # noqa: E731
    tile = lambda entity: {"type": "tile", "entity": entity}  # noqa: E731
    first = {"type": "grid", "cards": [heading("A"), tile("x")]}
    second = {"type": "grid", "column_span": 2, "cards": [heading("B"), tile("y")]}
    two_paths = {"views": [{"path": "a", "type": "sections", "cards": []}, {"path": "a", "type": "sections", "cards": []}]}
    yield "V2 before V4 (Astra)", {"views": [{"path": "a", "type": "masonry", "cards": []}]}, two_paths, two_paths
    yield (
        "sections not a plain list",
        _sections(first, second),
        _sections(second, first),
        {"views": [{"path": "s", "type": "sections", "sections": {"0": first}}]},
    )
    yield "sections alike", _sections(first, second), _sections(first, second, first), _sections(first, second, first)
    yield (
        "setting block gone",
        {"strategy": {"type": "x", "a": 1}},
        {"strategy": {"type": "x", "a": 2}},
        {"title": "t"},
    )
    yield (
        "only some copies back (cards)",
        {"views": [{"path": "v", "cards": [tile("x"), tile("x"), tile("y")]}]},
        {"views": [{"path": "v", "cards": [tile("y")]}]},
        {"views": [{"path": "v", "cards": [tile("x"), tile("y")]}]},
    )
    yield (
        "only some copies back (badges)",
        {"views": [{"path": "v", "cards": [], "badges": [tile("x"), tile("x"), tile("y")]}]},
        {"views": [{"path": "v", "cards": [], "badges": [tile("y")]}]},
        {"views": [{"path": "v", "cards": [], "badges": [tile("x"), tile("y")]}]},
    )
    imported = tile("k")
    imported_edited = {**tile("k"), "name": "n"}
    swapped_before = {"type": "sections", "sections": [first, second], "cards": [imported]}
    swapped_after = {"type": "sections", "sections": [second, first], "cards": [imported_edited]}
    doubled = [{"path": "d", "cards": []}, {"path": "d", "cards": []}]
    yield (
        "V2 before Q1",
        {"views": [{**swapped_before, "path": "s"}, *doubled]},
        {"views": [{**swapped_after, "path": "s"}, *doubled]},
        {"views": [{**swapped_after, "path": "s"}, *doubled]},
    )
    yield (
        "V3 before Q1",
        {"views": [swapped_before, {"cards": [tile("m")]}]},
        {"views": [swapped_after, {"cards": [tile("m")]}]},
        {"views": [swapped_after, {"cards": [tile("q")]}]},
    )
    # A section moved and edited in one save: the sections planner refuses.
    second_edited = {**second, "cards": [heading("B"), {**tile("y"), "name": "n"}]}
    yield (
        "V3 before sections",
        {"views": [{"type": "sections", "sections": [first, second]}, {"cards": [tile("k")]}]},
        {"views": [{"type": "sections", "sections": [second_edited, first]}, {"cards": [tile("k")]}]},
        {"views": [{"type": "sections", "sections": [second_edited, first]}, {"cards": [tile("m")]}]},
    )
    # Astra, plan review: the old function computed `shifted` before the
    # settings planner and raised on a view whose sections is a number.
    yield (
        "raises where it raised before",
        {"views": [{"path": "a", "title": "Before", "cards": []}]},
        {"views": [{"path": "a", "title": "After", "cards": []}]},
        {"views": [{"path": "a", "title": "Later", "cards": [], "sections": 1}]},
    )
    yield (
        "a different view at the path",
        {"views": [{"path": "a", "title": "A", "cards": []}, {"path": "b", "cards": []}]},
        {"views": [{"path": "b", "cards": []}]},
        {"views": [{"path": "a", "title": "Other", "cards": []}, {"path": "b", "cards": []}]},
    )


# -- stages, measured one at a time (once the planners exist) ------------

STAGES = ("V1", "V2", "V3", "V4", "sections", "settings", "cards", "badges", "views", "Q1")

# Pairs that cannot both refuse for one input, in the old version as in
# the new: V1 refuses only when the change changed nothing, and then no
# other stage has anything to refuse (a type change counts as a change);
# Q1 is only reached once every planner has passed. Every other pair
# must be met - and one of these showing up means the reasoning is wrong.
UNREACHABLE = {
    frozenset(pair)
    for pair in (
        ("V1", "V4"), ("V1", "sections"), ("V1", "settings"), ("V1", "cards"),
        ("V1", "badges"), ("V1", "views"), ("V1", "Q1"),
        ("sections", "Q1"), ("settings", "Q1"), ("cards", "Q1"), ("badges", "Q1"), ("views", "Q1"),
    )
}
RATIO_LIMIT = 1.10


def refusing_stages(before, after, current) -> frozenset:
    """Which stages would refuse, each asked on its own; empty if one raises."""
    try:
        return _refusing_stages(before, after, current)
    except Exception:  # an input that raises has no stages to measure
        return frozenset()


def _refusing_stages(before, after, current) -> frozenset:
    ctx = NEW_UNDO.UndoContext(before, after, current)
    out = {name for name, gate in zip(STAGES[:4], NEW_UNDO._GATES) if gate(ctx) is not None}
    planned = {}
    for kind in NEW_UNDO._CHECK_ORDER:
        result = NEW_UNDO._PLANNERS[kind](ctx)
        if isinstance(result, str):
            out.add(kind)
        else:
            planned[kind] = result
    if len(planned) == len(NEW_UNDO._PLANNERS) and NEW_UNDO._sections_meet_cards(planned) is not None:
        out.add("Q1")
    return frozenset(out)


def main() -> int:
    bases = BASES + real_bases()
    inputs = [(f"constructed: {name}", b, a, c) for name, b, a, c in constructed()]
    for seed in SEEDS:
        inputs += [(f"seed {seed}", b, a, c) for b, a, c in generated(seed, bases)]
    measure_stages = hasattr(NEW_UNDO, "UndoContext")
    diffs, templates, pairs = 0, {}, set()
    t_old = t_new = 0.0
    for number, (label, before, after, current) in enumerate(inputs):
        # Alternating who goes first: whichever runs first on an input
        # pays for warming up, and a fixed order showed as a 15 % gap
        # between two identical copies.
        if number % 2:
            new, _new_plan, took_new = outcome(NEW, before, after, current)
            old, old_plan, took_old = outcome(OLD, before, after, current)
        else:
            old, old_plan, took_old = outcome(OLD, before, after, current)
            new, _new_plan, took_new = outcome(NEW, before, after, current)
        t_old += took_old
        t_new += took_new
        if old != new:
            diffs += 1
            if diffs <= 3:
                print(f"DIFFERENCE in {label}")
        if old_plan is not None and old_plan.blocked is not None:
            template = template_of(old_plan.blocked)
            templates[template] = templates.get(template, 0) + 1
        if measure_stages:
            refusing = refusing_stages(before, after, current)
            pairs |= {frozenset(p) for p in itertools.combinations(sorted(refusing), 2)}
    print(f"base commit: {BASE_COMMIT}")
    print(f"inputs: {len(inputs)} (constructed: {len(list(constructed()))}, bases: {len(BASES)} built in + {len(bases) - len(BASES)} real, seeds: {SEEDS})")
    print(f"differences: {diffs}")
    print(f"refusal templates reached: {len(templates)} of {len(TEMPLATES)}")
    for template in TEMPLATES:
        print(f"  {templates.get(template, 0):6d}  {template}")
    if measure_stages:
        print(f"pairs of refusing stages met: {len(pairs)}")
        for a, b in itertools.combinations(STAGES, 2):
            print(f"  {'x' if frozenset((a, b)) in pairs else '.'}  {a} + {b}")
    ratio = t_new / t_old
    print(f"plan_undo time: old {t_old:.2f}s, new {t_new:.2f}s, ratio {ratio:.2f}")
    failures = []
    if diffs:
        failures.append(f"{diffs} input(s) answered differently")
    missing = [t for t in TEMPLATES if t not in templates]
    if missing:
        failures.append(f"{len(missing)} refusal template(s) never reached")
    if measure_stages:
        expected = {frozenset(p) for p in itertools.combinations(STAGES, 2)} - UNREACHABLE
        if pairs != expected:
            failures.append(
                f"pairs met are not the expected {len(expected)}: "
                f"missing {sorted(sorted(p) for p in expected - pairs)}, "
                f"unexpected {sorted(sorted(p) for p in pairs - expected)}"
            )
    if ratio > RATIO_LIMIT:
        failures.append(f"plan_undo is {ratio:.2f} times as slow, over {RATIO_LIMIT}")
    for failure in failures:
        print(f"FAIL: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
