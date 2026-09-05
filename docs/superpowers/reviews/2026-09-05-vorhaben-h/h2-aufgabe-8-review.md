# Review: Task 8 — Das Suchfeld

Reviewed read-only in worktree `ha-dashboard-history-h`, branch `vorhaben-h`,
commit `d5e3dce` (parent `4344fd8`).

## Verdict A — Spec compliance

Mostly yes: field text, CSS, state names, method names, and the message
strings under the box (`_searchNote`) all match the brief's code blocks
essentially verbatim, and all seven prescribed tests pass unmodified
(`320 passed, 3 skipped`, matching the already-adjudicated six-vs-seven
discrepancy). But the brief's own Step 4 manual-check script promises a
capability ("an expanded hit must have its comparison ... for the first
time on a row from nowhere") that the shipped code cannot deliver — see
Critical finding 1. That is as much a gap in the brief (it never asks to
touch `_changeAt`) as in the implementation, and is named as a plan
conflict below as well as a code defect.

## Verdict B — Code quality

Sound in the parts the brief specified verbatim (debounce, ticket-based
staleness, cursor/mode/dashboard-switch resets, flat list + hidden "Load
older" while searching, no comments lost). But it ships one confirmed,
reproducible, user-facing break — a remote search hit cannot be opened or
annotated at all — plus a smaller, previously-undisclosed note-flicker
race that goes a step beyond what the implementer's own report described.

## Findings

- **Critical** — `custom_components/dashboard_history/panel.js:599-601`
  (`_changeAt`) and its callers `_expand` (line 622-624) and `_describe`
  (line 855-857) look up a revision only in `this._changes`, never in
  `this._found`. Every remote search hit is by construction absent from
  `_changes` (the local step already covers anything that *is* loaded),
  so clicking a row drawn from `_found` — the entire point of the
  second, server-side search stage — silently does nothing: no error, no
  detail, `_open` stays `null`. Confirmed by direct execution: with
  `el._found = [{revision:"remote1", ...}]` and no matching entry in
  `_changes`, `el._expand("remote1")` leaves `el._open === null`. The
  pencil/describe button fails the same way. `operations.py`'s
  `_rendered()` (line 141-164) already carries a `previous` field
  specifically "said rather than left to be worked out from the row
  below ... in a search result it is not the predecessor at all" —
  i.e. the backend was built to support exactly this row-from-a-search
  interaction, and task 7's revision-based addressing (its own comment:
  "the search box makes a second one") was introduced for the same
  reason. None of the seven new tests exercise `_expand`/`_describe` on
  a `_found`-only revision, so this shipped green. **Also a conflict
  with the plan**: the brief's Step 3 code blocks never touch
  `_changeAt`, yet Step 4's manual script explicitly requires a
  search-result row to expand and show its comparison "for the first
  time on a row from nowhere" — the brief specifies code that cannot
  satisfy its own acceptance check.

- **Minor** — `custom_components/dashboard_history/panel.js:502-528`
  (`_search`): `this._searching = false` is set unconditionally before
  the `mine()` check, which the inline comment justifies only for the
  case where the "changes" slot was reclaimed by something that is not
  a search (`_select`, `_loadOlder`). It also fires when the slot was
  reclaimed by a *later search*: confirmed by execution (two escalating
  searches A then C; A's answer arrives after C has already claimed the
  slot and set `_searching = true`) — A's stale continuation resets
  `_searching` to `false` while C is still genuinely in flight, and
  `_searchNote()` briefly renders nothing at all (not "Searching the
  whole history…", not a count) until C resolves. No wrong rows result
  — `_shown()` never reads `_searching` — so this goes beyond, but does
  not contradict, the implementer's own disclosed "self-healing" account
  of the note; it is a second, milder instance of the same shared-flag
  design, cosmetic and self-correcting.

- **Minor** — `custom_components/dashboard_history/panel.js` `_refresh()`
  (around line 300-340) does not touch `_query`/`_found`/`_searching`.
  A live-update refresh (or the reload button) while a search stands
  replaces `_changes` with a fresh first page but leaves a stale
  `_found` from the remote step in place; if the local step still finds
  nothing after the refresh, `_shown()` falls back to that pre-refresh
  `_found`. Not incorrect data (the listed commits are real), just not
  re-verified against the freshest history. The brief does not ask for
  this case, so this is an observation rather than a spec violation.

- **Minor** — `custom_components/dashboard_history/panel.js` `_select`
  (line 425-448) resets `_query`, `_found`, `_moreFound` and the pending
  timer but not `_searching`. Harmless in practice (`_searchNote()`
  returns `""` immediately whenever `_query` is empty, which `_select`
  guarantees), and the value is forced back to `false` once the
  superseded request's own continuation runs — but leaving it out reads
  as an oversight next to the otherwise-complete reset list.

## Verified as accurate (implementer's own disclosures, not re-litigated)

- `test_picking_another_dashboard_drops_the_search`'s `found is None`
  half: confirmed by reading the sequence — the preceding
  `_search("autumn")` call (mode already switched to "simple") nulls
  `_found` synchronously at the top of `_search` before returning early,
  so `_found` is already `null` when `_select("other")` runs; only the
  `query == ""` half exercises `_select`'s own reset. Accurate.
- The cross-query "Searching the whole history…" staleness: confirmed by
  execution that it is confined to the note text and heals itself once
  the newer request resolves — no wrong rows and no rows from an
  untyped query appear on screen, because `_shown()` decides purely from
  `_query`/`_localMatches()`/`_found` and never from `_searching`.
  Accurate as far as it goes; see the related but distinct race noted
  above as Minor.

## Other checks performed, no issues found

- Cursor (`_cursor`) is untouched by `_search`/`_shown`; clearing the box
  returns exactly `this._changes` with the existing cursor and "Load
  older" button intact. Reachable only outside the search branch of
  `_renderMain`, so it cannot be pressed while a query stands.
- No predecessor, neighbour or section is derived from a position within
  the flat search list: `_isNewest`, `_matchingElsewhere` and
  `_renderSetBack`'s "before" lookup all key off `this._changes[0]` /
  `_changeAt` / `change.previous`, never off an index into `_shown()`.
- Comment-by-comment comparison of `panel.js` and
  `panel/simple.js` before (`4344fd8`) vs after: no explanatory comment
  was dropped. The `simple.js` rewrite keeps the "button and the way
  out come *with* the sentence" comment verbatim, just relocated into
  the new ternary's else-branch.
- `tests/test_panel_assets.py` untouched (`git diff --stat` empty for
  that path across the range).
- Commit message (`git log -1 --format=%B d5e3dce`): imperative subject
  under 50 characters, blank line, body wrapped at 72, correct
  `Co-Authored-By` trailer.
- `python3 -m pytest tests/ -q` → `320 passed, 3 skipped` (independently
  re-run).
- Server-side `search` WS schema (`services.py`) matches the frontend's
  `_call("search", { dashboard, text, limit: 100 })` field names exactly.
