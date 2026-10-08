# Limitations & Boundaries

This document lists the exact, measured boundaries of **Dashboard History**, where the tool refuses to act, and why. The table and the four sections below it are enough for daily use; an [appendix](#appendix-the-full-reasoning-case-by-case) at the end goes through every case in full, for anyone who wants to know exactly why.

> [!IMPORTANT]
> **No state is ever unrecoverable.**
> The whole-state restore writes the recorded YAML verbatim and bypasses card-matching logic entirely. What these limits affect is the **precision of the surgical tools** (Undo and Put back), not your ability to recover your dashboard.

> [!NOTE]
> Some of the cases below are complicated, and even harder to put into words. Many of them took me hours, days, sometimes weeks to understand and to trace through the code. I may well have misunderstood or misread some of them. That would change how a case is explained here, but not the decisions built on it: what Dashboard History restores, and what it refuses. If something looks wrong, or you have a question, please [open an issue](https://github.com/PPP01/ha-dashboard-history/issues/new/choose). Corrections are even better.

---

## Dashboards That Never Appear

Home Assistant's own default dashboard — the one titled **Overview**, present on every installation before you create any dashboard of your own — is a storage-mode dashboard like any other, but it starts out **with no configuration ever written for it**. Until it is saved for the first time, Home Assistant assembles it on the fly from your areas and entities instead of reading a stored file, and asking it for its configuration raises `ConfigNotFound` — Home Assistant's own way of saying there is nothing saved to return, not an error.

Dashboard History reads dashboards straight from Home Assistant's in-memory Lovelace objects, and it treats `ConfigNotFound` as *this dashboard was never saved*, skipping it rather than recording it as empty. The practical effect: an untouched default dashboard does not show up in Dashboard History's own dashboard list either — not hidden, not a bug, simply never handed a configuration to read.

The same is technically true of any dashboard you create yourself before its very first save — but in practice you save a custom dashboard within moments of creating it, while the default **Overview** is the one dashboard many installations never edit at all, so it is the case this actually shows up in. The moment you edit it once, in Home Assistant's own dashboard editor, Home Assistant writes its first configuration, and from then on it is tracked exactly like any dashboard you created — with full history starting from that first save. Nothing from before that edit can be recovered, because nothing before it was ever written down.

Built-in pages such as Energy, Activity, History, Media and To-do are not dashboards at all: they ship with Home Assistant itself and have no dashboard configuration to read, so they never appear in the list and never will. Only dashboards that carry a stored configuration do.

---

## Measured Behaviour Across Edge Cases

Every row below was empirically verified against the live codebase.

The real-world figures quoted here and elsewhere in the documentation (how many cards, sections or views were counted) are snapshots of the author's own installation at different points in time. They differ from one place to the next because the installation was in a different state each time, so read them as an order of magnitude, not as one consistent data set.

| Situation | What the history says | Undo this change | Put back (Compare Mode) | Whole-state restore |
| :--- | :--- | :--- | :--- | :--- |
| **Card with nothing to recognise it by**, edited | `1 removed, 1 added` | **Exact** | Offered (would duplicate) | **Works** |
| **Card moved and edited** in one save | `1 removed, 1 added` | **Exact** | Offered (would duplicate) | **Works** |
| **Badge** added, edited, moved or deleted | Named, e.g. *the badge entity: sun.sun was added* | **Exact** while the badge is unchanged since | Not offered | **Works** |
| **View or dashboard setting** changed (`icon`, `strategy:` key, …) | Named, e.g. *the setting "icon" was changed* | **Exact** while the value is unchanged since | Not offered | **Works** |
| **Section settings changed** (`title`, `column_span`, …) | Named, e.g. *section "X": the setting "title" was changed …* | **Exact** while the section is unchanged since | Not offered | **Works** |
| **Section added** | `1 section added` | **Exact** while the section is unchanged since; refuses if the sections around it were rearranged since | — | **Works** |
| **Whole section deleted** (one with at least one card) | `1 section removed` | **Exact**; if the sections around it were rearranged or deleted since, it comes back as the **last** section of the view and the button shows an asterisk | Offered as one item; parks the same way | **Works** |
| **Several whole sections deleted** in one save | Their cards, one line each | **Refuses** | Parks the cards in "Imported cards" | **Works** |
| **Sections swapped or moved** as whole blocks, titled or not, nothing else changed | `1 section moved` — one line per section, named by its heading if it has one | **Exact** — the whole row of sections is written back in one step, settings included; refuses if the sections around them were rearranged since | Nothing missing, nothing offered | **Works** |
| **Sections rearranged after the change**, card edited or deleted by it | Correct | **Parks** the card in "Imported cards" — button shows *Undo this change\** — except sections alike in every setting, which still write silently to the old index (see below) | Parks in "Imported cards", same exception | **Works** |
| **Section moved and edited in the same save**, or sections reordered together with a card edit | Its cards, one line each | **Refuses** — nothing proves it is the same section | Parks in "Imported cards" | **Works** |
| **View without URL path** shifts position | May name an untouched view | **Refuses** | **Refuses** | **Works** |
| …and was edited in the same save | Same | **Refuses** | Adds older copy as duplicate | **Works** |
| …and another view occupies its index | Same | **Refuses** | Writes into other view | **Works** |
| **View URL path changed** | `1 view removed, 1 view added` | **Exact** | Adds older view copy | **Works** |
| **Path freed and reused** by a new view | Treated as card edits | Writes old cards into new view | — | **Works** |
| **Two views sharing one path** | Treated as cards removed | **Refuses** | **Refuses** | **Works** |

---

## The Four Major Edge Cases

### 1. Cards with nothing to recognise them by

Some cards contain no entity, title, name, heading, list, or text. Across 1,523 real-world cards tested, **54 had no identifying fields** (primarily custom chart wrappers, blank `vertical-stack` containers, or `conditional` cards).

If you edit one of these (e.g. changing an `iframe` URL), the algorithm cannot prove whether the card was modified or replaced.
- **Undo this change:** Works **exactly**, because it looks for the specific post-change YAML representation.
- **Put back:** Because *Put back* is purely additive, restoring what it thinks was deleted would add the old version alongside the new version. The preview clarifies this before you accept.

### 2. Badges are matched in a world of their own

Home Assistant stores badges beside the view's card list, and like cards they carry no identifier. They are matched the way cards are, but never paired with a card — an `entity` badge and an `entity` card can be byte-identical ([issue #29](https://github.com/PPP01/ha-dashboard-history/issues/29)). As a result:
- A badge change is named in the explanation (*the badge entity: sun.sun was added*) and counted in the history line (`1 badge changed`).
- *Undo this change* takes it back while the badge is unchanged since. The same badge commonly stands on several views, so it is looked for on the whole dashboard and then in the view the change left it in; where neither settles it, the undo refuses.
- A deleted badge counts as already back only if its own view has more of it today than the change left — a copy on another view is not it.
- *Put back* does not offer badges.

### 3. Sections in detail

Home Assistant assigns sections **no unique identifier and no URL path**. A section is known only by its positional index in the row.

- **Cards inside sections:** Fully supported. Moving, editing, and deleting cards within sections works exactly like regular views.
- **Deleting a whole section:** Dashboard History restores the section as a complete unit into the gap it left. If the sections around it were rearranged since, it comes back as the last section of the view instead, and the button shows an asterisk.
- **Reordering sections:** Sections are matched as whole blocks before their cards ([issue #31](https://github.com/PPP01/ha-dashboard-history/issues/31)). A section swapped, moved, added or deleted in one save reads as one line — *section "Heizung" was moved* — and *Undo this change* writes the whole row of sections back in one step, own settings included. It refuses where it cannot prove that: a section moved **and** edited in the same save, two sections deleted at once, or the sections around a moved or added one rearranged since.

> [!TIP]
> **When a section cannot be recognised, the card is parked, not guessed.**
> A section is recognised by its position, its own settings (everything but its cards — `column_span`, `title` and the like) and the cards that should still stand beside the one being put back. When that no longer fits because the sections were rearranged since, the card goes into the view's "Imported cards" area, shown in Home Assistant's edit mode, and the undo button reads *Undo this change\**; you drag it into place yourself. A title is just one more setting in that comparison. It still earns its place in one case only: two sections that would otherwise agree on every setting, which the comparison cannot tell apart on its own (see the appendix).

### 4. Views without a URL path

On the installation this was built against, 8 of 67 views have no URL path (relying on positional index). If an earlier view is deleted, the positional index of subsequent pathless views shifts.
- Both *Undo* and *Put back* detect when positional shifts make identity ambiguous and **refuse** rather than risk corrupting your layout.
- Use **Replace the whole dashboard** to recover pathless view structures cleanly.

---

## Refusals by Design

Not all refusals are technical gaps; many are safety guarantees built into the architecture:

1. **No action runs without preview and confirmation:** Any operation that alters dashboard YAML or history requires an explicit `confirm: true`.
2. **Put back never overwrites:** It is strictly additive. It will never overwrite an existing card.
3. **Undo is all-or-nothing:** If a change touched three cards and one cannot be resolved safely, the entire undo refuses. Partial undos are forbidden.
4. **Current state is preserved before restoring:** Before executing any restore, the current live state is checked against the recorded history and committed if it is not there yet. If that cannot be confirmed — the repository is briefly unreadable or unwritable — the restore is refused by default rather than risking it; a second, explicit confirmation offers to write anyway. See the [FAQ](../FAQ.md#what-does-write-anyway-mean-when-a-restore-is-refused) for how often that actually happens.
5. **Admin-only access:** Every service and WebSocket command requires Home Assistant administrator privileges. Non-admins cannot inspect history or trigger restores.
6. **No guessing:** When content-based proofs fail, Dashboard History refuses honestly and directs you to whole-state restore or Compare Mode.

---

## Appendix: The Full Reasoning, Case by Case

The summary above is enough to use the tool safely. What follows is the
complete reasoning behind it — every measurement, every refusal message,
and the one case where the tool can write a state nobody asked for.
Worth reading if you want to know *why*, not just *what*.

### A card with nothing to recognise it by

Some cards carry no entity, no title, no name, no heading, no entity
list, no text, and no nameable card inside them. Counted on the real
installation: **54 of 1,523**, mostly custom chart cards, `vertical-stack`
and `conditional`.

Edit one of those and the data cannot say whether it is the same card
changed, or the old one deleted and a new one added. Take an `iframe`
card whose URL you changed. The history reads `1 removed, 1 added`, and
the two narrow ways back do very different things.

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
so the only thing it can do with a card it believes was deleted is add
it back. Both halves behave exactly as designed; they simply meet a
card with no identity — which is why only the undo is offered on this
row.

A card **moved and edited in the same save** lands in the same place
for a different reason: Pass 2 (see [How It Works](how-it-works.md)) no
longer recognises it, because the content changed, and Pass 3 does not
look across containers. Making it global would close this and open
something worse — the same entity on two views is ordinary, so a real
deletion could be mistaken for a move and never be offered back at all.
A missed offer is worse than one you can decline.

### Badges

A view's badges are matched like cards, in a world of
their own — see section 2 above. What remains is *Put back*: it never
offers a badge. A deleted badge comes back through *Undo this change*,
or by setting the dashboard back to a state that had it.

### Sections in detail

This is the weakest part of the tool, so here is every case, reproduced against the code. The pattern is simple once you see it: **what sits *inside* a section is handled well; the section itself is handled as a whole block, but only as long as its neighbours stay put.**

A section as Home Assistant's editor writes it has no path and no identifier — there is no equivalent of a view's URL path one level down. All the integration has to work with is the section's index in the row, cross-checked against its own settings and, for *Put back*, against the cards that stood beside the one being restored. A title would help, but is optional and in practice absent: 0 of 101 sections on the installation this was developed against carry one. Where the check fails, the card is parked in "Imported cards" rather than guessed into a section.

Sections are matched before their cards, as whole blocks ([issue #31](https://github.com/PPP01/ha-dashboard-history/issues/31)). That is why a swap reads as one move and not as a handful of card moves.

**Works, and works exactly:**

| What you did | The history says | Put back | Undo |
| --- | --- | --- | --- |
| Deleted a card in a section | `1 removed`, names the card | into the right section | exact |
| Edited a card in a section | `1 edited`, names the card | — | exact |
| Dragged a card to another section | `1 moved`, *"was moved to another section"* | — | exact |
| Deleted a whole section | *section 2 was removed* | the section, into the gap it left | exact |
| Added a whole section | *section 3 was added* | — | exact |
| Swapped or moved sections | *section "C" was moved* | — | exact — the whole row is written back in one step |
| Changed a section's settings (`title`, `column_span`, …) | *the setting "title" was changed from "X" to "Y"* | — | exact |

*Put back* for a whole section is reached through compare mode, not as a button on the row itself. In every row, "exact" holds while what the change left is still there unchanged: a section edited again since refuses with *was changed again after this*.

**Refuses, honestly, and writes nothing:**

| What you did | Why it refuses |
| --- | --- |
| Moved a section **and** edited it in the same save — or reordered sections and edited a card in the same save | Nothing proves the edited section is the same one. *Put back* parks the cards in "Imported cards" instead. |
| Deleted two or more whole sections in one save | Each would have to go back to a place nothing identifies. *Put back* parks the cards. |
| Moved or added sections, **and** the sections around them were added, deleted or reordered since | The row of sections is written back in one piece, in the order it had before the change; that order only means the same thing while the sections around it still stand as the change left them. Card edits in other sections since do not refuse. |
| Converted a view's layout (masonry to sections, typically) | Home Assistant adds an empty grid section on conversion; the undo names the conversion as the reason ([issue #32](https://github.com/PPP01/ha-dashboard-history/issues/32)). The history entry reads "the view … was converted from masonry to sections." |

A refusal is the correct outcome for all four — Home Assistant's own data does not contain the answer, and the design forbids guessing. What it costs is precision, not content: the whole-state restore recovers every one of these in full.

Where sections were only rearranged or deleted *after* the change, nothing is refused: a card that has to go back into a section there is parked in "Imported cards", and a deleted whole section comes back as the last section of its view, with an asterisk on the button ([issue #30](https://github.com/PPP01/ha-dashboard-history/issues/30)). The one exception is below.

**Writes something nobody asked for — four cases.** In all four a narrow tool writes into a place that is not the card's own:

- **A section alike in every setting stands at the old index since,** whether by a reorder or because the original was deleted and an identical one created in its place. Neither the guard nor the anchor can tell such sections apart — a swap is not required, a single deletion and a single, coincidentally identical section are enough. *Undo this change* puts an edited or deleted card back at its old index — where it was on screen, but inside whichever section stands there now, and without an asterisk. *Put back* does the same only where no card beside the restored one is left to tell the sections apart, typically when the section now at that index is empty; where a neighbour of the card now stands in another section alike in every setting, it parks instead. Needs sections that differ in nothing but their cards — a plain `type: grid`, the editor's default.
- **A URL path freed and handed to a new view.** An ordinary thing to do — delete a view, make another with the same path. The old cards are then written into the new view, because a path is unique at any one moment but not across a history.
- **A pathless view shifted and edited in the same save.** *Put back* adds it a second time, in its older form. The refusal below works by looking for the view as it was; an edited one no longer looks like itself. Needs a view without a URL path, which eight of 67 are, on the installation this was measured against.
- **A pathless view whose position another view has taken.** Then the item goes into that other view. Needs the same kind of pathless view, plus a neighbour that fits — rare, and the only one of the four this integration has never been able to catch.

The first case needs a **reordering** after the change, not an edit, and sections that agree on every setting. Anything that sets them apart — a `column_span`, or a title of its own — turns the same situation into a parked card with an asterisk. That is what is left of the old advice to give sections titles: it closes this last case for sections that would otherwise be identical.

**What would fix it properly, and its status:** an identity chain of the integration's own — matching each save's views and sections against the previous one (by path, then identical content, then similarity) and committing that mapping as a third track beside the dashboard and its metadata. It is computable retroactively, since every intermediate state is already a commit. **This is an idea and nothing more** — not designed, not planned, not built. Nothing here is a commitment.

Writing identifiers into *your* dashboards was considered and ruled out: Home Assistant offers no extension point before a save, so the only routes would be replacing its WebSocket command (forbidden by this project's own rules) or writing back after the event (changes other people's dashboards, doubles the history, and loses the race against an open editor).

### Views without a URL path

A view without a URL path is keyed by its position. When the position
shifts — even because a *neighbour* was deleted — the same key means a
different view.

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

That is the same proof the undo works from, one object smaller.

Until 2026-09-24 the undo's refusal was stricter than strictly
necessary — an *added* pathless view blocked it even where its
neighbours stayed unambiguous, appended at the very end or not, because
the check compared the whole set of positions between the two states
rather than where they stopped agreeing.
[GitHub issue #33](https://github.com/PPP01/ha-dashboard-history/issues/33)
narrowed that: positions are now only compared up to the length of the
shorter state, so a view appended after that point cannot taint
anything before it. A dashboard with exactly one view in both states is
never refused on position grounds at all: there is nothing it could be
mistaken for, path or title or not. An insertion or a deletion *within* that shared
length still refuses, deliberately — both change the view count the
same way an append does, and only whether the position's content still
matches at that length tells them apart.

*Put back* keeps one gap that the undo does not, and it follows from
working without the old state: a pathless view that was **both shifted
and edited** is no longer byte-identical to itself, so it does not look
like it is still there. It would be added a second time, in its older
form. Telling that apart from a view somebody really deleted needs an
identity of its own — the same idea as above.

There is a second shape of the same gap, and it is the worse one: the
position is looked up in the state as it stands, and if another view
has moved into it and its own shape fits what the proof asks for, the
item is written into *that* view, silently. This is not new and not
particular to sections — the anchor a card carries has always been open
to it. Both wait on the same idea above.

What the refusal does *not* fix is the wording of the history entry. A
shifted pathless view can still be described wrongly — naming a view
that was not the one deleted. The entry misleads; the buttons no longer
write.

A path can also stop being an identity outright: Home Assistant's
backend does not enforce that two views carry different ones. Read into
a lookup, only the last of the two survives, and the first is invisible
to every comparison. Both write paths refuse as soon as a path appears
twice — the whole-state restore is unaffected, and no dashboard Home
Assistant's own editor produces is in that shape.

