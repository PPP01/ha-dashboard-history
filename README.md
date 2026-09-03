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

## Telling a move from a deletion

This is the hardest thing the integration does, and it is worth
understanding, because it decides what you get offered when something
goes missing.

A card has no identifier. Not a hidden one, not an optional one —
measured across twelve real dashboards, 1783 cards carried exactly zero
identifiers between them. So when two states of a dashboard are
compared, the cards have to be recognised **by their content**. Four
passes do that:

1. Identical cards pair up **in the same card list**.
2. Whatever is left over is looked for **anywhere on the dashboard**. A
   card found somewhere else was moved — and a moved card is not
   missing.
3. What is still left is paired **within its own list** by a
   content-based fingerprint — entity, title, name, heading, first
   entity of a list, first line of text — choosing the **most similar**
   candidate.
4. Anything unpaired is a real deletion on one side, a real addition on
   the other.

Pass 1 running before pass 2 is what keeps this honest. Delete a card
from one view while an identical card sits untouched in another, and a
global search running first would pair your deleted card with the
untouched one and lose the deletion entirely. Every card claims its own
place first.

### What you will see

**You drag a card into another view, or into another section.**

```
1 moved
  tile: Living room lamp was moved to "Kitchen"
```

Nothing is offered to put back, because nothing is missing. To undo it,
use **Undo this change** (or **Back to the state before this change**)
— that puts the whole dashboard back, which also takes along anything
else you saved in the same step.

**You have two similar cards, delete one and edit the other.**

Say two tile cards on the same light: you delete the first and change
the second from blue to green. The surviving card matches its own old
form in three fields of four; it matches the deleted card in two of
five. The closer pair wins, so the card offered back is the one you
actually deleted — not the survivor.

Before this, the first match won instead of the best one, and the
result was backwards: you were offered the old version of a card that
was still on the dashboard, and the card you really lost was never
offered at all.

### Two things it still gets wrong

Both are named here rather than hidden, and both are covered by tests
so that they cannot drift silently.

**A card with nothing to recognise it by.** Some cards carry no entity,
no title, no name, no heading, no entity list, no text, and no nameable
card inside them — measured on a real installation, 27 of 484, mostly
custom chart cards, `vertical-stack` and `conditional`. Edit one of
those and the data cannot say whether it is the same card changed, or
the old one deleted and a new one added. You will see `1 removed, 1
added` and be offered the old version back. Accepting that gives you
the card twice; the diff shown before you accept is your protection.

**A card moved and edited in the same save.** Pass 2 no longer
recognises it (the content changed), and pass 3 does not look across
places. So it reads as a deletion plus an addition, with the same
consequence as above. Looking for edited cards across views would close
this and open something worse: the same entity on two views is
ordinary, so a real deletion could be mistaken for a move and never be
offered back at all. A missed offer is worse than one you can decline.

### What the gap costs, and when

Worth walking through, because the two ways back behave very differently
here — and because the cheap way has a time limit.

Change the URL of an `iframe` card. The history reads `1 removed, 1
added`, and the row offers both kinds of button.

**Undo this change** is exact:

```diff
     - type: iframe
-      url: https://example.com/new
+      url: https://example.com/old
```

**Put back** cannot be, and the preview says so before you accept:

```diff
     - type: iframe
+      url: https://example.com/old
+      aspect_ratio: 60%
+    - type: iframe
       url: https://example.com/new
       aspect_ratio: 60%
```

That is not a fault in the button. **Put back** is additive by
definition — it never overwrites anything — so the only thing it can do
with a card it believes was deleted is add it back. It believes that
because the card carries nothing to recognise it by. Both halves are
behaving exactly as designed; they simply meet a card with no identity.

**The cheap way has a time limit.** Immediately after the edit, **Undo
this change** costs nothing: there is nothing else in that step to
undo. A week and thirty saves later the same button is
**Back to the state before this change**, and it takes all thirty with
it — with a preview to match. From then on the choice is:

| | |
| --- | --- |
| **Put back** | Two cards. Delete the one you do not want, by hand. |
| **Back to the state before this change** | The other thirty changes go too. |

"Go" rather than "are lost": every one of them is still recorded, and
you can come forward again the same way. But it is a large step taken
for a small mistake, and you would be redoing work you had already
decided on.

**So the practical advice is simply: fix it soon.** If you notice that
one of these cards is wrong, the exact undo is right there. Leave it a
month and only the two blunter options remain.

**And the reason it is like this** is the one this whole page keeps
coming back to. A card with no entity, title, name, heading, entity
list or text has no identity across two states, and nothing can invent
one. The tool could guess — pair up whatever is left over and hope. The
cost of guessing wrong in the other direction is worse than this: a
card you really deleted, quietly reclassified as an edit, and never
offered back at all. A duplicate you can see in a preview and decline
beats a deletion you are never told about.


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

**Two ways back, and what each one reaches.** A row where something is
missing carries two kinds of button, and they are not two labels for one
action. They differ in reach:

| Button | What it touches |
| --- | --- |
| **Put back** | One item. It is reinserted into the dashboard *as it stands today*, and nothing else changes. |
| **Undo this change** / **Back to the state before this change** | The whole dashboard. That earlier state is written over what is there now. |

On the newest change the two can look identical, and sometimes they
genuinely are: delete a single card, and putting it back or undoing the
change both leave you with the same dashboard. That is the case most
people meet first — which is exactly why the difference is easy to miss.

Now picture a deletion from three weeks ago. **Put back** brings that one
card into today's dashboard and leaves the three weeks alone. **Back to
the state before this change** throws them away.

Where both are on screen, the panel says so:

> Put back adds a single item to the dashboard as it stands today and
> changes nothing else. Setting the state back replaces the whole
> dashboard with how it was then.

It describes each rather than claiming they differ. Where the outcomes do
coincide — and on the newest single deletion they do — "these are not the
same thing" would be the confusing sentence, not the helpful one.

Nothing is written until you have confirmed it — and before you do, the
panel says in plain words what will happen:

```
What applying this does

  In the view Ground floor
    heading: Right now will be deleted

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

### Versions

A version is a name for a state your dashboard has already reached — an
annotated git tag such as `my-dashboard/v1.2.0`. It belongs to one
dashboard, so every dashboard counts its own: two different dashboards
can each have their own `v1.0.0` without conflict.

Expand any change and choose "Version up to here". A dialog offers three
buttons — patch, minor, major — each already carrying the number it would
get, patch preselected, plus a title and an optional description. You
never type the number yourself: it always counts up from the highest that
dashboard already has, so it can never collide with one you made before.

There are no checkboxes for which changes to include. Each commit already
holds the dashboard's complete state, so the state after change 3
contains change 2 whether you wanted it there or not — a gap in a
selection is not something a version could express.

Making one writes no commit and changes nothing about the dashboard, so
it needs no confirmation.

A version on a dashboard that no longer exists is worth having — "Back to
this version" brings the whole dashboard back. Mark one of its own states
though: the change that recorded the *deletion* holds no state at all, so
marking that one is refused rather than made into a version nobody could
return to.

In the panel, the history is cut into collapsible sections at the
versions, with the changes not yet in a version sitting above them. Each
section head shows the version's number, its title, how many changes it
holds, and a "Back to this version" button — not offered when that
version is what the dashboard already holds.

"Back to this version" goes through the same preview as everything else:
plain words, the diff, and an explicit Apply. Going back destroys
nothing — the tag still points at its commit, so from an older version
you can go forward to a newer one with the same button, and working on
after going back is fine too.

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
| `versions` | The named versions, all of them or one dashboard's |
| `next_versions` | What the next patch, minor and major would be called |
| `create_version` | Name a recorded state as a version |
| `debug_snapshot` | What the integration currently sees |

`describe` and `create_version` are the only writing services without
`confirm`. Neither can put a dashboard into a state you would need
`restore_state` to escape: one writes a note, the other a tag, and
neither touches the dashboard itself. A wrong description is undone by
an ordinary edit — clearing the field; a version, once made, was never a
change to the dashboard in the first place.

The version services are in the panel as well, so reach for them only if
you want to script them. One detail matters for scripting: `restore_state`
accepts a version's name as its `revision`, exactly as it accepts a git
revision — that is what lets a script go to a version the same way the
panel does.

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
somewhere will no longer resolve. The descriptions and versions of the
dashboards that stay are carried across onto the new commits — that part
is not left to chance. **The forgotten dashboard's own versions go with
it** — every tag under its own name — because a version belongs to one
dashboard: keeping one would leave it hanging on some other dashboard's
commit, naming a state that no longer exists.

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

**A note on language.** Everything here is English: the code, the
comments, the commit messages, and anything on GitHub. One exception, and
it is deliberate — the design record under `docs/superpowers/` is written
in German. It is the author's working journal: every design decision in
this project is numbered there together with the reasoning and the
measurements behind it, and translating that would cost the precision it
is written for. Nothing in it is needed to use this integration or to
find your way around the code; this README and the comments carry that.
If you want the reasoning behind a particular decision and do not read
German, open an issue and ask — answering in English is easy.

The four modules that carry the logic — `yaml_io.py`, `analyze.py`,
`restore.py` and `versions.py` — import nothing from Home Assistant, so
the test suite runs without an installation:

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
