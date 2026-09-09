# Dashboard History

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/PPP01/ha-dashboard-history/blob/main/LICENSE)

Records every change to your Home Assistant dashboards, and gives you a
way back.

Home Assistant only offers undo *while* you are editing. Close the editor
and that history is gone; a card you deleted last week is only in a full
backup, if at all. This integration keeps a history of its own — one
commit per save, forever, with no configuration.

**This page has two parts.** [Part 1](#part-1-using-it) is for using it
and assumes nothing. [Part 2](#part-2-how-it-works-and-where-it-stops)
is the mechanism and the exact limits, for anyone who wants to know what
the tool can prove and what it can only assume.

Questions that come up while using it — and why some things are refused
on purpose — are answered in the
[FAQ](https://github.com/PPP01/ha-dashboard-history/blob/main/FAQ.md).

**[Part 1: Using it](#part-1-using-it)** —
[What you get](#what-you-get) ·
[Installing](#installing) ·
[The panel](#the-panel) ·
[Getting something back](#getting-something-back) ·
[If your dashboard uses sections](#if-your-dashboard-uses-sections) ·
[Versions](#versions) ·
[Describing a change](#describing-a-change) ·
[When a whole dashboard is gone](#when-a-whole-dashboard-is-gone) ·
[Renames and other settings](#renames-and-other-dashboard-settings) ·
[What it will not do](#what-it-will-not-do)

**[Part 2: How it works, and where it stops](#part-2-how-it-works-and-where-it-stops)** —
[Recognising cards without identifiers](#recognising-cards-without-identifiers) ·
[What holds the cards](#what-holds-the-cards-views-and-sections) ·
[The proof behind the undo](#the-proof-behind-the-undo) ·
[When a change is recorded](#when-a-change-is-recorded) ·
[Known limits, measured](#known-limits-measured) ·
[Refusals by design](#refusals-by-design) ·
[Services](#services) ·
[Where the data lives](#where-the-data-lives) ·
[Development](#development)

---

## Part 1: Using it

### What you get

- **Every save recorded, automatically.** No setup, no configuration, no
  scheduling. The history starts with the first save after installation.
- **A panel in the sidebar**, there all the time — not only while you are
  editing, which was the whole complaint this project started from.
- **Plain-language history.** Not just a diff: *"markdown: Shopping list
  was deleted"*, *"tile: Living room lamp was moved to Kitchen"*. The
  diff is still there, one click away.
- **Three ways back**, from the surgical to the sweeping: take back one
  change, put back one missing card, or set the whole dashboard to an
  earlier state.
- **Versions** — names for states worth coming back to, such as
  `my-dashboard/v1.2.0`. Some are made for you, so the list is never
  empty. Rename one whenever you like, or take one away again; the state
  underneath stays either way.
- **Your own notes on any change.** One field. Your text becomes the
  headline of that entry.
- **Search**, across the whole recorded history of a dashboard, including
  your own notes and version titles.
- **Deleted a whole dashboard?** It comes back — cards, title, icon and
  sidebar setting.
- **Nothing is written without a preview** and an explicit confirmation.

### Installing

Needs **Home Assistant 2024.11 or newer**.

1. Add this repository to HACS as a custom repository (type:
   Integration).
2. Install "Dashboard History".
3. Restart Home Assistant.
4. Settings → Devices & Services → Add Integration → Dashboard History.

That is all. There is exactly one option, and you can ignore it (see
[Versions](#versions)).

Only administrators can read or use any of this. A signed-in
non-administrator gets no history, no previews and no restores.

### The panel

**Dashboard History** appears in the sidebar. Pick a dashboard on the
left and you get its history, newest first.

**That list is your sidebar, in your sidebar's order** — including an
arrangement you dragged into place, which lives in your own user data
and so differs from the next person's. Dashboards that are *not* in your
sidebar, whether hidden for everyone or only by you, are counted and
folded away under `Not in the sidebar (N)`. The order is read when the
panel loads; rearrange your sidebar in another tab and the reload button
fetches it again.

**The state you have now is set apart at the top**, marked `current
state`. That mark is worked out rather than assumed: if a dashboard was
changed behind Home Assistant's back, the newest entry is *not* what you
have, and then nothing is marked. Entries further down holding the same
content say `same state as now`, which is what makes a history that went
back and forth readable at all.

Click a change and it expands: what it did, in words, with the diff
underneath and the buttons that lead back.

#### Two views

A button in the top bar, right next to the title, switches between them,
and your choice is remembered — in your browser, so it is yours rather
than the installation's.

**Simple view** shows nothing but the versions — the named states. This
is the one to use when you want *"put it back to how it was on Tuesday"*
and nothing more. Each version is a section you can fold open to see the
changes inside it.

At the top of it sits the state you have now, marked `current state`.
That mark is unconditional here, unlike the one on a row above: this box
*is* what you have, whatever the history does or does not agree with. It
always carries **Save this as a version**, which is how a version gets
made without leaving this view — including on a dashboard that has none
yet, where the box is the only thing on the page.

What else the box holds depends on where the dashboard stands:

- **On the newest version.** The box and that version's own row are
  drawn as one, so the number, the title and the date stand where a
  sentence about them would. Folded open, it lists the changes *that
  version* collected — not the ones since, because on a state a version
  already holds, there are none that changed anything.
- **Moved on since.** The box says so, and offers a second button,
  **Undo / Go back to v1.2.0**, which takes the dashboard off everything
  since that version in one step. Folded open, it lists what has
  happened since. Like every other way back the button shows you the
  diff first, and what you are leaving is kept: it stays in the history
  as its own entry, and the dialog offers to name it as a version too.

**Advanced view** shows every recorded change, newest first, twenty-five
at a time with a *Load older changes* button. The versions still appear,
as headers that cut the list into sections.

#### Search

A search box sits above the list and searches what the current view
shows: in the simple view, the versions; in the advanced view, the
changes that are loaded.

In the **advanced view**, when the answer is not among them, a button
offers **Search the whole history** — that goes to the server and walks
the entire recorded past, looking at the automatic message, any note you
wrote yourself, and the title, description and number of any version on
that state. If the box matches nothing that is loaded, the whole history
is searched without being asked.

The **simple view** searches the versions it has and says how many of
them matched. It has no button to the server, and needs none: the
versions are all there, however far back their states lie.

### Getting something back

There are three ways back, and they differ in *reach* rather than in
quality. The panel leads with the narrowest one that fits.

| | What it touches |
| --- | --- |
| **Undo this change** | That one change, and nothing else. Everything saved since stays exactly as it is. |
| **Put back** | One missing item, reinserted into the dashboard *as it stands today*. Nothing else changes. |
| **Back to the state before / after this change** | The whole dashboard. That earlier state is written over what is there now. |

**Undo this change** is what people mean by undoing something, so the row
leads with it. It is offered only where the tool can *prove* the result
is exact — see [The proof behind the undo](#the-proof-behind-the-undo).
Where it cannot, the row says so in place of the button rather than
guessing:

> This change cannot be taken back exactly: tile: Living room lamp was
> changed again after this, so there is no exact version left to put
> back.

**Put back** is for something that is simply missing. It only ever
*adds* — it never overwrites anything — so it is always safe, and it
leaves everything you have done since alone.

**The two whole-dashboard buttons sit under a fold**, labelled *Replace
the whole dashboard instead*. They are a real capability and somebody
wants one about once a year; leading with them would be offering the
largest step first. Either one disappears when its target is already what
the dashboard holds, so a button never offers a change that changes
nothing.

An example that shows the difference. Picture a deletion from three weeks
ago:

- **Put back** brings that one card into today's dashboard and leaves the
  three weeks alone.
- **Undo this change** does the same, and also takes back anything else
  that one save did.
- **Back to the state before this change** throws the three weeks away.

On the *newest single deletion* all three leave you with the same
dashboard, which is exactly why the difference is so easy to miss: the
first shape anybody meets is the one where they agree.

#### The undo does not run out with time

Thirty saves and a week later, **Undo this change** still takes back that
one save and leaves the other thirty standing. What it needs is not haste
but the card that change produced: still on the dashboard, byte for byte
as the change left it, and there exactly once.

**What ends it is a second edit, not the calendar.** Change the same card
again and there is no version left that this change produced — then the
row says so, and the remaining choice is the blunt one: put the old card
back beside the new one and delete the one you do not want, or set the
whole dashboard back and lose the changes since.

So the practical advice is *fix it soon* — where "soon" means "before you
edit that card again", not "before the week is out".

#### I deleted a card by accident

In the panel: find the change that deleted it, expand it, press **Undo
this change** or the card's own **Put back**, read the preview, confirm.

The same thing through Developer Tools → Actions, if you prefer:

```yaml
# 1. Find the change. Note its revision.
action: dashboard_history.history
data:
  dashboard: my-dashboard
```

```yaml
# 2. See what disappeared since then, with a position for each item.
action: dashboard_history.deleted_since
data:
  dashboard: my-dashboard
  revision: 939b93231b6f9ea7349d5c3e8a875534865facf3
```

```yaml
# 3. Put one back. Without confirm this only previews — nothing is written.
action: dashboard_history.restore_deleted
data:
  dashboard: my-dashboard
  revision: 939b93231b6f9ea7349d5c3e8a875534865facf3
  position: 0
  confirm: true
```

### If your dashboard uses sections

Sections — the boxes a dashboard in the modern layout is built from — are
the one place where this tool is noticeably weaker, and it is worth
knowing that *before* you need it.

**Cards inside a section are handled normally.** Deleted, edited, or
dragged from one section to another: all recognised, all named correctly,
all recoverable with the narrow tools. If your sections stay as they are
and you work on the cards in them, nothing below applies to you.

**The section itself is not recognised.** Home Assistant's editor gives a
section no identifier and no path, and a view's URL path has no equivalent
one level down — so the integration knows a section only by its position
in the row. That has four consequences:

- **Renaming a section** does not show up in words. The entry says `no
  card changes` and points at the diff, which is correct and complete.
- **Deleting a whole section** comes back through *Put back*, which
  offers the section as one thing rather than as a heap of cards — as
  long as the other sections of that view are as you left them. Edit one
  of them in between and it says so; *Undo this change* declines either
  way, because a section has no path to recognise it by. The whole-state
  restore brings it back in any case.
- **Adding a section** switches the undo off for that one save. Nothing
  is broken; the tool declines to work while the row it counts on has
  shifted.
- **Reordering sections that have no titles** is the one case in the
  whole integration where something can go wrong silently — see the
  caution below.

**Setting the whole dashboard back to an earlier state always works**, for
sections exactly as for everything else. Nothing you have is ever
unrecoverable; what the limits cost is the precision of the small tools.

> [!TIP]
> **Give your sections titles.** A title is the only thing the
> integration can recognise a section by. With titles, a reordering that
> would confuse it produces an honest refusal. Without them, **Put back**
> can file a card into the wrong section without warning. Titles are
> optional in Home Assistant and most people leave them off — on the
> installation this was developed against, all 80 sections were untitled.

There is an intention to recognise sections properly, by having the
integration keep an identity chain of its own alongside each save. It is
**an idea at this point** — not designed, not planned, not built — so
nothing on this page should be read as a promise about it.
[Part 2](#sections-in-detail) has the measured behaviour, case by case.

### Versions

A version is a name for a state your dashboard has already reached — an
annotated git tag such as `my-dashboard/v1.2.0`. It belongs to one
dashboard, so every dashboard counts its own: two dashboards can each
have a `v1.0.0` without conflict.

Expand any change and choose **Version up to here**. A dialog offers
three buttons — patch, minor, major — each already showing the number it
would get, patch preselected, plus a title and an optional description.
You never type the number: it counts up from the highest that dashboard
already has, so it can never collide with one you made before.

There are no checkboxes for which changes to include. Every commit holds
the dashboard's complete state, so the state after change 3 contains
change 2 whether you want it there or not — a gap in a selection is not
something a version could express.

Making a version writes no commit and changes nothing about the
dashboard, so it needs no confirmation.

#### Versions you never made

Two kinds appear on their own, so a dashboard is never a list with
nothing in it:

- **`v1.0.0`, once per dashboard.** The first time the integration sees a
  dashboard it marks the oldest state it has of it — the state to come
  back to before anything happened. A dashboard you create later gets its
  own at the next start of Home Assistant.
- **One per day, on the day's last state.** When the first change of a
  new day is recorded, the state that was there before it is marked and
  named after the day it belongs to, such as `5 September 2026`. A day on
  which nothing changed gets no version, and a day never gets two —
  nor does a day that ends on the state the newest version already
  holds, which is what "changed it and changed it back" leaves behind. A
  row that leads back to where you already are is one the simple view
  exists to spare you.

Both are labelled **saved automatically** in the simple view, and are
otherwise ordinary versions — same numbering, same *Back to this
version*.

The daily ones can be switched off under *Settings → Devices & services →
Dashboard History → Configure*. It takes effect at the next change, with
no restart. The `v1.0.0` is not affected by that switch, and **nothing is
ever deleted either way**: every state stays in the history, marked or
not.

#### Renaming a version

Hover a version — a row in the simple view, a section head in the
advanced one, or the box at the top where the two are drawn as one — and
a pencil appears, with a bin beside it. The pencil opens the same two
fields the create dialog asks for, prefilled: the title and the
description. Enter your correction and save.

The **number stays as it is**, and that is deliberate: the number is the
tag's name, and going back to a version is done by that name. The
reasoning, and what to do when you wanted a different number after all,
is in [the FAQ](https://github.com/PPP01/ha-dashboard-history/blob/main/FAQ.md#why-cant-i-change-a-version-number-afterwards).

A version made automatically stays marked **saved automatically** when
you rename it — the label says who made the version, not what it is
called. Nothing about the dashboard or the history changes, so renaming
needs no confirmation. A version cannot be left without a title.

#### Removing a version

The bin beside the pencil takes a version away. **The state it named
stays** — every recorded state does, marked or not, and in the advanced
view it is still a row you can go back to. What goes is the mark and the
words on it.

Unlike renaming, this **asks first**, and the question is worth reading
rather than clicking through. It names what will go — the tag, and the
title and description with it — says that the history is preserved
either way, and adds two more lines when they apply to the version in
front of you:

- **The number comes free.** Only when it was the highest: then the next
  patch hands out that same number again. A number from the middle of
  the list stays spent, so the order never shifts under a correction.
- **It will come back on its own.** For an automatic mark, the dialog
  says so when a save right now would make it again — worked out by
  running the day rule with that save in front of it, not by guessing
  from the calendar. The daily marking can be switched off entirely in
  the integration's settings, which the dialog points at.

The reason it asks at all, when renaming does not, is that this one
cannot be undone by the same route: the state comes back as a row, but
the title and description you wrote are gone with the tag. Removing and
creating again is two acts, and the second one only marks whatever state
you point it at.

Getting a number wrong is therefore not permanent — remove the version
and make the one you meant. That is also the short way out of *"I
clicked patch and meant minor"*. [The FAQ](https://github.com/PPP01/ha-dashboard-history/blob/main/FAQ.md#what-to-do-instead)
has the longer version, including why the number itself is never typed.

#### Keeping the state you are leaving

When you go back to an earlier state, the dialog offers to mark the state
you are *leaving* as a version in the same movement. In the simple view
that box is ticked by default, because somebody who only sees versions
would otherwise be leaving an unnamed state behind — and to them, an
unnamed state is gone.

**The box is not there when a version already holds that state**, which
is what you have after going back and forth without changing anything. A
mark would be a second dated name for content that has one, and the
dialog says which version holds it instead. Should you want that second
name anyway, *Version up to here* in the advanced view makes it — two
versions on one state are allowed on purpose.

The mark is made after the state you are leaving is safely in the history
and before the older one is written, which is the only moment it is the
state you actually saw.

Going back destroys nothing in any case: the tag still points at its
commit, so from an older version you can go forward to a newer one with
the same button, and working on after going back is fine.

### Describing a change

Hover a change and a pencil appears. One field, prefilled, Enter saves —
the same shape as Home Assistant's own *rename* on an integration.

Your text becomes the headline of that entry; the automatic message moves
underneath it in grey and stays there, because that is the part you can
trust when your own note from last year no longer says enough. Emptying
the field removes the description again.

The commit is **not** rewritten. A description is a git note, so every
revision you have written down anywhere stays valid.

### When a whole dashboard is gone

The deletion is recorded within about ten seconds, as `<dashboard>:
dashboard deleted`. Home Assistant fires no event for a deleted
dashboard, so it is noticed by comparison rather than as it happens:
deleting one moves a sidebar panel, and *that* is announced, which is the
cue to compare the history against what Home Assistant still has. No
restart needed.

The dashboard stays in the panel, folded away under a `Deleted (N)`
section. **Nothing is lost**, and it comes back with its cards, title,
icon and sidebar setting. Pick it there and the banner across the top
offers **Bring it back** — one click, with the same preview and
confirmation as every other way back.

The same thing through Developer Tools → Actions:

```yaml
action: dashboard_history.restore_state
data:
  dashboard: the-deleted-one
  revision: 939b93231b6f9ea7349d5c3e8a875534865facf3
  confirm: true
```

Measured against Home Assistant 2026.8.3: the dashboard is back
immediately with a byte-identical configuration, and Home Assistant
manages it as its own — you can rename or delete it from the settings
dialog straight away, with no restart.

#### Forgetting one for good

A deleted dashboard stays in the list forever, which is the point. When
you are certain you will never want one back, the *Forget for good*
button removes its history. Without confirmation you first get a count of
what would go — how many recorded states, over what period, and how many
carry a note you wrote.

This is **the only operation here that rewrites the stored history**, and
the only thing that refuses to touch a live dashboard: if Home Assistant
still has it, the answer is no.

One side effect, stated because you will notice it: git can only really
remove something by rewriting history, so every revision from the first
affected commit onwards changes, and a revision you wrote down elsewhere
will no longer resolve. Descriptions and versions of the dashboards that
stay are carried across — that part is not left to chance. The forgotten
dashboard's own versions go with it, because a version belongs to one
dashboard.

### Renames and other dashboard settings

A dashboard's title, icon and sidebar setting live in Home Assistant's
registry rather than in the dashboard configuration, and Home Assistant
announces no event when they change. They are picked up when a panel
moves — which covers creating, renaming and deleting — so a rename shows
up in the history as `renamed to "…"`, and a restored dashboard comes
back under the name it had rather than the name it started with.

### What it will not do

- **It does not record *who* made a change.** Home Assistant does not
  pass that information to integrations.
- **It is not a backup.** It covers dashboards, and nothing else.
- **It will not guess.** Where it cannot work out what belongs where, it
  refuses and says why, rather than writing something plausible. Part 2
  lists every one of those cases.
- **It does not edit your dashboards behind your back.** Nothing is ever
  written without a preview you confirmed.
- **It sees what Home Assistant sees, and nothing more.** Edit
  `.storage/lovelace.<key>` by hand and no entry appears — until the next
  restart. That is not a gap in the recorder: Home Assistant reads that
  file once and serves its own dashboard from memory afterwards, so the
  change is invisible on the dashboard too, and the next save overwrites
  it. [Part 2 has the detail](#a-change-written-straight-to-storage).
  Changes that arrive through Home Assistant — the UI, a service, the
  API, an automation — are recorded in the same moment they happen.

One thing worth knowing in plain terms: **the further back and the finer
the operation, the more the tool has to recognise things by their
content**, because Lovelace cards carry no identifier. That is why the
narrow ways back are sometimes withheld while the broad one always works.
Which cases those are, and why, is the subject of Part 2.

---

## Part 2: How it works, and where it stops

### Recognising cards without identifiers

A Lovelace card carries no identifier. Not a hidden one, not an optional
one. Counted across the eleven dashboards this was built against: **1523
cards, including the ones nested inside wrappers, and exactly 0 with an
`id`.** A card is defined purely by its position in a list.

So when two states of a dashboard are compared, the cards have to be
recognised **by their content**. Four passes do that, in this order:

1. **Identical cards pair up within the same card list.** Same content,
   same place: that card did not change.
2. **What is left over is looked for anywhere on the dashboard.** A card
   found somewhere else was *moved* — and a moved card is not missing.
3. **What is still left is paired within its own list** by a
   content-based fingerprint — entity, title, name, heading, first entity
   of a list, first line of text — choosing the **most similar**
   candidate. That card was *edited*.
4. **Anything still unpaired** is a real deletion on one side and a real
   addition on the other.

Pass 1 running before pass 2 is what keeps this honest. Delete a card
from one view while an identical card sits untouched in another, and a
global search running first would pair your deleted card with the
untouched one and lose the deletion entirely. Every card claims its own
place first.

Pass 3 choosing the *most similar* candidate rather than the first one
matters just as much. Two tile cards on the same light: you delete the
first and change the second from blue to green. The survivor matches its
own old form in three fields of four and the deleted card in two of five,
so the closer pair wins and the card offered back is the one you actually
deleted. Before this was best-match, the result was backwards — you were
offered the old version of a card still on the dashboard, and the card
you really lost was never offered at all.

### What holds the cards: views and sections

The comparison walks exactly two kinds of container, and knowing which is
which explains most of the limits further down.

| | Identified by | Stable? |
| --- | --- | --- |
| **View** | its URL path | Yes, when it has one. A view may have none. |
| **Section** | its position, cross-checked against its title | No. A section can have no path or id at all, and its title is optional. |

Counted on the same eleven dashboards: **67 views, of which 8 carry no
path**, and **24 views using the sections layout with 80 sections between
them — of which 80 carry no title.**

Anything that is not in one of those two containers is outside the
comparison altogether. In practice that means **badges**: a view's badges
are neither cards nor in a card list, so a change to them is invisible to
every part that speaks in words.

### The proof behind the undo

*Undo this change* does not merge and does not guess. It works from a
proof, and the proof is this: take the card that change produced, byte
for byte, and look for it in the dashboard as it stands today.

- Found **exactly once** — it can be pointed at without an identifier, so
  removing it and putting the old one in its place is a definite
  exchange.
- Found **twice**, or **not at all** — there is nothing to point at, or
  nothing to tell two candidates apart. The undo refuses and names the
  card.

This is what makes the undo exact rather than approximate, and it is why
it is offered on some rows and not on others. The proof is worked out
again on the confirming call, not just for the preview: somebody may have
saved while you were reading.

One consequence worth stating: the undo reaches **edits**, not only
disappearances. Reduce an `entities` card from sixty rows to one, edit the
text of a markdown card, delete a card from inside a `vertical-stack`,
rename a view's URL path — all of those are taken back exactly, verified
against the current code. What *Put back* is restricted to is
disappearances, because it is additive by definition.

#### Where the undo hides a Put back button

Where an undo already covers an item, that item's own *Put back* button is
gone, for one of two reasons and no others:

- The undo brings back exactly that one item and nothing else — a change
  that deleted a single thing. Two buttons doing literally the same thing
  is what the first person to see them side by side reported.
- The change also *added* something. Then a put-back is not merely
  redundant but wrong: an edit that touches the identifying field reads
  as one removal plus one addition, so putting the old card back would
  leave both versions standing.

What is missing because of *later* changes keeps its button, under a line
saying where it comes from.

### When a change is recorded

Three triggers watch for a change:

- **A save.** Home Assistant fires `lovelace_updated`; the recorder hears
  it and commits that one dashboard within milliseconds. The listener is
  subscribed *before* the opening pass begins, because the pass takes
  about twenty seconds on the test bench and a save made in that window
  was neither in the pass nor heard by a listener that did not exist yet.
- **A dashboard created, renamed or deleted.** None of those is a save,
  but all three move a panel, and `panels_updated` is fired. It arrives
  in bursts, so the events are collapsed into one reconciliation ten
  seconds later.
- **Startup.** Every dashboard is read and compared against the history.

Those three are the ones that watch. There is a fourth that this
integration causes itself: **before it writes a dashboard**, for a
restore or an undo, it records what is there now. That is the safety net
under every way back — see [Refusals by design](#refusals-by-design) —
and it is why going back never costs you the state you went back from.

Everything that reaches a dashboard through Home Assistant is covered by
the first trigger — the UI, a service call, the WebSocket API, an
automation, an MCP server that goes through `lovelace/config/save`. There
is no separate path for any of them.

#### A change written straight to `.storage`

Edit `.storage/lovelace.<key>` by hand and the history will not see it —
until the next restart of Home Assistant. Neither will Home Assistant.
Its own dashboard object reads the file exactly once (verified in HA
2026.8.3, `homeassistant/components/lovelace/dashboard.py`):

```python
# LovelaceStorage — the object behind a storage-mode dashboard
async def async_json(self, force: bool) -> json_fragment:
    if self._data is None:
        await self._load()
    return self._json_config or self._async_build_json()
```

Three things follow from that, and all three matter more than the
missing history entry:

- **The dashboard in your browser keeps showing the old state.** This is
  the code path the frontend itself uses for `lovelace/config`.
- **`force` does not help.** The parameter exists for YAML dashboards,
  which pass it on; in the storage path it is never read. Reloading the
  page returns the same cache, and there is no reload service for
  dashboards — `lovelace.reload_resources` covers resources only.
- **The next save overwrites your edit.** `async_save` assigns the cached
  configuration and writes the file from it, so anything you put there by
  hand is gone the moment somebody presses Save — or restores a state
  through this integration.

So editing those files is not a way to change a storage-mode dashboard,
independently of this integration. The way in from outside is the API,
and a change made that way is in the history in the same moment it is on
the dashboard.

One consequence worth naming, because this integration causes it: the
opening pass reads every storage-mode dashboard, which fills Home
Assistant's cache for all of them. Without it, a dashboard that had not
been opened since the last restart would still have `_data is None`, and
a hand-edited file would be picked up on first view. With it, that window
is closed a few seconds after startup.

### Known limits, measured

Every row below was reproduced against the current code. The last column
is the point: **no state is ever unrecoverable** — the whole-state restore
writes the recorded YAML verbatim and is untouched by any of this. What
the limits cost is the *narrow* way back, not the content.

| Situation | What the history says | Undo this change | Put back | Whole state |
| --- | --- | --- | --- | --- |
| Card with nothing to recognise it by, edited | `1 removed, 1 added` | exact | offered, **would duplicate** | works |
| Card moved *and* edited in one save | `1 removed, 1 added` | exact | offered, **would duplicate** | works |
| A badge added, changed or deleted | `no card changes`, points at the diff | **refuses** | not offered | works |
| A section renamed | `no card changes`, points at the diff | **refuses** | not offered | works |
| A whole section deleted | the section, as one item | **refuses** | offered, with proof | works |
| A section added | the cards in it, as added | **refuses** | — | works |
| Titled sections reordered | correct | **refuses** | **refuses** | works |
| **Untitled** sections reordered | correct | writes positionally | **writes into the wrong section** | works |
| A view without a URL path shifts position | can name a view that was not touched | **refuses** | **refuses** | works |
| …and was edited in the same save | the same | **refuses** | **adds it a second time**, in its older form | works |
| A view's URL path changed | `1 view removed, 1 view added` | exact | offered (adds the old view) | works |
| A path freed and reused by a new view | read as card changes inside it | writes the old cards into the new view | — | works |
| Two views sharing one path | read as cards removed, not as a view gone | **refuses** | **refuses** | works |

Four of these deserve the detail.

#### A card with nothing to recognise it by

Some cards carry no entity, no title, no name, no heading, no entity list,
no text, and no nameable card inside them. Counted on the real
installation: **54 of 1523**, mostly custom chart cards, `vertical-stack`
and `conditional`.

Edit one of those and the data cannot say whether it is the same card
changed, or the old one deleted and a new one added. Take an `iframe` card
whose URL you changed. The history reads `1 removed, 1 added`, and the two
narrow ways back do very different things.

*Undo this change* is exact:

```diff
     - type: iframe
-      url: https://example.com/new
+      url: https://example.com/old
```

*Put back* cannot be, and the preview says so before you accept:

```diff
     - type: iframe
+      url: https://example.com/old
+      aspect_ratio: 60%
+    - type: iframe
       url: https://example.com/new
       aspect_ratio: 60%
```

That is not a fault in the button. *Put back* is additive by definition,
so the only thing it can do with a card it believes was deleted is add it
back. Both halves behave exactly as designed; they simply meet a card with
no identity. Which is why, on this row, only the undo is offered.

A card **moved and edited in the same save** lands in the same place for a
different reason: pass 2 no longer recognises it (the content changed) and
pass 3 does not look across places. Making pass 3 global would close this
and open something worse — the same entity on two views is ordinary, so a
real deletion could be mistaken for a move and never be offered back at
all. A missed offer is worse than one you can decline.

#### Badges are outside the comparison

A view's badges are neither cards nor in a card list, so a change to them
produces:

```text
This change cannot be described in terms of cards - see the details
below.
```

The details it points at are behind *Show the technical details*, the
fold that carries the diff.

The diff below it is complete and correct; only the words are missing.
*Undo this change* refuses with *"this change did not alter any cards"*,
and no *Put back* is offered, because nothing it can name went missing. A
badge is recovered by setting the dashboard back to a state that had it.

#### Sections in detail

This is the weakest part of the tool, so here is every case, measured
rather than reasoned about. The pattern is simple once you see it: **what
sits *inside* a section is handled well; the section itself is barely
handled at all.**

A section as Home Assistant's editor writes it has no path and no
identifier — there is no equivalent of a view's URL path one level down.
(Home Assistant does store an `id` field on a section unchanged if one is
already there; putting identifiers into your dashboards is ruled out for
this integration, for the reasons at the end of this section.) All it has
to work with, then, is the section's index in the row, cross-checked
against its title. A title is optional, and in practice absent: all 80
sections on the installation this was developed against carry none.

**Works, and works exactly:**

| What you did | The history says | Put back | Undo |
| --- | --- | --- | --- |
| Deleted a card in a section | `1 removed`, names the card | into the right section | exact |
| Edited a card in a section | `1 edited`, names the card | — | exact |
| Dragged a card to another section | `1 moved`, *"was moved to another section"* | — | exact |
| Deleted a whole section | the section, named as one item | into the gap it left | **refuses** |

So the everyday case is sound. As long as the row of sections is as it
was, cards inside them are recognised and recoverable like any others.

**Refuses, honestly, and writes nothing:**

| What you did | Why it refuses |
| --- | --- |
| Deleted a whole section, and a neighbouring section changed since | The proof *Put back* works from is that today's sections are the ones this one stood beside — then the gap is the only place it fits. An edit next door takes that away, and the undo refuses regardless: a section has no path to recognise it by. |
| Added a section | The row of sections shifted, so every positional address is suspect. The rule is stricter than it needs to be here — appending one at the end is unambiguous — and it still refuses. |
| Reordered sections **that have titles** | The titles no longer line up with the positions, which is precisely the signal the guard looks for. It stops. |
| Renamed a section | A section's own properties are not cards. The change reads as `no card changes` and the undo says *"this change did not alter any cards."* |

A refusal is the correct outcome for all four — Home Assistant's own data
does not contain the answer, and the design forbids guessing. What it
costs is precision, not content: the whole-state restore recovers every
one of these in full, and since 2026-09-09 a deleted section also comes
back on its own as long as the sections beside it are untouched.

**Writes something nobody asked for — one case:**

Reorder **untitled** sections and change a card in the same save. The
guard compares the number of sections and their titles; with two untitled
sections swapped, the count is unchanged and both titles are still empty,
so the check passes while telling the guard nothing. *Put back* then files
the card into whichever section now occupies that index — verified: the
card lands beside the wrong neighbour, silently. The undo is not blocked
either.

This is not the only row where the tool writes a state nobody asked for
— the table has three, and it is worth knowing which:

- **This one**, untitled sections reordered. Needs nothing unusual: the
  editor produces untitled sections by default.
- **A URL path freed and handed to a new view.** Also an ordinary thing
  to do — delete a view, make another with the same path. The old cards
  are then written into the new view, because a path is unique at any
  one moment but not across a history.
- **A pathless view shifted and edited in the same save.** *Put back*
  adds it a second time, in its older form. The refusal one row above
  works by looking for the view as it was; an edited one no longer looks
  like itself. Needs a view without a URL path, which eight of 67 are.

Two things bound this row in particular:

- The trigger is a **reordering**, not an edit. Sections have to change
  places in the same save as the card change.
- **Titles remove it entirely.** With titles the same situation becomes
  the honest refusal above. This is the single most useful thing a user of
  the sections layout can do for their own safety, which is why it is
  called out in Part 1 as well.

**What would fix it properly**, and its status: an identity chain of the
integration's own — matching each save's views and sections against the
previous one (by path, then identical content, then similarity) and
committing that mapping as a third track beside the dashboard and its
metadata. It is computable retroactively, since every intermediate state
is already a commit, and it would leave `analyze.py` free of Home
Assistant. **This is an idea and nothing more.** It has not been designed,
not planned and not built, and it touches a decision in the design record
that argues from cards having no identity — so it needs that argument
revisited first. Nothing here is a commitment.

Writing identifiers into *your* dashboards was considered and ruled out:
Home Assistant offers no extension point before a save (`async_save`
writes the configuration through verbatim, and `lovelace_updated` arrives
afterwards), so the only routes are replacing its WebSocket command or
writing back after the event — the first is forbidden by this project's
own rules, the second changes other people's dashboards, doubles the
history and loses the race against an open editor.

#### Views without a URL path

Eight of 67 views carry no path, and a view without one is keyed by its
position. When the position shifts — even because a *neighbour* was
deleted — the same key means a different view.

Both write paths refuse in that case, and they say different things
because they know different things. The undo works from a plan over two
whole states, so it can see that a position has stopped meaning what it
meant:

> a view without a URL path sits somewhere else now, so an exact undo
> cannot tell which view is which

*Put back* is handed one item and the state as it stands, nothing more,
so it asks the question it can answer — is this view actually missing?
It looks for it, byte for byte, in the dashboard it is about to write:

> this view has no URL path and one just like it is on the dashboard
> already, so it did not go missing and putting it back would add a
> second copy

That is the same proof the undo works from, one object smaller. It is
also the newer of the two: until 2026-09-09 the put-back path had no
check at all, and deleting the neighbour of an untouched pathless view
offered that view back and added a second copy of it. The undo had been
guarded since 2026-09-04; the writing twin of the same case was missed.

The undo's refusal is deliberately stricter than strictly necessary — an
*added* pathless view blocks it even though its neighbours are still
unambiguous. Refusing too often is the correct error to make here.

*Put back* keeps one gap that the undo does not, and it follows from
working without the old state: a pathless view that was **both shifted
and edited** is no longer byte-identical to itself, so it does not look
like it is still there. It would be added a second time, in its older
form. Telling that apart from a view somebody really deleted needs an
identity of its own — the idea below.

What the refusal does *not* fix is the wording of the history entry. A
shifted pathless view can still be described wrongly — naming a view that
was not the one deleted. The entry misleads; the buttons no longer write.
This is the same gap the section idea above would close, and it has the
same status: an idea.

A path can also stop being an identity outright: Home Assistant's backend
does not enforce that two views carry different ones, and saved through
the API `['x', 'x']` goes in without complaint. Read into a lookup, only
the last of the two survives, and the first is invisible to every
comparison. Since 2026-09-09 both write paths refuse as soon as a path
appears twice — the whole-state restore is unaffected, and no dashboard
Home Assistant's own editor produces is in that shape.

### Refusals by design

Not everything above is a defect. These are refusals the project chose:

- **Nothing that writes a dashboard state runs without `confirm`.**
  `restore_deleted`, `restore_state` and `undo_change` each answer with a
  preview and write nothing until confirmed. `describe`,
  `create_version` and `retitle_version` write without asking — a note
  and a tag's wording, no dashboard changes, so a confirmation dialog
  would be ceremony without protection.
- **`confirm` says when it is needed, not when it alone suffices.** Two
  operations ask although no dashboard changes: `remove_version` and
  `forget`. Neither could put back what it takes — a tag's title and
  description, a rewritten history — and irreversibility is a reason of
  its own.
- **Put back never overwrites.** It is additive by definition. Where that
  is the wrong shape for what you want, the undo is the tool.
- **Undo is all or nothing.** One unresolvable step blocks the whole plan.
  A half-applied undo leaves a state nobody asked for and which the row
  beside it no longer describes.
- **The state you leave is preserved before every undo**, so the way
  forward is always open. The safety net is the history, not the preview.
- **Administrators only.** Every service is registered as an admin service
  and every WebSocket command requires admin, because a non-administrator
  cannot edit dashboards in Home Assistant either — and a preview leaks a
  dashboard's full content.
- **No `git` binary, ever.** Whether one exists differs between Home
  Assistant OS, Container, Core and Supervised.

### Services

Everything the panel does is available under Developer Tools → Actions.
Dashboards are addressed by their **key**, which is the dashboard's
`url_path` — and `_default` for the built-in default dashboard. Run
`dashboard_history.debug_snapshot` to see the keys as the integration sees
them. Note that the key is the `url_path` (`energie-2`), not the
dashboard's internal id (`energie_2`); the two are not the same string.

| Service | What it does |
| --- | --- |
| `history` | The recorded states of one dashboard, newest first, paged |
| `search` | Find changes of one dashboard by their words, over the whole history |
| `explain` | What one change did, in plain words |
| `deleted_since` | What disappeared since a revision, each with a position |
| `restore_deleted` | Put one of them back — additive (needs `confirm`) |
| `undo_change` | Take one change back and keep the ones after it (needs `confirm`) |
| `restore_state` | Set a dashboard back to an earlier state (needs `confirm`) |
| `describe` | Give a change your own description |
| `versions` | The named versions, all of them or one dashboard's |
| `next_versions` | What the next patch, minor and major would be called |
| `create_version` | Name a recorded state as a version |
| `retitle_version` | Give an existing version a new title and description |
| `remove_version` | Take a version's mark away — the state it named stays (needs `confirm`) |
| `forget` | Remove a deleted dashboard's history for good (needs `confirm`) |
| `debug_snapshot` | What the integration currently sees |

Four notes for scripting:

- `undo_change` can answer with a **refusal** rather than a preview, and
  it re-derives its proof on the confirming call — so handle both.
- `restore_state` accepts **a version's name** where it accepts a
  revision, which is how a script reaches a version the same way the panel
  does. It also takes `keep_as_version` to mark the state it is about to
  replace.
- `create_version` requires a non-empty title. A version without a name
  is a row nobody can pick out of a list again, and leaving a field blank
  is not a way of saying anything. `retitle_version` requires one for the
  same reason, so it cannot be used to take a name away — that is what
  `remove_version` is for, and it says so and asks first.
- `retitle_version` changes a version's **wording only**. The number it
  is addressed by, the state it marks and the time it was made all stay —
  so the order of the version list does not shift under a correction.
  Renaming the number is not offered at all; the reasons are in
  [the FAQ](https://github.com/PPP01/ha-dashboard-history/blob/main/FAQ.md#why-cant-i-change-a-version-number-afterwards).

### Where the data lives

In `config/dashboard_history/`, as a git repository this integration owns.
Each save is one commit, each version a tag, each description a git note.

A dashboard is two files in that commit: `<key>.yaml` for what is on it,
and `meta/<key>.yaml` for what Home Assistant knows about it — the title,
the icon, the sidebar setting. Those live in Home Assistant's registry
rather than in the dashboard configuration, which is why they need a file
of their own, and why a restored dashboard comes back under its own name.

You may look inside. Do not edit it by hand — the integration writes it
and expects to be the only writer.

**No system `git` is required.** A pure Python implementation does the
work, so it behaves identically on Home Assistant OS, Container, Core and
Supervised. Blocking work — commits, diffs, matching — runs in an executor
and never on the event loop.

#### How much space

Measured on the installation this was built against: the largest
dashboard is 262 KB as YAML, and the first recorded state of every
dashboard came to roughly 620 KB in total. A save that changes one card
adds a few kilobytes, because git stores states deduplicated and
compressed.

### Development

**A note on language.** Everything here is English: the code, the
comments, the commit messages, and anything on GitHub. One exception, and
it is deliberate — the design record under `docs/superpowers/` is written
in German. It is the author's working journal: every design decision is
numbered there together with the reasoning and the measurements behind it,
and translating that would cost the precision it is written for. Nothing
in it is needed to use this integration or to find your way around the
code; this page and the comments carry that. If you want the reasoning
behind a particular decision and do not read German, open an issue and ask
— answering in English is easy.

Six modules carry the logic and import nothing from Home Assistant —
`analyze.py`, `restore.py`, `versions.py`, `yaml_io.py`, `store.py` and
`keys.py` — so the test suite runs without an installation:

```bash
python3 -m pytest tests/ -v
```

Some cases run against **real** dashboards, which is the difference
between four invented cards and fifteen hundred grown ones. Point
`DASHBOARD_HISTORY_REAL_STORAGE` at a Home Assistant `.storage`
directory, or write the path into `tests/.real-storage`. Without either,
those cases skip *visibly* rather than passing quietly.

Everything else — the capture, the services, the WebSocket API, the panel
— needs a running Home Assistant, and every defect found in this project
so far has been in exactly those parts. There is a disposable instance for
that (see `docker/README.md`) and two things to run against it:

```bash
python3 tests/integration/run_checks.py     # the API, end to end
python3 tests/integration/look_at_panel.py  # the panel, in a real browser
```

## License

MIT — see [LICENSE](https://github.com/PPP01/ha-dashboard-history/blob/main/LICENSE).
