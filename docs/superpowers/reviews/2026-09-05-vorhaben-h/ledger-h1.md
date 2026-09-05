# SDD ledger — plan: docs/superpowers/plans/2026-09-04-versionen-von-selbst.md

Worktree: <projekte>/ha-dashboard-history-h, branch `vorhaben-h`
Spec: docs/superpowers/specs/2026-08-30-dashboard-history-design.md (Entscheidung 17)
Baseline pytest: `256 passed, 3 skipped` (no real .storage in this worktree — deliberate)
Plans committed: ef652a9

Second plan to follow in the same worktree:
docs/superpowers/plans/2026-09-04-die-zwei-modi.md (8 tasks, own ledger)

## Preflight scan

### Pairs that share a file or an interface

| Pair | Produced → consumed | Finding |
|---|---|---|
| T1 → T2 | `day_title`, `automatic_description` → `Milestones._async_make`; `read_description` → `operations._version_dict` | Names and arities agree. Clean. |
| T1 → T3 | `same_day(one, other, zone)` → `_async_mark_day` | Agrees. Clean. |
| T2 → T3 | `Milestones.__init__`, `_async_make(key, level, change)` → `async_arm`/`_async_mark_day` | Agrees; T3 appends to the same class. Clean. |
| T2 → T3 | `__init__.py`: T2 creates `milestones`, T3 arms it after the floor block and disarms in unload | Sequential edits to adjacent lines. Clean. |
| T2 → T3 | `run_checks.py`: T3 appends to `run_milestones` | Clean after the correction that moved `_versions_settled` into T3. |
| T2 → T4 | `entry_id(access)` → `daily_versions_switch` | Agrees. Clean. |
| T3 → T4 | `const.OPTION_DAILY_VERSIONS` → `config_flow` schema | Agrees. Clean. |
| T4 → T3 | `entry.options[daily_versions]` → `_async_mark_day` reads it per save | Agrees; no update listener by design. Clean. |
| H1 → H2 | `_version_dict` incl. `automatic`; `day_title` format | H2 T1/T2/T5 consume exactly these; `today()` in H2 builds the same string. Clean. |

### Task self-consistency

| Task | Finding |
|---|---|
| T1 | 12 tests against 6 new functions; Schritt 2 says twelve failures — counted, correct. `local_day` is exported and reached only through `same_day`; covered indirectly, not directly. Noted, not a defect. |
| T2 | Tests are integration-only, and the plan says why (the module imports Home Assistant). Anchors verified against the tree today. |
| T3 | **Schritt 2 is green on purpose** and the plan says so in as many words. Carried into the dispatch so the reviewer does not read it as a missing red. |
| T4 | Two pytest cases + one integration check; `config_flow.py` is replaced whole. `OptionsFlow.__init__` trap documented and measured. |

### Rulings made before execution

Ruling: worktree placed beside the repository, not in `.worktrees/` — both `docker/compose.yaml` and `run_checks.py` resolve their config directory through the repository's parent, so a nested worktree would point at a directory that does not exist. Cost if wrong: none observed; the container was recreated and mounts verified.

Ruling: `EnterWorktree` not used, `git worktree add ... HEAD` instead — the native tool branches from `origin/main` by default and local `main` is 72 commits ahead of it, so a native worktree would have been missing all of project G. Cost if wrong: none; the branch was verified to sit on the local HEAD.

Ruling: five plan defects corrected before execution rather than left for the fix loop — stale `_by_number` anchor in T2 (moved to `versions.py` by commit 9e1558e this evening), duplicate import instruction in T1, `_versions_settled` defined a task before its use, a `run_milestones` docstring that its own T4 would falsify, and machine-dependent test counts. Cost if wrong: the plan text now differs from what was reviewed by the author; every change is in commit ef652a9 and readable there.

## Progress
Task 1: complete (commits ef652a9..d349f38, review clean) — pytest 268 passed, 3 skipped
Task 1: minor (deferred): stdlib imports in tests/test_versions.py sit after the local `versions` import — plan-mandated, the brief dictates the append position.
Task 1: minor (deferred): the two DST cases would not catch a naive seconds-difference implementation; the shipped implementation compares `.date()` and is correct regardless. Plan-mandated test text.

Integration baseline (before any task, commit ef652a9, container re-pointed at this worktree):
**117 of 118 checks passed.** The one failure is `the sacrificial dashboard is recorded as deleted`
in `run_forget` — the newest entry was still `dh-forget-check: first recorded state` where a deletion
was expected. Not caused by anything on this branch: task 1 touched only `versions.py`, which
`run_forget` never reaches, and the failure was already there on the first run after the container
was recreated. Every task dispatch carries this so nobody chases it. Re-checked at the final review.

Ruling: Gemini's H1 review, finding 1, adopted — a dashboard created while Home Assistant is running
has no floor, so its first automatic version would be a day mark at patch level, and
`candidates(key, [])["patch"]` is `v0.0.1` (measured). The next start would find a version, skip the
dashboard, and strand it on the v0.0.x track for good. `_async_mark_day` now makes the first
automatic version of a dashboard at major level. Plan corrected in f1cb906 before task 3 was
dispatched. Cost if wrong: a dashboard whose first mark arises from a day boundary gets v1.0.0
rather than v0.0.1 — the same number the floor would have given it.

Ruling: Gemini's H1 review, finding 2, adopted as one sentence of prose — the English date in the
version title is the project's language rule, not a slip from the German example in the spec.
Cost if wrong: none, documentation only.

Ruling: Gemini's H1 review, finding 3, declined as code and recorded as a named limit instead —
`async_create_entry(data=user_input)` replaces the options wholesale, which is harmless while there
is exactly one required option with a default. Merging options that do not exist is stock on
speculation, and the file is touched again the day a second one arrives. Cost if wrong: whoever adds
option two without reading the note silently drops option one; the note sits three lines above the
code that would do it.

Ruling: the baseline's one failing check (`the sacrificial dashboard is recorded as deleted`) is
bench flakiness, not a defect. Evidence: it went green in task 2's first run and red again in its
second, while two card checks did the opposite — and neither block is touched by any code this
branch has changed. Both are the first checks in the file, running against a grown bench of real
dashboards that `pick_target` chooses dynamically. Cost if wrong: a real regression in card
restoration would be read as noise; the final whole-branch review re-checks it, and `restore.py`
and `analyze.py` are untouched by H1 in git.
Task 2: complete (commits f1cb906..e260a4c, review clean) — pytest 268 passed, 3 skipped; integration 121/123 then 122/123, the two failures alternating between runs (see the flakiness ruling above); the three new milestone checks green in both, idempotence probe included.
Task 2: minor (deferred): `from .milestones import Milestones` breaks the otherwise alphabetical import order in `__init__.py` — plan-mandated, and the project runs no import-order linter.
Task 2: minor (deferred): `Event` and `callback` are imported in milestones.py but unused until task 3 wires the listener — plan-mandated, and it resolves itself in the very next task.

Task 3: integration run fully green — **124 of 124 checks passed**, no failure at all. That includes
all three checks that had been alternating between runs, which settles the flakiness ruling above:
they are bench noise, not a regression. The day-mark block passed, `a second change on the same day
adds no further version` included.
Task 3: review — spec ✅, quality approved, 1 Important + 2 Minor.
Task 3: Ruling: the Important finding is adopted against the plan's text. The brief says
`self._hass.async_create_task(...)`; a task started that way outlives `async_disarm()`, and across a
config-entry reload the surviving task holds the *old* instance's lock while the new instance holds a
new one — reopening exactly the double-mark the lock exists to prevent. Fix: `entry.async_create_
background_task(...)`, which Home Assistant cancels when the entry unloads. Public API, the entry is
already held, one line. Cost if wrong: a mark interrupted at unload may not be written — and a
missing mark is the failure this module is explicitly allowed to have ("a version that could not be
made is a mark that is missing"), whereas a duplicate tag is not.
Task 3: minor (deferred): two saves landing within milliseconds across a midnight can lose the day
mark entirely — `_async_mark_day` reads the newest two entries at execution time, so the state that
should have been marked slides out of the two-entry window. Plan-inherent, not an implementation
fault. Belongs in the plan's "benannte Grenzen" section; added there when H1 closes.
Task 3: minor (deferred): the lock is instance-wide rather than per dashboard — plan-mandated,
harmless under asyncio.
Task 3: ⚠️ resolved by me: the success path of `_async_mark_day` has no automated coverage. That is
not a gap this task opened — the plan names it as a limit in "Zwei benannte Grenzen": no API can
backdate a commit, and `milestones.py` imports Home Assistant so pytest cannot reach it. The pure
part (`versions.same_day`) is covered by twelve pytest cases from task 1. No fix.
Task 3: fix round 1/5 (1 addressed, 0 open — task now bound to the config entry; commits cc3af0b..7d37e9c)
Task 3: complete (commits e260a4c..7d37e9c, review clean) — pytest 268 passed, 3 skipped; integration 124/124

Task 4: the day mark proved itself live. The session ran across midnight (2026-09-04 → 09-05), and
`dh-floor-check` came back holding `['v1.0.1', 'v1.0.0']` with v1.0.1 titled "4 September 2026" — a
real day mark for the day before, made by the mechanism task 3 built. That is exactly the path the
task 3 review flagged as having no automated coverage anywhere.
Task 4: **defect found in task 2's own check** — `run_milestones` asserts `names == ["v1.0.0"]`,
which is false on any bench that lives across a midnight. It is the check that is wrong, not the
code. Fixed in a follow-up before the final review.
Task 4: complete (commits 7d37e9c..b3f8950, review clean) — pytest 270 passed, 3 skipped; integration 126/128, the two failures both adjudicated above.
Task 4: minor (deferred): the two pytest cases assert existence and a substring only — plan-mandated wording.
Task 4: minor (deferred): step 2's second failing-probe was not run separately because config_flow.py was already being replaced; covered by the step 4 run and disclosed in the report.
Task 4: ⚠️ resolved by me: whether `self.config_entry` really raises inside `OptionsFlow.__init__` cannot be checked from the diff (no homeassistant package on this machine). The integration run answers it operationally — `run_daily_switch` drives the real flow against HA 2026.8.3 and both directions are accepted. No fix.

Final whole-branch review: no Critical, 2 Important + 5 Minor. Fix wave 4f997f6 addressed all four
findings I routed into it; the scoped re-review verdicted every one ADRESSIERT.
Ruling: the re-review's one residual — a 56-character commit subject against the project's 50 —
amended by me rather than dispatched. It changes no code, the diff was already verified, and a
dispatch plus re-review for a subject line is out of proportion. Cost if wrong: the amended commit
differs from the one the re-review read, in its message only.
Ruling: H1's workspace is kept rather than deleted at this point. Project H2 runs next on the same
branch, and these rulings have to survive to the handover. Cost if wrong: a directory lingering in
gitignored scratch.
H1 COMPLETE — 10 commits (ef652a9..cbd4c07), pytest 270 passed 3 skipped.
*(Corrected on 2026-09-05: the count said 9 and left out cbd4c07,
the simplification pass, which is part of the range.)*
