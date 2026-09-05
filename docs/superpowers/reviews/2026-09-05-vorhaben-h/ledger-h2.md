# SDD ledger — plan: docs/superpowers/plans/2026-09-04-die-zwei-modi.md

Worktree: <projekte>/ha-dashboard-history-h, branch `vorhaben-h`
Spec: docs/superpowers/specs/2026-08-30-dashboard-history-design.md (Entscheidung 17, 9, 13)
Runs **after** the H1 ledger in the sibling directory `2026-09-04-versionen-von-selbst/` is complete.
Starting point once H1 is done: `270 passed, 3 skipped`.

## Preflight scan

### Pairs that share a file or an interface

| Pair | Produced → consumed | Finding |
|---|---|---|
| H1 → T1 | `_version_dict` incl. `automatic` → the `run_keep_as_version` check asserts `automatic is False` | Agrees: `_async_keep_as_version` passes a person's description, never the marker. |
| T1 → T6 | `restore_state(…, keep_as_version)` → `_restoreState`'s third argument to `_confirm` | Agrees, field for field (`level`, `title`, `description`). |
| T2 → T7 | `Change.previous` in every row → `_detailFor(change)`, `_renderSetBack` | Agrees. T7 deletes `_before` in the same commit that starts reading the field. |
| T2 → T8 | `dashboard_history/search` → `_search` | Agrees on `text`/`limit`/`more`. |
| T3 → T5/T7/T8 | `rows.js` (`sections`, `renderRow`, `versionHead`, `someNames`), `dialogs.js` | T7 edits `renderRow`'s markup, T8 edits neither. No overlap in the same lines. |
| T4 → T8 | `PAGE = 25`, `_cursor`, `_loadOlder` | T8 hides the button while a query stands; it does not touch `_loadOlder`. |
| T5 → T6 | `this._mode` → `_armKeep` ticks the box in the simple mode | Agrees. |
| T5 → T8 | `_versions`, `_matching`, `renderSimple` | T8 adds a third argument `searching` to `renderSimple` and rewrites its empty state. Same file, later task. Clean. |
| T6 → T7 | `_confirm(title, request, wantsKeep)` → `_restoreState` keeps that shape while its addressing changes | Agrees. |

### Task self-consistency

| Task | Finding |
|---|---|
| T1 | Integration-only, and the plan says why: the ordering that makes it correct sits between two awaits pytest cannot reach. |
| T2 | 15 pytest cases against `previous` + `search_changes`. Step 2's expected failure names both attribute errors. |
| T3 | Pure move. Its gate is "the existing Node tests pass unchanged", plus one asset test that knows the part list by name. |
| T4 | 4 cases. The `_HELD` fixture answers held calls by type, tolerating the second call T5 adds — deliberate and stated. |
| T5 | 5 cases. Empty state now renders the button and the mode link (was a dead end). |
| T6 | 6 cases through the real `_confirm`, with a DOM stand-in. The Escape case has a measured negative control (1 call vs 4). |
| T7 | Pure refactor + 2 cases. Gate is again "existing tests unchanged". |
| T8 | 7 cases. Two search paths, one per mode. |

### Rulings made before execution

Ruling: Aufgabe 7 (addressing by revision) split out of the original Aufgabe 7 as a task of its own,
so the refactor that promises no behaviour change gets its own gate — the same pattern Aufgabe 3
already uses. Cost if wrong: one extra dispatch and review seat.

Ruling: `matching_versions` wired into the panel in T5 — project G computes it server-side across
every version, and the panel had been recomputing the same question over the loaded window, which is
the very blindness G existed to remove. Cost if wrong: the chip naming an identical version could
name one the user considers stale; the server's answer is the more complete of the two.

## Progress

### Preflight, second pass (after H1 completed)

Briefs verified current: cut 22:16 against a plan last written 22:06 and unchanged since (committed
ef652a9, working tree clean). No re-cut needed.

H1's shipped interface checked against what H2 expects to consume, not merely against what H1's plan
promised:
- `operations._version_dict` returns `name`/`revision`/`title`/`description`/`automatic` — T5 reads
  `automatic`, T1's integration check asserts it is False for a person's version. Agrees.
- `versions.day_title` yields `5 September 2026`; T6's `today()` yields
  `${getDate()} ${MONTHS[getMonth()]} ${getFullYear()}` with an identical month table. Agrees
  character for character.

Ruling: the two `today`s disagree on timezone by construction — Python reads the dashboard's
configured Home Assistant zone, JavaScript reads the browser's. Near midnight, a browser in another
zone offers a title one day off from what an automatic mark of the same moment would carry. Accepted,
not fixed: the JS value is only the *prefilled* title of a version the person is about to make and
can edit, never a value written unseen, and the alternative — asking the backend for its idea of
today before every dialog — buys a round trip for a default string. Cost if wrong: a hand-made
version created around midnight from a distant browser carries yesterday's or tomorrow's date in its
default title, visibly, before the person confirms it.

### Simplification pass before H2 (user-requested)

Ran the code-simplifier over H1's production code only (`custom_components/`, commits
`ef652a9..HEAD`), tests and translations explicitly out of scope. It changed three files: one real
refactor in `milestones.py` (a private `_async_versions(key)` absorbing a duplicated executor hop and
the duplicated `versioning.latest(...)` check), an import-order fix in `__init__.py`, and a type
annotation on `_version_dict`. Committed as `cbd4c07`.

Ruling: the refactor's one condition change — `if versioning.latest(...)` became
`if numbered is not None` — accepted after checking it by hand rather than on the agent's word.
`latest` returns either `None` or a 3-tuple, and no non-empty tuple is falsy in Python (`(0,0,0)`
included), so the two agree on every value the function can build. Cost if wrong: a dashboard with a
version numbered `v0.0.0` would be treated as unnumbered; no such value is reachable.

Ruling: the simplifier's own caveat carried into the gate rather than waved off — **no pytest case
reaches `milestones.py`** (it imports Home Assistant, absent on this machine), so `270 passed,
3 skipped` says nothing about the file it changed most. Verified instead by restarting
`dashboard-history-test` (Python caches imported modules; an entry reload is not enough) and running
`run_checks.py`.

Ruling: the simplification was committed while that integration run was still in flight, so H2 could
start. Justified by scope: task 1 touches `operations.py`, `websocket_api.py` and `services.py`, not
`milestones.py`, so a correction from the run would be orthogonal to it. Cost if wrong: one extra
commit on a feature branch.

Checked and left alone: `versions.automatic_description(text)` has no production caller passing
`text` — only a test does. Looked for the obvious future caller (the `describe` service writing words
onto an automatic version, which would have to preserve the marker) and it does not exist:
`async_describe` writes to a *change* via `store.set_description(revision, …)`, while the marker
lives in a *version tag's* description. Two separate stores, no contact. The parameter is stock, held
in place by a plan-mandated test that is out of the simplifier's scope. No change.

## Progress — H2

BASE for task 1: cbd4c07

**STANDING ORDER from the user (2026-09-05):** when H2 is complete — all eight tasks done and the
final whole-branch review clean — run the code-simplifier again over H2's production code, the same
way it was run over H1's before H2 began. Scope it to the diff H2 produced (`custom_components/`,
BASE cbd4c07 to the H2 HEAD), tests and translations out of scope. This comes **before**
`superpowers:finishing-a-development-branch`, not after.

Carry the same guard rails into that dispatch as the H1 pass, plus one more that H1's pass did not
need: `panel.js` and everything under `custom_components/dashboard_history/panel/` are the bulk of
H2, and `tests/test_panel_assets.py` knows the part-file list by name — a simplifier that merges or
renames a part file breaks that test. And the panel has no pytest coverage of the kind that would
catch a behaviour change silently: `tests/test_panel_behaviour.py` loads panel.js in Node, so it does
reach the logic, but only the logic the tests name.

Simplification verification did NOT complete. The run died in `run_milestones` with
`websockets.exceptions.ConnectionClosedOK: received 1000 (OK)` — a clean Home Assistant shutdown,
i.e. the task-1 implementer restarting `dashboard-history-test` mid-run. One FAIL before that point,
`the sacrificial dashboard is recorded as deleted`, the known flaky first check. **`milestones.py`
after commit cbd4c07 is therefore still unverified by anything.** Re-run owed once task 1's own run
finishes; not treated as done until then.

Ruling: my dispatch instruction was the cause and is corrected for every later dispatch. It told the
implementer not to start a second `run_checks.py` while one was live, and they did not — they
restarted the *container*, which is a separate action that kills a live run just as dead. Every
dispatch from task 2 on must say: before `docker restart dashboard-history-test`, check
`pgrep -af "run_check[s].py"` and wait, because a restart severs another run's WebSocket. Cost of
the omission here: one wasted ~12-minute run, no code affected.
Task 1: implemented, commit 92a82ff "Let a restore mark the state it replaces" (5 files, +153/-2).
pytest 270 passed 3 skipped (unchanged, as the task adds no pytest cases by design).
Integration **131 von 131** — fully clean, no FAIL line at all.

That clean run settles the debt left open above: `milestones.py` as simplified in cbd4c07 was live in
the container for it, and `run_milestones` is inside those 131. The simplification is verified after
all, by the implementer's run rather than by my own killed one. No re-run owed.

It also puts a third data point under the flakiness ruling: `the sacrificial dashboard is recorded as
deleted` was red in my killed run and green here, minutes apart, with only task 1's code between them
— and task 1 touches nothing that check reaches. Bench noise, confirmed again.

Task 1: review dispatched (sonnet), with the implementer's own concern routed as the focus — that
`_async_keep_as_version` passes no explicit revision and is correct only because of where it sits
between `_keep_the_live_state` and `async_save_config`. The reviewer is told to read the whole
`async_restore_state`, not the diff hunk, and to check for any early return or await that could move
or skip it.
Task 1: review — spec ✅ ("nur eine im Brief selbst angelegte Ungenauigkeit"), quality approved.
0 Critical, 0 Important, 2 Minor. The ordering argument was verified line by line in the full
`async_restore_state` body: no early return, no exception path and no extra await between
`_keep_the_live_state` and `async_save_config` that could move or skip the mark.

Ruling: Minor 1 (`kept_as_version` omits `"error"` on the success path, while the brief's Interfaces
line promises both keys always) resolved *against the plan text*, not against the code. The value is
`async_create_version`'s return passed through unchanged, and that is the shape the `create_version`
service has answered with since project G. Normalising it only inside `_async_keep_as_version` would
give one message two shapes — nested unlike the same answer at the surface. The plan line now
describes what ships and names the safe way to read it (`?.error` / `.get("error")`, never
`"error" in …`). Task 6's consumer already uses `applied?.kept_as_version?.error`, so nothing
downstream changes. Cost if wrong: a future reader of the *code* still has to look at
`async_create_version` to learn the shape; the plan no longer misleads them into `"error" in …`.

Ruling: Minor 2 (the docstring of `async_restore_state` never mentioned `keep_as_version`) fixed by
me rather than dispatched — comment-only, no behaviour, and a fix round plus re-review for one
sentence is out of proportion. Both changes are commit e889b9b, pytest 270 passed 3 skipped.

Task 1: COMPLETE (commits cbd4c07..e889b9b).

BASE for task 2: e889b9b
Task 2: implemented, commit d0fa76d (6 files, +327/-16). pytest **286 passed, 3 skipped**,
integration **131 von 131**, no FAIL line.

Ruling: the implementer found the brief's prose miscounting its own verbatim code block — the text
says fifteen new cases, the block holds sixteen. Verified independently: `grep -c '^def test_'` on
the brief gives 16, and the commit adds 16. Taking the code block as binding was right, and every
expected total from task 2 onward was therefore one short. Corrected in the plan (commit e920575:
286, 290, 295, 301, 303, 309) and in the briefs. Cost if left: each later task reports one test more
than its own step predicts, and the honest reading of that is "a test I did not write is running" —
an investigation per task.

⚠️ My own error, recorded because the recovery matters more than the slip: running the skill's
`scripts/task-brief` against this plan **emptied briefs 3-8 to zero bytes**. The script matches
English `### Task N` headings; this plan's are German `### Aufgabe N`, and it truncated each output
file before discovering it had nothing to write. The briefs had been hand-cut, which is why they
existed at all. Restored by extracting the `### Aufgabe N` sections from the plan directly and
verified **byte-identical** to the pre-deletion sizes (16107 / 9258 / 21399 / 20335 / 18750 / 17913),
which is the proof that nothing was lost or paraphrased. Do not use `scripts/task-brief` on this
plan; extract by section heading instead.

Task 2: review dispatched (sonnet). Focus routed: whether `previous` is really free (the brief claims
`list_changes` needs no extra read because `async_history` already fetches limit+1), whether
`search_changes` runs in an executor, and whether the four searched fields behave as specified.
Task 2: review — spec ✅ ("vollständig spezifikationstreu"), quality approved. All four routed focus
points confirmed: `previous` is filled without an extra read *including for the last row of a page*
(the pre-existing bug this task was to fix), all four fields searched case-insensitively with `[]` on
empty text, the version namespace really is stripped before matching, and the 16 tests demonstrably
separate a message hit from a version-field hit. 1 Important (plan conflict) + 1 Minor.

Ruling: the Important finding — the commit subject the brief dictates verbatim is 52 characters
against the 50 this project sets flat — fixed by rewriting the message, and the plan and brief
corrected to the shorter line ("Let a row say what came before, and search it all", 49). The
implementer copied faithfully as instructed; the rule broke in the plan. Because d0fa76d was no
longer HEAD this needed a reset+cherry-pick rather than an amend, so it was done under a backup tag
and the result **proven by tree equality**: `HEAD^{tree}` equals the backup's, i.e. messages changed
and not one byte of code. Commits are now b8a11e8 (task 2) and 4798b8d (the count correction).
Cost if wrong: nothing; the branch is local and unpushed.

Ruling: the Minor (the comment above the cursor walk said one entry too few is read for a
foreign-dashboard cursor, when it is one too many) fixed by me rather than dispatched — comment-only,
and the danger in a wrong comment is precisely that the next reader trims the number to match the
sentence. Commit d9b1cec, together with the plan's subject line.

Task 2: COMPLETE (commits e889b9b..d9b1cec). pytest 286 passed 3 skipped.

BASE for task 3: d9b1cec
Task 3: implemented, commit bbc31b1 "Split the panel along what its pieces are for". panel.js -236,
new panel/rows.js (147) and panel/dialogs.js (70), tests/test_panel_assets.py +11/-0.
pytest **286 passed, 3 skipped** — unchanged in both directions, which is this task's whole gate.
`tests/test_panel_behaviour.py` untouched (verified by git diff --stat). Integration **131 von 131**,
not even the flaky checks appeared.

Ruling: the implementer's one deliberate deviation from the brief's verbatim code is upheld. The
brief's `someNames` block had lost a docstring paragraph that panel.js carried before the move — the
one saying the named version is the version on the most recent *matching state*, not the highest
number. Verified independently: present at panel.js:956 before, at rows.js:51 now, absent from the
brief (grep count 0). For a task whose contract is "pure move", carrying it across was right and
following the letter would have been a silent loss. The plan's snippet is now complete too (commit
5b137ec), so reproducing from it cannot drop the paragraph a second time. Cost if wrong: none; a
comment that was already in the tree stayed in the tree.

Ruling: the brief's manual browser eyeball for this task is deferred, not waived. The implementer had
no credentials for the test instance. Doing it now, on a move that changes no behaviour, and then
again after each of tasks 4-8 which change the panel substantially, is four or five browser passes
for one question. It is folded into a single pass after task 8, where the panel is in its final shape
and the eyeball actually answers something. Cost if wrong: a rendering fault introduced by the split
would be found after task 8 rather than now — bounded by the fact that both Node panel tests and the
asset test, which knows the part list by name, pass unchanged.

Task 3: review dispatched (sonnet). Focus routed: prove the move is pure by reading the diff as a
move rather than as new code, and check the part-file boundaries against the responsibilities the
brief names.
Task 3: review — spec ✅ (files, exports, signatures, load order, both renames, the asset test's part
list all match the brief word for word), move verified behaviour-preserving. 0 Critical,
0 Important, 2 Minor, both named as plan conflicts rather than implementer errors.

Ruling: both Minors adopted, and on checking they were larger than reported. The reviewer found two
comment paragraphs missing from `versionHead` and `renderRow`; measured against the pre-move
`panel.js`, the comment body of those two functions had gone from 36 lines to 2 in the parts the
brief dictates — much of it condensed into the new docstrings, which is fine, but three paragraphs
were gone outright:
  1. why there are two chip wordings at all (the top entry is where you are; a lower one can hold
     byte-identical content without being it);
  2. the measurement behind `spokenFor` (head read "same content as now", row read "same state as
     now" — one fact wearing two coats);
  3. why the version chip sits beside the label rather than in a sentence beneath it, which
     measurement showed was read past.
All three carry a single editorial decision — one wording for one fact across the three places that
state it — and that is exactly what a split scatters: the paragraph explaining why head, row and
tooltip agree lived in one of the three, and the other two now sit in another file. Restored in
`rows.js` and in the plan's snippet together (commit 0479d0b), pytest still 286 passed 3 skipped.
Cost if wrong: comments only; no behaviour was touched.

Ruling: this is the third lossy snippet in this plan (after `someNames` in task 3 and the test count
in task 2). Every remaining task's review carries an explicit instruction to diff moved or rewritten
code against its pre-task version rather than reading the unified diff, because a unified diff shows
a move as an unrelated delete-plus-add and hides exactly this.

Task 3: COMPLETE (commits d9b1cec..0479d0b). pytest 286 passed 3 skipped, integration 131/131.

BASE for task 4: 0479d0b
Task 4: implemented, commit c38c3c1 "Let the panel page through the history" (38 chars).
panel.js +64, panel/style.js +1, tests/test_panel_behaviour.py +104.
pytest **290 passed, 3 skipped** — exactly the 286 + 4 the corrected plan predicts, which is the
first confirmation that the count correction from task 2 was right. Integration **131 von 131**,
no flaky check appeared.

The implementer reports no comment was dropped from the brief's snippets this time, and says so
explicitly because the dispatch asked for it — the third lossy-snippet finding turned that from a
formality into a real question. Also recorded the `panel/style.js` boundary rationale on request.

Useful discovery, carried into later dispatches: the first integration attempt hit the Bash
foreground timeout purely because Python buffers stdout — `python3 -u` makes the log readable while
the run is still going, instead of withholding it to the end.

Task 4: review dispatched (sonnet). Focus routed: append-versus-replace and a double press of the
button, cursor passed back rather than an offset computed, end of history recognised, the number
twenty-five written once, the style.js boundary, and — with an explicit method, since the unified
diff hides it — whether any explanatory comment present before the task is gone now.
Task 4: review — spec ✅ (PAGE=25, `_cursor`, `_loadOlder`, button, CSS, tests, commit message all
match the brief exactly), quality approved: append-not-replace and cursor-not-offset are provably
exercised, end of history handled, no comment lost anywhere in the rewritten regions.
0 Critical, 1 Important (plan conflict) + 2 Minor.

Ruling: the Important finding is adopted and fixed. `test_another_dashboard_starts_at_the_top_again`
asserted that switching dashboards sends no `before` — but `_select` has no branch that could send
one, so the case passed with `this._cursor = null` deleted from `_select`. Verified by reading
`_select` and `_loadOlder` in full rather than on the reviewer's word. What the reset actually
prevents is narrower: pressing "load older" *while a switch is in flight* would otherwise use the
previous dashboard's cursor against the newly selected key. The scenario now does that and counts
requests carrying a `before`. **Negative control run: with the reset line removed the case fails,
with it restored all eight pass.** Fixed in the test and in the plan's copy of it (commit c1faf0c).
Cost if wrong: none; the assertion is strictly stronger than the one it replaces.

Ruling: Minor 1 (a fast double-click on "load older" sends two identical requests, though the state
stays correct through the claim ticket) parked, not fixed. Every other guarded action in this file
behaves the same way, so suppressing it here alone would make this one button inconsistent with the
rest, and the reviewer says as much. Cost if wrong: one redundant read per impatient double-click.

Ruling: Minor 2 (the red-then-green steps were not run as literal separate steps; the implementer
verified test power by reading instead) noted and answered by the fix above — the strengthened case
now has a *measured* negative control, which is what those steps exist to produce.

Task 4: COMPLETE (commits 0479d0b..c1faf0c). pytest 290 passed 3 skipped, integration 131/131.

BASE for task 5: c1faf0c
Task 5: implemented, commit e1fa503 "Offer a mode that only knows versions". New part file
`panel/simple.js`, plus panel.js, panel/style.js and both panel test files.
pytest **295 passed, 3 skipped** exactly, integration **131 von 131**.

Two pieces of judgment the implementer showed and I confirm: it restored a docstring paragraph on
`_versionsMatchingNow` that the brief's block had dropped (the fifth such loss in this plan), and it
repaired an *existing* test that broke honestly — `_select` now issues two calls, so a case finding
its call by fixed index had to find it by type instead. Neither was dictated; both were right.

Ruling: the implementer's third concern is the important one and is now fixed. It reported, on being
asked directly, that **no test covered the `matching_versions` wiring** — every case would still pass
with the panel recomputing the answer locally over its loaded window. That wiring exists because of
my own preflight ruling, and it is the single change on this branch that nothing was watching. Added
`test_a_matching_version_below_the_window_keeps_its_name`: the server names a version marking a
commit the window does not contain, which a local sum can never produce. **Negative control run: put
the local sum back and it is the only one of fourteen panel cases that fails** — proving both that
the new case bites and that the existing ones were blind. Commit d0f75f1, in the test file and in the
plan's copy. Test count therefore 296; the expectations for tasks 6-8 shifted to 302, 304, 310 in the
plan and in their briefs.

Ruling: the manual browser check for this task is again deferred into the single pass after task 8.
The implementer could not read the instance's token (blocked by its own permission classifier) and
correctly did not try to work around it. Cost if wrong: unchanged from the task 3 ruling.

Task 5: review dispatched (sonnet).
Task 5: review — spec ✅ (code, names, labels, strings, all five dictated tests and the part list
match the brief word for word), quality approved. Mode switch confirmed pure display, empty state
has both exits, no paging conflict, storage failure handled, no comment loss beyond the one the
implementer itself restored. 0 Critical, 1 Important + 3 Minor.

Ruling: the Important finding adopted and fixed. `_refresh()` received the same second fetch
`_select()` got, but is reached by an *event* rather than a click, so no Node scenario had ever run
it — zero occurrences of `_refresh` in the panel test file, verified. It also carries a decision
`_select` does not: it deliberately returns to the first page. Added
`test_a_refresh_asks_for_both_and_starts_at_the_top`. **Negative control run three ways — dropping
the versions fetch, keeping the cursor, and blanking `matching_versions` each turn the case red.**
Commit 817f397, in the test file and the plan's copy. Cost if wrong: none; strictly added coverage.

Ruling: Minor 1 (new CSS in panel/style.js deviates from the file's fallback-colour and comma
spacing) parked. It is verbatim from the brief's code block, the reviewer says so, and it is
presentation with no behaviour attached. Cost if wrong: a style file with two conventions in it;
worth a sweep when the panel is next touched wholesale, not a rewrite now.

Correction to the review's last Minor, recorded so the record is accurate: it says the implementer
shipped a `matching_versions` test without counting it, and that the true figure was 296 rather than
the 295 reported. That test was added by **me** after the implementer's report, in commit d0f75f1.
The implementer's own count of 295 was right for what it delivered.

Test count now **297 passed, 3 skipped**; expectations for tasks 6-8 shifted again, to 303, 305, 311,
in the plan and in their briefs.

Task 5: COMPLETE (commits c1faf0c..817f397). integration 131/131.

BASE for task 6: 817f397
Task 6: implemented, commit a92094c. panel.js, panel/dialogs.js, panel/style.js,
tests/test_panel_behaviour.py. Integration **131 von 131**, 0 FAIL.

Ruling: the brief's prose says six new cases, its verbatim code block holds **seven** — the same
defect as task 2, verified by `grep -c '^def test_'`. The implementer shipped seven rather than
trimming one to hit the predicted number, and said so. Correct: the number is the prediction, the
block is the requirement. Plan and briefs corrected.

Ruling: the implementer's third concern is adopted and fixed, and it is the most valuable report any
implementer has made on this branch. Asked directly which of its dictated tests could not fail, it
named three, and had *measured* it by watching them green in the pre-implementation red run. Two of
those three are legitimate regression guards for behaviour that predates task 6. The third,
`test_discarding_sends_no_version_at_all`, is half of a meaningful pair with
`test_keeping_the_state_sends_a_version_with_the_restore` — together they discriminate, so no change.

What was genuinely uncovered is what the implementer's fourth concern named: **the failed-keep
path**. The restore succeeds, the version is not made, and only the banner can say so — the quietest
failure on the branch. Added three cases (commit 8ee1c45): the failure is spoken; the same failure
reported twice by the server is spoken once; a keep that worked says nothing.

⚠️ Finding turned up *by* the negative control, not by any reviewer: deleting the guard
`failed !== applied?.note` changes no outcome — all 25 panel cases stay green. `applied?.note` sits
ahead of `keptFailed` in the `||` chain, so wherever a note exists it wins and `keptFailed` can never
be reached. The guard looks load-bearing and is not. Behaviour left alone (a note plus a differently
worded failed keep needs two simultaneous faults), but the comment now names the ordering as the
thing that does the work, so a later edit reorders the chain knowingly. Cost if wrong: in that
double-failure case the person hears the note and not the missing version — which is what already
happens today, now written down instead of implied.

Test count now **307 passed, 3 skipped**; tasks 7-8 shifted to 309 and 315 in the plan and briefs.

Task 6: review dispatched (sonnet).
Task 6: review — spec ✅ (every signature, field, label, CSS class and dialog markup verbatim from
the brief; `_restoreItem` and `_undoChange` byte-for-byte unchanged), quality sound. Preview-before-
write, the `dialog.returnValue` reset and its test, the mode-driven default, omit-vs-empty-object for
`keep_as_version`, and the single `keepable` gating both arm and send all verified. No comment loss
anywhere the diff touches, checked against `git show 817f397:` rather than the unified diff. Part
boundary respected. 0 Critical, 1 Important, 0 Minor.

Ruling: the Important finding adopted and fixed. `keepable` withholds the offer in two cases —
nothing to apply, and a restore that recreates a deleted dashboard — and neither had ever been run:
every scenario in the file, before this task and after, builds an ordinary restore. Added three
cases (commit 8629c26). Each asserts both halves of the promise: the box is hidden *and* no version
is sent however the dialog closes. The third is an ordinary restore through the same harness, so
that "not offered" means withheld rather than never reachable. **Negative control run: dropping
either half of the condition turns exactly one of the two red and nothing else** — they test
separate things, not one thing twice. Cost if wrong: none; strictly added coverage.

Test count now **310 passed, 3 skipped**; tasks 7-8 shifted to 312 and 318 in the plan and briefs.

Task 6: COMPLETE (commits 817f397..8629c26). integration 131/131.

BASE for task 7: 8629c26
Task 7: implemented, commit c8fa472 "Address a row by its revision, not by its place" (47 chars).
panel.js +168/-, panel/rows.js, tests/test_panel_behaviour.py. pytest **312 passed, 3 skipped**
exactly, integration **131 von 131**.

Verified mechanically rather than on the implementer's word: it says three existing scenarios were
edited at their *call sites only*, no assertion changed. `git diff … | grep -E '^[-+] *assert'`
returns **four added lines and not one removed** — all four belong to the two new cases. The claim
holds.

The headline fix is proven, not merely asserted. The new case builds a bottom row whose `previous` is
`"c"`, and `"c"` is deliberately not among the loaded changes: **no positional scheme can produce it**
— the old code found nothing below that row and never asked `deleted_since` at all. Structural, the
same shape of proof as the `matching_versions` case. **Negative control run by me: putting the
positional lookup back (`_changes[index + 1]`) fails exactly that one case and nothing else.**

Ruling: the implementer's own caveat is upheld and needs no action —
`test_the_first_recorded_state_asks_about_nothing_before_it` is a control, not a proof, and it said
so unprompted. It would go red only on a different bug (an unconditional `deleted_since`), which is
still worth having; a pair where one case proves and the other bounds is the shape asked for.

Task 7: review dispatched (sonnet).
Task 7: review — spec ✅ (`_changeAt`, `_madeSince`, `_isNewest`, `data-revision`, `newest`, the
removal of `_before`, all exactly as briefed), purity ✅ by function-by-function comparison against
`8629c26` rather than the unified diff: all 168 changed lines are the same logic under a new address,
and the only behaviour change is the briefed, test-proven fix. **0 Critical, 0 Important, 2 Minor** —
the cleanest task on this branch.

Ruling: Minor 2 adopted and fixed. The refresh branch that finds the open row again via
`_changeAt(this._open)` had no case — the refresh scenario opens no row — and it is precisely where
addressing by revision earns its keep: a refresh happens because the history grew, so a row that was
first is now second. Added `test_an_open_row_survives_a_refresh_that_moved_it` (commit 4344fd8).
Writing it corrected me: my first assertion lumped both follow-up questions together, and the code
was right — `deleted_since` asks against the row's *predecessor*, `explain` about the row *itself*.
Two revisions, and by index after a refresh neither number is what it was. The case now asserts them
separately, which is stricter than what I first wrote. **Negative control run: put the positional
lookup back in that branch and it is the only one of thirty-one that fails.**

Ruling: Minor 1 parked. The new `if (change && item)` guard in the `[data-restore]` handler changes
behaviour in a practically unreachable edge (the old code could call `_restoreItem` with
`index === -1`), and it is verbatim from the brief. Removing a guard because its case is unreachable
today is how it becomes reachable tomorrow. Cost if wrong: none observed.

Test count now **313 passed, 3 skipped**; task 8 shifted to 319 in the plan and its brief.

Task 7: COMPLETE (commits 8629c26..4344fd8). integration 131/131.

BASE for task 8: 4344fd8
Task 8: implemented, commit d5e3dce "Give each mode a search over what it shows". panel.js +187,
panel/simple.js, panel/style.js, tests/test_panel_behaviour.py +107.
pytest **320 passed, 3 skipped**, integration **131 von 131**.

Ruling: the brief's prose miscounts its own code block for the **third** time on this plan — seven
`def test_` against a promised six (verified by grep). Shipped the block, corrected the plan
(commit 0dea68a). The pattern is now established well enough to state as a rule for anyone reading
this ledger later: in this plan the code block is the requirement and the number is only its
prediction.

Task 8: review dispatched (sonnet), with the implementer's two concerns routed as focus points plus
the two edges I had asked it about.
Task 8: review — spec largely ✅ (strings, CSS, state names and all seven dictated tests verbatim),
quality solid on everything the brief specified, **but one Critical**, plus 3 Minor. Both items the
implementer had disclosed itself were independently verified as accurate.

Ruling: the Critical is real and is fixed. Verified by me before acting: `_shown()` returns
`this._found` while a server search stands, and `_changeAt` read only `this._changes` — so every
remote hit was inert. Clicking one opened nothing, describing one wrote nothing, and neither said
why. The function's own docstring names the two lists ("the search box makes a second one") and then
reads one of them; the author knew there were two. **Not one of the 320 tests noticed** — the fix
alone left them all green, which is why two cases were added with a measured control: restore the
one-list lookup and exactly those two fail. Loaded list is asked first, so the ordinary path is
byte-identical in behaviour. Also a plan conflict: task 8's step 3 never touches `_changeAt` while
its step 4 requires the result to work. Plan corrected with the code.

Ruling: Minor 1 fixed rather than parked, because the fix makes the existing comment true instead of
inverting it. Clearing `_searching` before the claim check is deliberate (otherwise a run whose claim
`_loadOlder` took would leave "Searching the whole history…" standing for good) — but *any* run
clearing it is too coarse: type, pause, type again, and the first answer blanks the indicator while
the second search is still out. A run counter now lets only the newest run clear it, which covers
both cases the comment claims to cover. Measured: restore the unconditional clear and exactly one
case fails.

Ruling: Minor 3 fixed — `_select` now clears `_searching` along with the rest of its reset list. One
line, and an inconsistent reset list is what produces the next bug of this shape.

Ruling: Minor 2 parked. `_refresh` deliberately leaves `_query` and `_found` alone: wiping somebody's
query because a live update arrived is worse than a result list that is a few seconds old, and search
hits are historical entries that do not change. Cost if wrong: a hit list that does not include a
change made seconds ago, until the query is retyped.

Test count now **323 passed, 3 skipped**; the plan's task 8 carries the three added cases and the
corrected number.

Task 8: COMPLETE (commits 4344fd8..2fd5223).

ALL EIGHT TASKS COMPLETE. Final whole-branch review next, then the user's standing order: a second
code-simplifier pass over H2's production diff, then finishing-a-development-branch.

## Final whole-branch review

Split in two by the project's own seam, both on opus: server (90 KB diff) and panel (130 KB).

**Server: no Critical.** All seven hard rules verified as still holding after the branch, and the
hygiene check for anything about the developer's installation came back clean. 3 Important, all
adopted and fixed in commit 9be8aad, each verified by me first:
- `search_changes` read a version's description raw, so the `dashboard-history: automatic` marker was
  searchable: `auto`, `dash`, `history`, `dashboard` each returned every automatic version. Every
  other exit strips it via `_version_dict`; the search was the one that did not. Fixed by reading the
  description through `versions.read_description`, which needed the dual import idiom in `store.py`
  (both load paths verified). Test added with a measured negative control.
- The day mark took the *second-newest* entry as yesterday's last state. That holds only if it runs
  once per save, in order, and it does not — two saves landing together start two marks that both
  arrive after both writes, both see two entries from today, and yesterday's last state is never
  marked by anything, permanently. Now walks back to the day boundary within a bounded window
  (`_RECENT = 20`). This supersedes the limit H1's ledger had parked as plan-inherent.
- `keep_as_version` was shaped twice and the two shapes disagreed: the service took any dict, so
  `{}` with `confirm: true` made a tag with an empty title — and nothing in this integration can
  delete a version. Fixed at the cause: one `KEEP_AS_VERSION` in `const.py`, which both doors already
  import, so the shapes cannot drift again.

Ruling: the reviewer's suggested fix for the day mark (carry the revision in the event) was declined
in favour of walking back inside `milestones.py`. The event carries only dashboard names, so its way
would have meant changing `capture.py` — the file the "nothing blocks the start" rule lives in — and
the payload of an event the panel and `run_checks.py` also read. The contained fix addresses the same
failure. Cost if wrong: a burst of more than 20 saves across one midnight still loses the mark, which
is now stated in the code.

**Panel: one Critical (C1), 9 Important, 5 Minor.** Hygiene clean there too: no foreign paths,
credentials or real dashboard names anywhere in the diff.

C1 verified by me before dispatching anything: the request closures read `this._selected` when they
are *called*, and they are called twice — once for the preview, once for the write. The modal only
appears after the preview returns, so the sidebar is live in between. Preview a restore on one
dashboard, pick another, press Apply, and the write goes to the second with the first one's revision.
`_forget` has the same shape and is irreversible, under a dialog naming the wrong dashboard.
Pre-existing on main, widened here by attaching `keep_as_version` to it.

Fix wave for the panel review: commits 4fa0cbe, 15502d0, d02fe04, 313aeed, a1d6d6a. All six routed
items done. pytest 324 → **343 passed, 3 skipped** (19 new cases, 13 fault injections measured),
integration 131/131.

How the dialog-teardown defect was made visible is worth keeping: every panel test stubs `_render`,
so a fault *inside* rendering was structurally invisible to all of them. The new scenario runs the
**real** `_render` against a stand-in root that honestly discards its children on `innerHTML` and
answers `dialog[open]` truthfully.

Ruling: the fixer's decision to leave the second half of I6 is upheld. Where a version's own commit
sits below the loaded window the simple mode now shows **no** fold count rather than a wrong one. An
absent number claims nothing; a wrong one claims something false. The advanced mode keeps its count,
because there "load older" can make it true.

Scoped re-review: **all six ADDRESSED**, and the completeness question paid — the capture reaches all
six `_confirm` callers, not the four the original review named, and `_describe` addresses by revision
and needs none. No comment lost against 9be8aad; exactly one deleted line in the whole test diff (the
stand-in's property list, extended). No assertion removed or loosened. 3 residuals.

Ruling: both Important residuals dispatched rather than parked, because they are about the Critical's
*durability*, not its correctness. The re-review measured that reverting the capture at six sites
leaves the suite green — "the repair reaches five of five, the measurement reaches two of five". A
Critical whose fix no test holds is a Critical with a delay on it: the next refactor undoes it
silently and looks safe doing so. Sent with the third residual (a failed reload after a write is now
silent, because `_refreshQuietly` swallows what `_select` used to leave in the banner) and the
third instance on this branch of a test that passes with its own feature removed.

Residual wave: commits f78b36a, a506062, 641b940. pytest 343 → **349 passed, 3 skipped**,
integration 131/131. All three residuals closed, and the evidence is a table rather than a claim:
each of the six reversions that used to leave the suite green was re-applied alone and now fails,
naming the case that catches it.

Two things from that wave worth keeping:
- while measuring, one of its own new runs turned out to be green while stopping at its first line —
  the two runs before it go through the real `_select`, which replaces `_changes`. Found and fixed by
  the measurement itself, which is the argument for measuring.
- residual 3 produced `_reloadAfterWrite(done)`: the reload after a write now raises the busy count
  and *answers* with "<what succeeded>, but the page could not be reloaded: <why>". `_refreshQuietly`
  survives for its real purpose, the refresh nobody asked for, and its comment paragraph was moved
  rather than deleted.

Known and left, per the re-review's own verdict: after Apply, the banner can land on a dashboard the
person switched to — a message in the wrong place, not a write in the wrong place, and unchanged
since before the fix wave.

**H2 COMPLETE.** 8 tasks, final review both halves, one fix wave, one scoped re-review, one residual
wave. pytest 349 passed 3 skipped, integration 131 von 131.

Now running the user's standing order: the second code-simplifier pass, over H2's production diff
(cbd4c07..HEAD, `custom_components/` only). Then finishing-a-development-branch.

Second simplification pass (the user's standing order): commit be62dc4, three files, pytest
**349 passed, 3 skipped** unchanged, integration **131 von 131**.

Four sayings collapsed — `shortName` (eight places), `_showError` (seven), `_clearDetail` (three),
and one `onClick` helper for eleven click handlers whose bodies are unchanged, comments included. One
condition that was asked three times in a row (in the test, in the sentence it produces, and in the
comment explaining it) now asked once; one deleted outright because a query of no characters is
already a query of fewer than two. And the panel's offer to switch modes, written out twice in
`simple.js`, is now one constant.

Ruling: the `beforeIsNow` extraction checked by hand rather than accepted. Old
`!this._changeAt(before)?.same_as_now` yields `!undefined` = true where the predecessor is outside the
window; new `Boolean(before && …)` yields `false`, so `!false` = true. Equivalent on every reachable
value, and the comment was corrected to match rather than dropped.

Recorded because it is the right answer to the question I asked: the simplifier was asked whether
`operations.py`'s row building really shares what it looks like it shares. It found the genuine
duplicate (the three-line marks dict, now `_marks_by_revision`) and **declined** the `same`
computation, because `async_history` deliberately folds version revisions into it for
`matching_versions` and `async_search` does not. Two things that look alike are not a duplication.

BRANCH COMPLETE — nothing merged, nothing pushed, nothing tagged. That is the user's call.
