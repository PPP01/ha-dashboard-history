# Dashboard History

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Records every change to your Home Assistant dashboards and lets you put
back what disappeared.

Home Assistant only offers undo *while* you are editing. Close the editor
and that history is gone; a card you deleted last week is only in a full
backup, if at all. This integration keeps a history of its own.

## What it does

- Records every dashboard save automatically. No configuration needed.
- Shows the history of each dashboard: when it changed and what changed.
- **Puts back what disappeared** — a deleted card, a deleted view.
- Restores a whole dashboard to an earlier state.
- Lets you name a point in the history: a *version* with a title and a
  description.

## What it does not do

- **It does not undo edits.** Only disappearances can be restored. See
  "Why only deletions?" below — the reason is not laziness.
- It does not record *who* made a change. Home Assistant does not pass
  that information to integrations.
- It is not a backup. It covers dashboards, nothing else.

## Why only deletions?

A Lovelace card carries no identifier. It is defined purely by its
position in a list. Putting back a card that is gone is *additive*:
nothing is overwritten, so there is exactly one correct result. Undoing
an *edit* means replacing today's version with an older one — a merge
without identities, and when a later change touched the same card there
is no single correct answer.

Deletions are also the painful case. A card you moved by accident, you
move back. A card you deleted is gone.

## Installation

1. Add this repository to HACS as a custom repository (type: Integration).
2. Install "Dashboard History".
3. Restart Home Assistant.
4. Settings → Devices & Services → Add Integration → Dashboard History.

## Usage

### The panel

After setup you get **Dashboard History** in the sidebar. It is there all
the time, not only while you are editing a dashboard — which was the whole
complaint this project started from.

Pick a dashboard on the left, and you get its changes, newest first. Click
a change to see what it made disappear, and put any of it back. A deleted
dashboard is listed too, marked as such, with a button that brings it back.

**You click a change, never a revision.** That is deliberate. Asked to undo
a deletion, people reach for the line that says the card was deleted — which
is one line too late, because what they want is the state just before it.
The panel works that out for you, so the trap is not signposted, it is gone.

Nothing is written until you have seen the diff and pressed Apply.

### Services

Everything the panel does is also available as services under Developer
Tools → Actions.

Dashboards are addressed by their **key**: that is the dashboard's
`url_path`, and `_default` for the built-in default dashboard. Run
`dashboard_history.debug_snapshot` to see the keys as the integration
sees them. Note that the key is the `url_path` (`energie-2`), not the
dashboard's internal id (`energie_2`) — the two are not the same string.

### I deleted a card by accident

1. `dashboard_history.history` with your dashboard — note the revision
   from *before* the deletion.

   ```yaml
   action: dashboard_history.history
   data:
     dashboard: dashboard-erika
   ```

2. `dashboard_history.deleted_since` with that revision — lists what is
   missing, each with a position.

   ```yaml
   action: dashboard_history.deleted_since
   data:
     dashboard: dashboard-erika
     revision: 939b93231b6f9ea7349d5c3e8a875534865facf3
   ```

   ```yaml
   items:
     - position: 0
       kind: card
       label: heading
       view: home
   ```

3. `dashboard_history.restore_deleted` with that position — returns a
   preview. **Nothing is written.**

   ```yaml
   action: dashboard_history.restore_deleted
   data:
     dashboard: dashboard-erika
     revision: 939b93231b6f9ea7349d5c3e8a875534865facf3
     position: 0
   ```

4. Same call again with `confirm: true` — the card is back, at its old
   position.

### Services

| Service | What it does |
| --- | --- |
| `history` | The recorded states of one dashboard |
| `deleted_since` | What disappeared since a revision |
| `restore_deleted` | Put one of them back (needs `confirm`) |
| `restore_state` | Set a dashboard back to an earlier state (needs `confirm`) |
| `create_version` | Name a point in the history |
| `versions` | List the named points |
| `debug_snapshot` | What the integration currently sees |

## If a whole dashboard is deleted

The deletion is recorded the next time Home Assistant starts, as a commit
saying `<dashboard>: dashboard deleted`. Home Assistant announces a deleted
dashboard with no event of its own, so it is noticed by comparison rather
than as it happens.

**Nothing is lost.** Every earlier state stays readable at its revision:

```yaml
action: dashboard_history.history
data:
  dashboard: the-deleted-one
```

**And it comes back.** `restore_state` with a revision from before the
deletion recreates the dashboard — with its old title, icon and sidebar
setting, not just its cards:

```yaml
action: dashboard_history.restore_state
data:
  dashboard: the-deleted-one
  revision: 939b93231b6f9ea7349d5c3e8a875534865facf3
  confirm: true
```

Without `confirm` you get the preview and a `creates_dashboard: true` flag,
and nothing is written.

A dashboard is created through Home Assistant's dashboard registry, which
is not a guaranteed extension point. So the two halves are graded
differently: writing the registry entry and the configuration must work,
and does. Everything beyond that is a bonus, and whatever falls short is
named in the response rather than glossed over.

Measured against Home Assistant 2026.8.3: the dashboard comes back
immediately, with its old title and icon and a byte-identical
configuration — **and one thing is left over.** Home Assistant's own
dashboard *settings* do not know about it until the next restart, so
renaming or deleting it from there reports it as missing. Viewing it,
editing its cards and its history all work. The response says as much:

```yaml
applied: true
created: true
note: >-
  the dashboard is back and usable; Home Assistant's dashboard settings
  will not manage it until the next restart
```

## Renames and other dashboard settings

The title, icon and sidebar setting of a dashboard live in Home Assistant's
registry rather than in the dashboard configuration, and Home Assistant
announces no event when they change. They are picked up when a panel moves,
which covers creating, renaming and deleting a dashboard, so a rename shows
up in the history as `renamed to "…"` — and a dashboard that is restored
comes back under the name it had, not the name it started with.

## Where the data lives

In `config/dashboard_history/`, as a git repository this integration
owns. Each dashboard is one YAML file; each save is one commit; each
version is a tag.

You may look inside it. Do not edit it by hand — the integration writes
it and expects to be the only writer.

No system `git` is required: the integration uses a pure Python
implementation, so it works the same on Home Assistant OS, Container,
Core and Supervised.

### How much space

Measured on the installation this was built against: ten dashboards, the
largest 262 KB as YAML, come to roughly 620 KB for the first recorded
state of each. A save that changes one card adds a few kilobytes, since
git stores the states deduplicated and compressed.

## Development

The three modules that carry the logic — `yaml_io.py`, `analyze.py` and
`restore.py` — import nothing from Home Assistant, so the test suite runs
without an installation:

```bash
python3 -m pytest tests/ -v
```

## License

MIT — see [LICENSE](LICENSE).
