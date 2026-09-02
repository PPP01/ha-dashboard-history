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
- **Says in plain words what a change did**, and what restoring it would
  do — cards and views by name, with the diff underneath for anyone who
  wants it.
- **Lets you describe a change in your own words.** One field. The text
  becomes the headline of that entry.

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

**The state you have now is set apart at the top**, marked `current state`,
with the history below it. That mark is worked out, not assumed: if the
dashboard was changed behind Home Assistant's back, the newest entry is
*not* what you have, and then nothing is marked. Entries further down that
hold the same content say `same as now` — which is what makes a history
that went back and forth readable at all.

Where setting the dashboard back would change nothing, the button is not
offered; it says why instead.

**You click a change, never a revision.** Asked to undo a deletion, people
reach for the line that says the card was deleted — which is one line too
late, because what they want is the state just before it. For putting a
single card back, the panel works that out for you, so the trap is not
signposted, it is gone.

For setting the *whole* dashboard back, a row offers **both** of the states
it sits between:

- *Back to the state before this change* — for undoing something.
- *Back to the state after this change* — for a state you recognise and
  want again.

Either one disappears when its target is what the dashboard holds already,
so a button never offers a change that changes nothing.

Nothing is written until you have confirmed it — and before you do, the
panel says in plain words what will happen:

```
What applying this does

  In the view Ground floor
    heading: Aktuell will be deleted

  ▸ Show the technical details
```

The diff is still there, one click away, and it is still the exact
account. It is just no longer the first thing you have to read. The same
summary appears when you expand a change, in the past tense: what that
change did.

And when a change cannot be described in terms of cards — a renamed
dashboard, a changed icon — the summary says so and points at the diff.
It never claims that nothing changed while a diff below it shows
otherwise.

### Describing a change

Hover a change and a pencil appears. One field, prefilled, Enter saves —
the same shape as Home Assistant's own "rename" on an integration.

Your text becomes the headline of that entry; the automatic message moves
underneath it in grey and stays there, because it is the part you can
trust when your own note from last year no longer says enough. Emptying
the field removes the description again.

The commit is **not** rewritten. The description is a git note, so every
revision you have written down anywhere stays valid.

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
| `explain` | What one change did, in plain words |
| `describe` | Give a change your own description |
| `deleted_since` | What disappeared since a revision |
| `restore_deleted` | Put one of them back (needs `confirm`) |
| `restore_state` | Set a dashboard back to an earlier state (needs `confirm`) |
| `forget` | Remove a deleted dashboard's history for good (needs `confirm`) |
| `debug_snapshot` | What the integration currently sees |

`describe` is the only writing service without `confirm`. The rule
protects dashboards from unintended change; a description changes no
dashboard, and emptying the field undoes it.

Two more exist for anyone who wants them, and they are not in the panel:
`create_version` and `versions`. A version is an annotated git tag, which
does one thing a description cannot — it gives a point in the history a
*name you can use as a revision*. If you do not need that, describe the
change instead; it is the same idea with less to remember.

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

Measured against Home Assistant 2026.8.3: the dashboard comes back
immediately, with its old title and icon and a byte-identical
configuration, and Home Assistant manages it as its own — you can rename
it or delete it from the settings dialog straight away, with no restart.

It is created through Home Assistant's own dashboard collection, which is
not a guaranteed extension point. If a future version puts that object out
of reach, the restore **refuses** rather than half-writing one:

```yaml
applied: false
error: >-
  Cannot recreate the dashboard the-deleted-one: Home Assistant's dashboard
  collection could not be reached … Create a dashboard with the URL
  the-deleted-one under Settings > Dashboards, then run this restore again
  to put its cards back.
```

That refusal replaced an earlier version that wrote the entry through a
collection of its own and reported a partial success. It looked like it
worked: the dashboard appeared, opened and could be edited. But Home
Assistant lists dashboards from one place and changes them in another, so
renaming it failed with "Unable to find dashboard_id". A half-restored
dashboard that looks healthy is worse than an honest refusal.

## Tidying up: forgetting a deleted dashboard

A deleted dashboard stays in the list forever, which is the point — it is
the one you come here for. But delete one every few months and the list
fills up with them, so they are **folded away** under a `Deleted (N)`
section rather than mixed in with the live ones.

When you are sure you will never want one back, you can **forget** it:

```yaml
action: dashboard_history.forget
data:
  dashboard: the-one-i-am-done-with
  confirm: true
```

Without `confirm` you get a count of what would be lost — how many
recorded states, over what period, and how many carry a description you
wrote — and nothing is changed. In the panel it is the *Forget for good*
button on a deleted dashboard.

This is the only thing here that cannot be undone, and the only thing
that refuses to touch a live dashboard: if Home Assistant still has it,
the answer is no.

**One side effect, stated because you will notice it.** Git can only
really remove something by rewriting history, so every revision from the
first affected commit onwards changes. A revision you wrote down
somewhere will no longer resolve. Your descriptions and named versions
are carried across onto the new commits — that part is not left to
chance.

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

Everything else — the capture, the services, the WebSocket API, the panel
— needs a running Home Assistant, and every defect found in this project
so far has been in exactly those parts. There is a disposable instance
for that (see `docker/README.md`) and two things to run against it:

```bash
python3 tests/integration/run_checks.py     # the API, end to end
python3 tests/integration/look_at_panel.py  # the panel, in a real browser
```

## License

MIT — see [LICENSE](LICENSE).
