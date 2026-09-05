# Final review — server half of `vorhaben-h`

Read-only review of `.superpowers/sdd/2026-09-04-die-zwei-modi/final-server.diff`
(`main..HEAD`, 33 commits, 18 files) in the worktree
`<projekte>/ha-dashboard-history-h`. Nothing was edited and no
writing git command was run. `python3 -m pytest tests/ -q` on this branch:
**323 passed, 3 skipped**.

Verdict: **mergeable after three fixes.** No Critical findings. The hard rules
all hold; the numbering and the paging arithmetic are correct; the two gaps that
matter are a leaked internal marker in the search and a day mark that can be
lost.

---

## Hard rules — verified after the branch, not before

| Rule | Result |
|---|---|
| No system call to `git` | Holds. `grep -rn "subprocess\|os.system\|'git'"` over `custom_components/` and `tests/integration/run_checks.py` returns nothing. |
| No intercepting/replacing HA internals | Holds. The only registration is `websocket_api.async_register_command` (`websocket_api.py:211`), the supported API. No `setattr`, no wrapping of core objects. `config_flow.py` uses the documented `async_get_options_flow`/`OptionsFlow` shape. |
| Nothing blocks HA's start | Holds in substance. `__init__.py:44-56` guards `async_lay_the_floor` in its own `try`, separate from the recorder's, and `milestones.py` catches at every level (`async_lay_the_floor`, `_async_floor_for`, `_async_mark_day`). See finding **M3** for a setup-*duration* remark that is not a rule violation. |
| `yaml_io.py`, `analyze.py`, `restore.py`, `versions.py` import no Home Assistant | Holds. `grep -n homeassistant` over the four returns nothing. `versions.py` gained only `datetime`/`date`/`tzinfo`; the `tzinfo` is passed in by the caller (`milestones._async_make` reads `dt_util.DEFAULT_TIME_ZONE` at call time), so the HA dependency stays on the HA side of the line. `tests/test_versions.py` exercises the new day logic in plain pytest, DST both ways. |
| Blocking work in an executor | Holds. `store.search_changes` — the longest read the tool has — is reached only through `hass.async_add_executor_job` (`operations.py:406`). Same for `list_versions`, `list_changes`, `create_version`, `_same_as_live` on every new path. `milestones` does no git work on the event loop: `_handle_recorded` is a `@callback` that only spawns a task, and the task's first git touch is behind an executor hop. |
| Nothing writes a dashboard state without a preview | Holds. `keep_as_version` is evaluated at `operations.py:570-583`, *after* the `if not confirm:` return at `operations.py:535`. It writes a tag, not a state, and tags are the named exception. The automatic versions write tags only. |
| Only vanished things are restored | Untouched by this branch. |
| Nothing about the developer's own installation | Holds. Scanned the whole diff for private IPs, `/home/…`, `C:\…`, host names, tokens and long hex strings: nothing. The new bench checks build their own dashboards (`dh-floor-check`, `dh-keep-check`); `run_checks.py` keeps base URL, config path and token behind environment variables, as before. |

## The four things I was told to look hardest at

**1. Concurrency and lifetime — clean.** `_marking` is taken before the version
list is read and released only after the tag is written
(`milestones.py:236-277`), so the "already marked" check and the write are one
section; a second event for the same key finds the tag and returns. Tasks are
bound to the config entry (`entry.async_create_background_task`), so HA cancels
and awaits them during unload before the new instance is built — the old lock
cannot outlive its instance. `async_unload_entry` disarms before stopping the
recorder, and there is no `await` between the `hass.data.pop` and the disarm.
`_async_mark_day` catches `Exception`, not `BaseException`, so cancellation
propagates rather than being swallowed. Underneath it all `store.create_version`
still holds its own threading lock and refuses a colliding name, so even a lost
asyncio lock could not produce two tags with one name. **I found no way to get a
duplicate tag and no way to lose the lock.**

**2. The automatic numbering — correct, including the trap.** `_async_versions`
(`milestones.py:118-136`) deliberately does *not* read "has a version" off
`list_versions`; it measures against `versioning.latest`, whose `_NUMBERS` regex
(`versions.py:26`) accepts only three plain numbers with no leading zeros and no
suffix. A dashboard whose only tag is `heizung/wichtig` or `v2.0.0-beta`
therefore counts as unnumbered and gets `major` → `v1.0.0`, not `v0.0.1`. The
same guard is repeated on the runtime path: `_async_mark_day` picks
`"patch" if numbered is not None else "major"` (`milestones.py:274`), which is
what saves a dashboard created while HA was running. The floor and the day mark
cannot collide on one state — the `any(v.revision == previous.revision …)` check
at `milestones.py:264` covers the case where the day boundary lands on the state
the floor already marked.

**3. The search — in an executor, walks once, limit bounds the result.** One
`search_changes` per query (`operations.py:406`); the full walk happens inside it
exactly once; the `limit + 1` / `break` pair gives an honest `more`. What it
searches matches the plan's four things. Two remarks below (**I1**, **M4**).

**4. `previous` — the claim holds and the last row is real.** Verified
empirically on a throwaway repository: pages of three over ten commits give
`[(9,8),(8,7),(7,6)] [(6,5),(5,4),(4,3)] [(3,2),(2,1),(1,0)] [(0,None)]` — every
last-row predecessor is the first row of the next page, and only the genuinely
oldest change answers `None`. A cursor belonging to another dashboard behaves as
documented. The cost is exactly one extra walk entry (`max_entries = limit + 1`,
or `+2` with a cursor), never an extra read call.

---

# Findings

## Critical

**None.** I looked specifically for a duplicate tag, a lost lock, a `v0.0.x`
floor, a search outside an executor, a `previous` of `None` at a page edge, a
write without a preview, and installation details in the diff. None of them are
there.

## Important

### I1 — The internal `automatic` marker is searchable, so ordinary words match every automatic version
`custom_components/dashboard_history/store.py:782-789`

`search_changes` joins `version.description` **raw**. For a version made by
`milestones`, that string is literally `dashboard-history: automatic`
(`versions.py:AUTOMATIC`, written as the tag body by
`store._create_version:263`). Everywhere else the marker is stripped before it
leaves the module — `operations._version_dict:131` calls
`versioning.read_description` precisely so that "a list that prints its own
bookkeeping is one nobody trusts" (`tests/test_versions.py`,
`test_the_marker_is_never_shown_to_anybody`). The search is the one place that
did not get the treatment.

Reproduced against a throwaway repository holding two changes and one automatic
`home/v1.0.0` on the older one:

| needle | hits |
|---|---|
| `automatic` | the tagged change |
| `dashboard-history` | the tagged change |
| `dashboard` | the tagged change |
| `history` | the tagged change |
| `auto` | the tagged change |

Concrete failure: with daily versions on (the default), a month of use leaves
~30 automatic versions per dashboard. A person types `auto` — or `dash`, or
`hist` — into the search box and gets back thirty states with no visible reason
why any of them matched, because the matching text is exactly the string the
panel is forbidden to show. The plan (`2026-09-04-die-zwei-modi.md`, point 2)
lists four things the search covers; this is a fifth that nobody asked for.

Fix is one line: feed `versioning.read_description(version.description)[0]` into
`words` instead of `version.description`. `versions.py` is HA-free and `store.py`
already lives beside it, so the import costs nothing. Worth a test alongside
`test_a_search_finds_a_state_by_the_description_of_a_version_on_it`.

### I2 — A day mark is lost when two changes land before the marking task reads
`custom_components/dashboard_history/milestones.py:243-247` (the `list_changes(key, 2)` call)

The event tells the task *which dashboard* changed but not *which revision*
(`capture._announce:256-259` fires `{"dashboards": …, "reason": …}`), so
`_async_mark_day` re-derives the boundary from "the newest two, right now".

Sequence:

1. Monday's last save is commit **A**.
2. Tuesday, a save produces **B**. `_announce` fires; `_handle_recorded` creates
   the background task. Its first `await` is the executor hop at line 243, so it
   suspends before reading anything.
3. Still Tuesday, milliseconds later, a second save produces **C**. The
   recorder's `_writing` lock serialises the *commits*, not the marking tasks.
4. The task for B finally runs `list_changes(key, 2)` and gets `[C, B]`.
   `same_day(B, C)` is true, so it returns. The task for C reads the same pair
   and returns too.

**A** — Monday's last state — is never marked, and no later save can mark it:
the boundary has left the newest-two window for good. On an installation where
the simple mode of decision 17 shows nothing but versions, a missing day is a day
that does not exist.

Two saves within milliseconds is not exotic: the panel's own restore path writes
one snapshot and then one state, and a card drag in the Lovelace editor followed
immediately by a second one produces the same shape. The window is narrow but the
loss is permanent and silent (nothing is logged — the function returns from the
`same_day` branch).

Fix: carry the revision. `capture._async_write` already has `revisions` running
in parallel with `touched`; announcing the pairs and having `_async_mark_day`
work from the announced revision's own predecessor (`store.previous_change`, which
already exists and is already tested) removes the re-derivation entirely.
A cheaper patch is to walk back from the newest until the local day changes, but
that reads more and still guesses.

### I3 — The service lets `keep_as_version` create a permanent, untitled version
`custom_components/dashboard_history/services.py:105` vs.
`custom_components/dashboard_history/websocket_api.py:117-129`

The WebSocket command shapes the field properly — `vol.Required("title")` inside
a nested schema. The service registers the same field as
`vol.Optional("keep_as_version"): vol.Any(None, dict)`, which accepts any dict at
all, and `_async_keep_as_version` then falls back with
`wanted.get("title") or ""` (`operations.py:502`).

Concrete: calling

```yaml
service: dashboard_history.restore_state
data:
  dashboard: home
  revision: <a revision>
  confirm: true
  keep_as_version: {}
```

creates a real annotated tag whose title and description are both empty. In the
simple mode a version is presented by its title, so it lands in the list as a
blank row indistinguishable from any other blank row — and **there is no way to
remove it**: `grep -rn "delete_version\|remove_version" custom_components/`
returns nothing, and `store._marked_commit`'s docstring says so in as many words
("a version, unlike a description, has nothing that deletes it again").

The sibling service `create_version` gets this right —
`vol.Required("title"): cv.string` (`services.py:172`). The two ways in should be
fenced by the same line, which is the stated principle in
`operations.async_create_version`'s own docstring ("Refused here rather than in
the panel, so the service is fenced by the same line").

Fix: give the service the same nested schema the WebSocket command uses, or at
minimum reject an empty title in `_async_keep_as_version` the way an unknown
level is rejected (`{"created": None, "error": …}`).

## Minor

### M1 — The stated reason for arming after the floor is stale, and the ordering costs the startup pass its day marks
`custom_components/dashboard_history/__init__.py:53-56`,
`custom_components/dashboard_history/milestones.py:172-190`

`async_arm`'s docstring says the order exists because "on a dashboard with none
the first automatic version would be `v0.0.1` rather than `v1.0.1`". That is no
longer the operative safeguard: `_async_mark_day` picks `major` itself when
`numbered is None` (`milestones.py:274`, added by `1a0a509`/`eb5b16e`). The
comment now explains a protection that is doubled elsewhere.

The ordering's real cost is not mentioned. `capture.async_start()` announces its
opening pass synchronously, before `async_setup_entry` reaches `async_arm()`, so
anything that pass records is invisible to the day marker. Sequence: HA is down
overnight; `.storage/lovelace.dashboard_x` is edited by hand or by a backup
restore; HA starts on Tuesday; the opening pass commits the change and announces
it to nobody. Monday's last state is never marked, and Tuesday's later saves see
`[Tue, Tue]` and return. Same for a save made during the ~20 s opening pass — a
window the recorder deliberately keeps its listener open for
(`capture.async_start:72-88`), so the save *is* recorded, just never marked.

Fixing **I2** by carrying the revision would let the arm move ahead of the floor
safely and close this at the same time.

### M2 — `async_search` reads the tag list twice per query
`custom_components/dashboard_history/operations.py:404-408`

The `asyncio.gather` runs `store.search_changes` and `store.list_versions`
concurrently, but `search_changes` opens with `self.list_versions(key)` of its
own (`store.py:773-775`). Every search therefore does two full tag scans in two
executor threads against the same repository. Harmless (both are read-only, and
`_repo()` opens fresh handles), but on the bench's 146 versions it is twice the
work for one answer, and the plan's "keine einzige zusätzliche Leseoperation"
(point 3) was a claim about `previous`, not about this. `search_changes` could
return the marks it already built, or `async_search` could pass the versions in.

### M3 — `async_lay_the_floor` costs one full tag scan per dashboard on every start
`custom_components/dashboard_history/milestones.py:74-116`

The pass is idempotent by construction, which is the right call — but its cost is
paid every start, not only the first. For each dashboard it runs
`_async_versions` (a whole-repository tag scan filtered by key), and for each one
that needs a floor `async_create_version` runs a third scan
(`operations.py:744`). With the design record's 146 versions and a dozen
dashboards that is a dozen full scans, appended to the ~20 s the recorder's
opening pass already takes, all inside the awaited `async_setup_entry`. Nothing
blocks the event loop — every scan is an executor hop, so the hard rule holds —
but HA will start logging *"Setup of dashboard_history is taking over 10
seconds"*, and a reload (which `run_checks.reload_entry` performs, timeout 300)
pays it again. One `list_versions(None)` grouped by key would collapse the whole
pass to a single scan.

### M4 — The search's limit bounds the result, not the work
`custom_components/dashboard_history/store.py:779-793`

`search_changes` calls `list_changes(key, None)`, which materialises a `Change`
for **every** commit touching this dashboard — plus a full `descriptions()` note
pass — before the first comparison is made. The `break` at `limit` then only
stops the scan of an already-built list. The docstring is honest that the walk is
unbounded and deliberate; what it does not say is that the memory is unbounded
too, and that the walk covers the whole repository's commits (every dashboard's),
filtered by path. Noting it rather than asking for a change: a generator form of
`list_changes` would fix both, and that is a bigger change than this branch
should carry.

### M5 — `search.limit` does not prefill in Developer Tools
`custom_components/dashboard_history/services.yaml` (the `search:` block)

The field carries `example: 50` where every other numeric field in the file
carries `default: 50` — `history.limit` two blocks above is the direct
comparison. The voluptuous schema does default to 50 (`services.py:143`), so the
behaviour is right; only the form is empty where the neighbouring form is
prefilled. One word.

---

## Things I checked and found correct — recorded so they are not re-checked

- **Every new field appears in every answer that should carry it.** `automatic`
  reaches the panel through `async_versions` (as `{**_version_dict(v),
  "same_as_now": …}`), through `async_history`'s per-row `versions`, through
  `async_history`'s `matching_versions`, and through `async_search`'s per-row
  `versions` — all four via the single `_version_dict`, which is exactly the
  point of that helper. `previous` reaches both row-producing answers via the
  single `_rendered`.
- **`strings.json` and `translations/en.json` are byte-identical** and both carry
  the new `options.step.init` block with `data` and `data_description`;
  `tests/test_integration_files.py` now guards the pair and the "nothing is
  deleted either way" sentence.
- **`search` is registered as an admin service** like every other
  (`async_register_admin_service`, `services.py:186`) and the WebSocket command
  inherits `@websocket_api.require_admin` from `_command`. The 2026-09-03 review's
  C1 finding stays fixed.
- **The panel cache-buster is not affected.** `PANEL_VERSION` stayed at `0.2.0`,
  which would once have been a stale-asset bug, but `panel._fingerprint` now
  digests `panel.js` *and* every file under `panel/`, so the four new parts change
  the URL by themselves. `tests/test_panel_assets.py` names all five parts.
- **Error swallowing is justified in every place the branch added one.**
  `async_lay_the_floor`, `_async_floor_for` and `_async_mark_day` each log at
  `exception` level before returning; `_async_make` logs at `debug` for a refusal
  and `_async_floor_for` raises that to `warning` where a refusal really is an
  obstacle (a live dashboard that cannot get a floor, which would otherwise repeat
  silently at every start). None of them hide something the user needs to act on,
  and none of them can reach Home Assistant's start.
- **`manifest.json` is still `0.2.0`.** Not a branch defect — the history shows
  the version is bumped in its own release commit (`ef9dc58`). Recorded only as a
  reminder that HACS needs the bump before this ships.
