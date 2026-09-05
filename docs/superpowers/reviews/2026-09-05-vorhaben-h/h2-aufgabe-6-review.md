# Review: Task 6 — Der Rücksprung fragt nach dem jetzigen Stand

Commit reviewed: `a92094c` (`817f397..a92094c`), read-only in
`<projekte>/ha-dashboard-history-h` (branch `vorhaben-h`,
HEAD is `8ee1c45`, one commit ahead of the reviewed commit — task 7 already
landed on top; this review looks only at `a92094c`'s own diff).

## Verdict A — Spec compliance

**Compliant.** Every signature, field name, label string, CSS class and the
dialog markup block in the diff matches `task-6-brief.md` verbatim: `_confirm(title,
request, wantsKeep = false)`, `request(confirm, keep)`, `_armKeep(show)`,
`_keepChoice()`, `today()`/`MONTHS`, the `.keep`/`.keepbox`/`.keeptitle`
markup between `.body` and `.actions`, the `.keep`/`.keep label` CSS rules,
and the exact wording "Kept either way — without a name it is only findable
in the advanced view." `_restoreItem` and `_undoChange` are byte-for-byte
unchanged, confirmed by diffing `git show 817f397:panel.js` against the
current file outside the `_confirm`/`_restoreState`/new-methods region.

One point worth noting explicitly: `_keepChoice()` sends only `{level,
title}`, never `description`. This matches the brief's own code block
exactly, and matches the server contract in
`custom_components/dashboard_history/websocket_api.py` (`restore_state`
schema, ~line 118-133), where `title` is `vol.Required` and `description`
is `vol.Optional(..., default="")` — so its absence is not a gap, it is the
server's own optionality being used as intended.

## Verdict B — Code quality

**Sound.** The five load-bearing behaviours hold up under direct code
reading and under the new tests: preview always precedes any write
(`request(false, null)` before `request(true, keep)`, `panel.js:541,617`);
`dialog.returnValue = ""` is reset before every `showModal()`
(`panel.js:604`), and `test_a_dialog_dismissed_without_a_button_writes_nothing`
genuinely depends on that reset (traced by hand: removing the reset line
would leave the stand-in dialog's `returnValue` at `"apply"` from the prior
press, and the Escape-dismissed third call would then also write —
confirmed by reading `node().close()` in the test harness, which only
overwrites `returnValue` when a defined value is passed); the checkbox
default is driven by `this._mode === "simple"` alone (`panel.js:686`); the
`keep_as_version` field is spread in only when `keep` is truthy
(`_restoreState`, using `...(keep ? {keep_as_version: keep} : {})`), so a
clear checkbox produces no field at all — not an empty object; and
`keepable` (`panel.js:600-602`) is the single boolean gating both
`_armKeep(keepable)` and `const keep = keepable ? this._keepChoice() : null`
(`panel.js:603,612`), so a suppressed offer structurally cannot reach
`request(true, keep)` with a non-null `keep` — there is no second code path
that could disagree with the tick box's visibility.

Comment-preservation check (per instruction 6, compared directly against
`git show 817f397:panel.js`/`dialogs.js`/`style.js`, not the unified diff):
no explanatory comment was dropped anywhere the diff touches. Every
existing comment in `_confirm`, `_restoreItem`/`_undoChange`, and the
`.confirm` dialog markup survives untouched; the diff is purely additive in
every hunk.

Part boundary: the new `.keep` markup lives in `panel/dialogs.js`, not
`panel.js` — respected as required.

### Findings

- **Important** — `custom_components/dashboard_history/panel.js:595-603`
  (`keepable` computation): no test exercises `keepable` being suppressed
  by `nothingToDo` or by `preview.creates_dashboard` in combination with an
  actual `wantsKeep = true` call (i.e. via `_restoreState`). The `_KEEP`
  scenario in `tests/test_panel_behaviour.py` only ever hits the "ordinary
  restore" preview shape (`applied: false, preview: "-a\n+b", ...`); no
  scenario gives `_restoreState` a preview with `note` and no diff
  (already-identical) or with `creates_dashboard: true`. Confirmed by
  grepping the pre- and post-task-6 test file for `creates_dashboard` /
  `nothingToDo` / "already identical" / "This recreates" — none of those
  appear anywhere in `tests/test_panel_behaviour.py`, before or after this
  task. The logic reads correct on inspection (verified above), but this
  is exactly the interaction review item 5 asks to check, and right now it
  is checked only by reading the code, not by a test that would go red if
  someone loosened the `&&` in `panel.js:600-602`. Not brief-mandated (the
  brief's own `_KEEP` scenario doesn't cover it either), so this is not a
  deviation by the implementer — it is a real residual gap worth a
  follow-up test, most cheaply added as one more `press()`-style case with
  a preview carrying `creates_dashboard: true` or `note` without a diff.

No other findings. Nothing Critical or Minor beyond the one Important item
above.

## Test run (read-only, for verification)

- `python3 -m pytest tests/test_panel_behaviour.py -v` → 25 passed (18
  pre-existing + 7 from this task; matches the report's "22 passed" for
  the state right after task 6, before task 7 added 3 more).
- `python3 -m pytest tests/ -q` → 307 passed, 3 skipped at current HEAD
  (`8ee1c45`); 304 passed is what the report correctly measured at
  `a92094c` itself, 3 short of the current count because task 7's own
  tests are not yet present at that commit.
- `git log -1 --format=%B a92094c`: subject "Ask what becomes of the state
  being replaced" (45 chars, imperative, capitalised), blank line, body
  wrapped at 72, ends with the required `Co-Authored-By:` trailer. Compliant.
