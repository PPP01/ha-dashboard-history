# ha-dashboard-history

Home Assistant integration: change history and restore for Lovelace dashboards. Meant to be published via HACS eventually; for now it's only being tried out on the author's own installation.

@.claude/lessons.md

**Read before working — both:**

- `docs/superpowers/status.md` — current state: which initiatives are done, what's still open, a module overview. Start here.
- `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` — the design and its *reasoning*. Binding in case of conflict. Written in German — see "Language" below.

The individual implementation plans under `docs/superpowers/plans/` and the reviews under `docs/superpowers/reviews/` are a dated journal, not required reading — `status.md` points there when the current state needs it.

Larger initiatives (a letter in the spec, its own plan) get implemented with `superpowers:subagent-driven-development`; smaller fixes use the normal workflow.

## Language

Audience decides the language, not the kind of document — anything an outside contributor might ever see is English.

- **English — everything a stranger to the project might see.** Code, comments, docstrings, service names, log messages, the README, **and commit messages.** Plus anything on GitHub: issues, pull requests, release notes, the repository description, labels.
  - **Commit messages were German until 2026-09-02** — 51 of them are public and stay as they are. They are **not** rewritten: there's a release `v0.2.0` that HACS depends on. A history that changes convention at one point is more honest than one smoothed over afterwards.
- **German — the one deliberate exception.** The design journal under `docs/superpowers/` (spec, plans, reviews, `status.md`) — the author's working journal, with real umlauts (ä ö ü ß) and German guillemets (»…«). See the README's "A note on language" for the full reasoning; nothing in the journal is needed to use this integration or find your way around the code.

Personal preferences — what language the assistant is addressed in, typography quirks — don't belong here, since they say nothing about the project. They live in `CLAUDE.local.md` (gitignored, see `.gitignore`), which anyone can create for themselves and which simply doesn't exist for anyone else.

## Hard rules

These are stated as such in the spec and are not negotiable:

- **No shelling out to `git`.** `dulwich` only. Whether a `git` binary exists differs between HA OS, Container, Core, and Supervised. Measured, it's only a 15 ms difference per save — for twice the behavioral surface.
- **No intercepting or replacing Home Assistant internals.** No monkey-patching of WebSocket commands or services. That would hit every user at once on release.
- **Nothing blocks Home Assistant's startup.** Errors while recording are logged and swallowed. A broken history is annoying; a broken HA startup is not.
- **`yaml_io.py`, `analyze.py`, `restore.py`, `versions.py`, `store.py`, and `keys.py` stay free of Home Assistant.** No `import homeassistant` in them — they are the core and have to stay testable in plain pytest.
- **Blocking work belongs in an executor** (`hass.async_add_executor_job`). A commit takes about 30 ms.
- **Every service and every WebSocket command requires admin rights** (`async_register_admin_service` / `@websocket_api.require_admin`, since 2026-09-03). No write path is reachable without admin.
- **Nothing is written without a preview.** Any service that triggers an irreversible or hard-to-undo step — changing a dashboard state, rewriting history (`forget`), removing a version (`remove_version`) — requires `confirm: true` and otherwise returns only the preview. Exempt, because none of that applies: `describe` (writes a note), `create_version` and `retitle_version` (set or rename a tag) — no dashboard changes, and a confirmation dialog beforehand would be ceremony without any protective effect (spec Decision 7, boundary from 2026-08-31).
- **Restoring is additive, never a guessed replacement.** What disappeared comes back, because that's unambiguous (spec Decision 4: Lovelace cards carry no identifier — counted: 661 cards, 0 with `id`). Since initiative E (spec Decision 15), in addition: a single change can be undone in a targeted way — but only when the card it produced can be shown to sit exactly once, unchanged, in today's state. Otherwise it's refused, never guessed.

## Tests

```bash
python3 -m pytest tests/ -v
```

The six Home-Assistant-free modules run without a live installation. `tests/conftest.py` puts the package directory on `sys.path`, so `import analyze` works flat, without running the HA-importing `__init__.py`.

Some cases check against **real** dashboards — that's the difference between four made-up cards and a few hundred grown ones. Where they live isn't in the repository: either in `DASHBOARD_HISTORY_REAL_STORAGE` or in the untracked file `tests/.real-storage`, which `conftest.py` reads. Without either, those cases skip **visibly** (`140 passed, 3 skipped`) instead of quietly passing through.

## Trying it on a real installation

Installed via HACS as a custom repository: *HACS → Custom repositories* → `https://github.com/PPP01/ha-dashboard-history`, category Integration. That way the integration lands in `custom_components/` the same way any user eventually will — not through a shortcut only the developer has.

**No symlink from the working tree.** If the installation is reached over a network mount (SSHFS and similar), none can be created there, and it would resolve on the side where Home Assistant runs anyway — this repository's path doesn't exist there.

Updates through HACS need real releases with an ascending version number. A pre-release suffix sorts **below** the base version under semver and isn't recognized as an update.

### Check locally first

Before any live step, check it in the throwaway instance:

```bash
docker compose -f docker/compose.yaml up -d
python3 tests/integration/run_checks.py
```

It drives a real Home Assistant 2026.8.3 over HTTP and WebSocket and
reaches the modules `pytest` structurally can't — every defect found in
this project so far was there. Setup and the two pitfalls:
`docker/README.md`. Configuration and the token live **outside** the repo.

A third path, for the little that falls between the other two:

```bash
docker exec -i dashboard-history-test python3 - < tests/integration/run_day_marks.py
```

It runs **inside** the container, where `homeassistant` exists, but
**without** a running instance — for code `pytest` can't import and that
`run_checks.py` can't trigger, because no API backdates a commit. It
builds a real repository and only moves the clock at the one point
where the calendar math reads it. Only viable as long as the faked
piece stays small; if it grows, the case belongs in `run_checks.py`
instead. Over `stdin`, because only `custom_components/` is mounted
into the container.

⚠️ **An installation something depends on is not a test rig.** Two rules from that, both learned the expensive way: **never poll during an HA restart** — HA's IP-ban system locks out the developer's own access otherwise — and **no test may delete by prefix**, only by its own, exactly named key. What went wrong once, from that, is in the addendum from 2026-09-01 in `docs/superpowers/plans/2026-08-31-eigene-texte-und-klartext.md`.

Environment: HA 2026.8.3, container Python 3.14.6, development machine Python 3.12.3.

## Git

- Commit format: **English** (see "Language"). Subject in the imperative, first letter capitalized, max. 50 characters. Blank line. Body wrapped at max. 72 characters per line, explaining the *why*.
- Branch is `main`, remote is `origin` (public on GitHub). **Pushed, tagged, and published only on the user's explicit go-ahead.** The repository is publicly readable: no paths from someone else's machine, no details about the installation it's tried on, no credentials — not even in test data or comments.
