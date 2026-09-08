# Dashboard History

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

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
  empty.
- **Your own notes on any change.** One field. Your text becomes the
  headline of that entry.
- **Search**, across the whole recorded history of a dashboard, including
  your own notes and version titles.
- **Deleted a whole dashboard?** It comes back — cards, title, icon and
  sidebar setting.
- **Nothing is written without a preview** and an explicit confirmation.

### Installing

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

A button in the top right switches between them, and your choice is
remembered.

**Simple view** shows nothing but the versions — the named states. This
is the one to use when you want *"put it back to how it was on Tuesday"*
and nothing more. Each version is a section you can fold open to see the
changes inside it.

At the top of it sits the state you have now, marked `current state`.
That mark is unconditional here, unlike the one on a row above: this box
*is* what you have, whatever the history does or does not agree with.
It names the version you are standing in, or says that the dashboard
has changed since the last one was saved — and in that case it offers a
single button, **Undo / Go back to v1.2.0**, which takes the dashboard
off everything since that version in one step. Like every other way
back it shows you the diff first, and what you are leaving is kept: it
stays in the history as its own entry, and the dialog offers to name it
as a version too. The box folds open as well, and lists the changes
made since that version.

**Advanced view** shows every recorded change, newest first, twenty-five
at a time with a *Load older changes* button. The versions still appear,
as headers that cut the list into sections.

#### Search

A search box sits above the list and searches what the current view
shows: in the simple view, the versions; in the advanced view, the
changes that are loaded. If the answer is not among them, a button offers
**Search the whole history** — that goes to the server and walks the
entire recorded past, looking at the automatic message, any note you
wrote yourself, and the title, description and number of any version on
that state.

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
- **Deleting a whole section** cannot be taken back with the narrow
  tools: neither *Put back* nor *Undo this change* will do it, and both
  say why. The whole-state restore brings it back in full.
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
  which nothing changed gets no version, and a day never gets two.

Both carry the label `automatic`, and are otherwise ordinary versions —
same numbering, same *Back to this version*.

The daily ones can be switched off under *Settings → Devices & services →
Dashboard History → Configure*. It takes effect at the next change, with
no restart. The `v1.0.0` is not affected by that switch, and **nothing is
ever deleted either way**: every state stays in the history, marked or
not.

#### Keeping the state you are leaving

When you go back to an earlier state, the dialog offers to mark the state
you are *leaving* as a version in the same movement. In the simple view
that box is ticked by default, because somebody who only sees versions
would otherwise be leaving an unnamed state behind — and to them, an
unnamed state is gone.

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
icon and sidebar setting:

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

This is **the only thing here that cannot be undone**, and the only thing
that refuses to touch a live dashboard: if Home Assistant still has it,
the answer is no.

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
| A whole section deleted | its cards, listed as deleted | **refuses** | **refuses** | works |
| A section added | the cards in it, as added | **refuses** | — | works |
| Titled sections reordered | correct | **refuses** | **refuses** | works |
| **Untitled** sections reordered | correct | writes positionally | **writes into the wrong section** | works |
| A view without a URL path shifts position | can name a view that was not touched | **refuses** | — | works |
| A view's URL path changed | `1 view removed, 1 view added` | exact | offered (adds the old view) | works |
| A path freed and reused by a new view | read as card changes inside it | writes the old cards into the new view | — | works |
| Two views sharing one path | the first is invisible to the analysis | — | — | works |

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
This change cannot be described in terms of cards — see the technical
details below.
```

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

So the everyday case is sound. As long as the row of sections is as it
was, cards inside them are recognised and recoverable like any others.

**Refuses, honestly, and writes nothing:**

| What you did | Why it refuses |
| --- | --- |
| Deleted a whole section | `find_removed` knows `view` and `card`, not `section`. Its cards are offered individually, and each refuses: *"the section this card sat in is not the one standing at that place now, so putting it back would file it in a stranger."* The undo refuses for the same reason. |
| Added a section | The row of sections shifted, so every positional address is suspect. The rule is stricter than it needs to be here — appending one at the end is unambiguous — and it still refuses. |
| Reordered sections **that have titles** | The titles no longer line up with the positions, which is precisely the signal the guard looks for. It stops. |
| Renamed a section | A section's own properties are not cards. The change reads as `no card changes` and the undo says *"this change did not alter any cards."* |

A refusal is the correct outcome for all four — Home Assistant's own data
does not contain the answer, and the design forbids guessing. What it
costs is that a deleted section has **no narrow way back at all**: not
*Put back*, not *Undo*. The whole-state restore recovers it in full.

**Writes something nobody asked for — one case:**

Reorder **untitled** sections and change a card in the same save. The
guard compares the number of sections and their titles; with two untitled
sections swapped, the count is unchanged and both titles are still empty,
so the check passes while telling the guard nothing. *Put back* then files
the card into whichever section now occupies that index — verified: the
card lands beside the wrong neighbour, silently. The undo is not blocked
either.

This is the one row in the whole table where the tool writes a state
nobody asked for. Two things bound it:

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

Every write path refuses in that case:

> a view without a URL path sits somewhere else now, so an exact undo
> cannot tell which view is which

The refusal is thorough: it covers the case where the pathless view was
not touched at all, and it is deliberately stricter than strictly
necessary — an *added* pathless view blocks an undo even though its
neighbours are still unambiguous. Refusing too often is the correct error
to make here.

What the refusal does *not* fix is the wording of the history entry. A
shifted pathless view can still be described wrongly — naming a view that
was not the one deleted. The entry misleads; the buttons no longer write.
This is the same gap the section idea above would close, and it has the
same status: an idea.

### Refusals by design

Not everything above is a defect. These are refusals the project chose:

- **Nothing that writes a dashboard state runs without `confirm`.**
  `restore_deleted`, `restore_state` and `undo_change` each answer with a
  preview and write nothing until confirmed. `describe` and
  `create_version` are the exceptions, and they write a note and a tag —
  no dashboard changes, so a confirmation dialog would be ceremony
  without protection.
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
| `forget` | Remove a deleted dashboard's history for good (needs `confirm`) |
| `debug_snapshot` | What the integration currently sees |

Three notes for scripting:

- `undo_change` can answer with a **refusal** rather than a preview, and
  it re-derives its proof on the confirming call — so handle both.
- `restore_state` accepts **a version's name** where it accepts a
  revision, which is how a script reaches a version the same way the panel
  does. It also takes `keep_as_version` to mark the state it is about to
  replace.
- `create_version` requires a non-empty title. A version without a name is
  a row nobody can pick out of a list again, and nothing in this
  integration deletes a tag.

### Where the data lives

In `config/dashboard_history/`, as a git repository this integration owns.
Each dashboard is one YAML file, each save one commit, each version a tag,
each description a git note.

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

Four modules carry the logic and import nothing from Home Assistant —
`yaml_io.py`, `analyze.py`, `restore.py` and `versions.py` — so the test
suite runs without an installation:

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

MIT — see [LICENSE](LICENSE).
