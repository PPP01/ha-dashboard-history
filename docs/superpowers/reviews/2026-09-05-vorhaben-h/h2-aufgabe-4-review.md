# Task 4 review — Paging: "Load older" and twenty-five

Reviewed read-only in `<projekte>/ha-dashboard-history-h`,
branch `vorhaben-h`, commit `c38c3c1` against parent `0479d0b`.

## Verdict A — Spec compliance

The diff implements every element the brief specifies, with its exact
names, numbers and strings, and nothing extra or renamed: `PAGE = 25`
(one definition, used at all three `history` call sites — `_select`,
`_refresh`, `_loadOlder` — with no other `25` introduced anywhere and
the server-side manual-call default staying `50` in `websocket_api.py`,
`services.py`, `store.py`, `operations.py`, untouched); `this._cursor =
null` in the constructor with the brief's comment verbatim; `_select`
resetting `_cursor` and passing `limit: PAGE`; `_refresh` passing
`limit: PAGE` and deliberately resetting `_cursor` from
`next_cursor` on every refresh; `async _loadOlder()` placed directly
after `_select`, guarding on `!this._cursor || !this._selected`,
claiming the same `"changes"` ticket slot, appending via `.concat(...)`
rather than replacing, and updating `_cursor`; the `_renderMain()` tail
appending the `.older` / `data-older` button block exactly as given,
conditioned on `this._cursor`; the `[data-older]` click wiring in
`_render()`; and the `.older` CSS rule appended verbatim to
`panel/style.js` before its closing backtick. The four new tests were
added to `tests/test_panel_behaviour.py` verbatim from the brief. The
commit message matches the brief's template exactly (verified against
`git log -1 --format=%B c38c3c1`: subject "Let the panel page through
the history", 38 characters, imperative, capitalised; blank line; body
wrapped at ≤72 chars; correct `Co-Authored-By` trailer). No spec
element is missing, extra, or renamed.

## Verdict B — Code quality

Correct and faithful in the load-bearing paths — appending (not
replacing) is provably exercised by
`test_older_entries_are_appended_and_not_substituted`, cursor-not-offset
paging is provably exercised by
`test_the_next_page_is_asked_for_by_cursor`, and end-of-history is
provably exercised by `test_the_end_of_the_history_is_remembered`; the
double-press race is correctly handled by the existing per-slot ticket
mechanism (`_claim("changes")`), so a page can never be appended twice
or written under the wrong dashboard; no explanatory comment present in
the pre-task file was dropped (checked directly, not via the unified
diff, across every rewritten region: the `PAGE` constant block, the
`_refresh` and `_select` bodies, `_renderMain`'s tail, and the
`[data-forget]`/`[data-refresh]` wiring block — all clean insertions
around untouched comments); and the new `.older` CSS rule is correctly
scoped to `panel/style.js`, consistent with every other element's rule
living there rather than in `panel.js`. One of the four new tests,
however, does not actually prove what it claims (see finding 1) — this
originates in the brief's own verbatim test code, so it is reported
separately as a conflict with the plan rather than an implementation
defect. `python3 -m pytest tests/ -q` reproduced independently:
`290 passed, 3 skipped`, exact match to the brief's expectation.

## Findings

1. **Important — conflict with the plan.**
   `tests/test_panel_behaviour.py`, the `_PAGING_RESET` scenario feeding
   `test_another_dashboard_starts_at_the_top_again` (brief lines
   91–123, carried verbatim into the test file). The test does not
   prove the invariant its own comment claims ("A cursor from one
   dashboard handed to another would ask for the entries after a
   commit that dashboard never had"). `_select` (panel.js line ~354)
   never includes a `before` field in its own `history` call regardless
   of `this._cursor`'s value — it only ever sends `{ dashboard, limit:
   PAGE }`. Combined with the mocked reply always returning
   `next_cursor: null`, all three assertions (`between == "x"`,
   `"before" not in askedFor`, `after == ["y"]`) would pass identically
   even if the reset line `this._cursor = null;` in `_select` (panel.js
   line 353) were deleted outright. The real race that line guards
   against — `_loadOlder()` firing with the *new* dashboard's key but
   the *old* dashboard's stale cursor, in the window between
   `this._selected = key` and the new dashboard's `history` answer
   arriving — is never triggered in the test; nobody calls
   `_loadOlder()` during that gap. Since this test code is verbatim
   from the brief, the defect sits in the plan, not in the
   implementation, which copied it faithfully as instructed.

2. **Minor.** `panel.js` `_loadOlder` (lines 378–395). Pressing "Load
   older changes" twice before the first answer returns fires two
   identical WS `history` requests (both with the same `before` value,
   since `this._cursor` is only updated after a request resolves). The
   ticket mechanism correctly prevents any state corruption — only the
   second (current) claim is allowed to write into `_changes` — but the
   duplicate network round-trip itself is not suppressed. This matches
   the pre-existing pattern for every other guarded action in the file
   (`_select`, `_refresh` are equally unguarded against a fast repeat
   click), so it is house style rather than a new inconsistency, but is
   worth naming since double-press was flagged as the classic risk for
   this task.

3. **Minor — process note.** The brief's Step 1/Step 2 (write the four
   tests first, run them, and confirm the specific failure
   `el._loadOlder is not a function` / `_cursor` `undefined`) was not
   executed as a literal separate red run; per the implementer's own
   report, implementation and tests were written together and the
   tests' power to fail was instead argued for by reading the code.
   The delivered tests and passing suite are correct regardless (see
   Finding 1's caveat on one of them), so this affects process rigor
   rather than the delivered artifact.

No Critical findings.
