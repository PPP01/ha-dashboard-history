# Limitations & Boundaries

This document lists the exact, measured boundaries of **Dashboard History**, where the tool refuses to act, and why. The table and the four sections below it are enough for daily use; an [appendix](#appendix-the-full-reasoning-case-by-case) at the end goes through every case in full, for anyone who wants to know exactly why.

> [!IMPORTANT]
> **No state is ever unrecoverable.**
> The whole-state restore writes the recorded YAML verbatim and bypasses card-matching logic entirely. What these limits affect is the **precision of the surgical tools** (Undo and Put back), not your ability to recover your dashboard.

---

## Dashboards That Never Appear

Home Assistant's own default dashboard — the one titled **Overview**, present on every installation before you create any dashboard of your own — is a storage-mode dashboard like any other, but it starts out **with no configuration ever written for it**. Until it is saved for the first time, Home Assistant assembles it on the fly from your areas and entities instead of reading a stored file, and asking it for its configuration raises `ConfigNotFound` — Home Assistant's own way of saying there is nothing saved to return, not an error.

Dashboard History reads dashboards straight from Home Assistant's in-memory Lovelace objects, and it treats `ConfigNotFound` as *this dashboard was never saved*, skipping it rather than recording it as empty. The practical effect: an untouched default dashboard does not show up in Dashboard History's own dashboard list either — not hidden, not a bug, simply never handed a configuration to read.

The same is technically true of any dashboard you create yourself before its very first save — but in practice you save a custom dashboard within moments of creating it, while the default **Overview** is the one dashboard many installations never edit at all, so it is the case this actually shows up in. The moment you edit it once, in Home Assistant's own dashboard editor, Home Assistant writes its first configuration, and from then on it is tracked exactly like any dashboard you created — with full history starting from that first save. Nothing from before that edit can be recovered, because nothing before it was ever written down.

---

## Measured Behaviour Across Edge Cases

Every row below was empirically verified against the live codebase.

| Situation | What the history says | Undo this change | Put back (Compare Mode) | Whole-state restore |
| :--- | :--- | :--- | :--- | :--- |
| **Card with nothing to recognise it by**, edited | `1 removed, 1 added` | **Exact** | Offered (would duplicate) | **Works** |
| **Card moved and edited** in one save | `1 removed, 1 added` | **Exact** | Offered (would duplicate) | **Works** |
| **Badge** added, edited, or deleted | `no card changes`, diff shows change | **Refuses** | Not offered | **Works** |
| **Section renamed** | `no card changes`, diff shows change | **Refuses** | Not offered | **Works** |
| **Whole section deleted** | Cards named one by one | **Refuses** | **Restores section as one unit** | **Works** |
| **Section added** | Cards shown as added | **Refuses** | — | **Works** |
| **Titled sections reordered** | Correct | **Refuses** | **Refuses** | **Works** |
| **Untitled sections reordered** | Correct | Writes positionally | **Writes into wrong section** | **Works** |
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

### 2. Badges are outside the card comparison

Home Assistant stores badges outside the view's card list. As a result:
- Changes to badges appear in the **diff**, but the change summary reads `no card changes`.
- *Undo this change* refuses with *"this change did not alter any cards"*.
- Badges are restored using **Replace the whole dashboard**.

### 3. Sections in detail

Home Assistant assigns sections **no unique identifier and no URL path**. A section is known only by its positional index in the row.

- **Cards inside sections:** Fully supported. Moving, editing, and deleting cards within sections works exactly like regular views.
- **Deleting a whole section:** Dashboard History restores the section as a complete unit into the gap it left (provided neighboring sections were not modified).
- **Reordering untitled sections:** The only case where silent misplacement can occur. If two untitled sections swap positions, their index changes but their empty titles match, so positional restoration files cards into the section now sitting at that index.

> [!TIP]
> **Give your sections titles!**
> A title provides the identity anchor Dashboard History needs to verify section positions. With titles, an ambiguous reordering results in an honest refusal instead of an incorrect restore.

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

### Badges are outside the comparison

A view's badges are neither cards nor in a card list, so a change to
them produces:

> This change cannot be described in terms of cards — see the details
> below.

The diff underneath is complete and correct; only the words are
missing. *Undo this change* refuses with *"this change did not alter
any cards"*, and no *Put back* is offered, because nothing it can name
went missing. A badge is recovered by setting the dashboard back to a
state that had it.

### Sections in detail

This is the weakest part of the tool, so here is every case, measured
rather than reasoned about. The pattern is simple once you see it:
**what sits *inside* a section is handled well; the section itself is
barely handled at all.**

A section as Home Assistant's editor writes it has no path and no
identifier — there is no equivalent of a view's URL path one level
down. All the integration has to work with is the section's index in
the row, cross-checked against its title. A title is optional, and in
practice absent: all 80 sections on the installation this was developed
against carry none.

**Works, and works exactly:**

| What you did | The history says | Put back | Undo |
| --- | --- | --- | --- |
| Deleted a card in a section | `1 removed`, names the card | into the right section | exact |
| Edited a card in a section | `1 edited`, names the card | — | exact |
| Dragged a card to another section | `1 moved`, *"was moved to another section"* | — | exact |
| Deleted a whole section | its cards, named one by one | the section, into the gap it left | **refuses** |

*Reached through compare mode, not as a button on the row itself.*

One thing the last row does not change: the *words*. A deleted section
is offered back as one thing, but the entry in the history still lists
the cards that were on it, one by one — the explanation speaks in cards
and was not touched here. What became one item is the way back, not
the sentence above it.

So the everyday case is sound. As long as the row of sections is as it
was, cards inside them are recognised and recoverable like any others.

**Refuses, honestly, and writes nothing:**

| What you did | Why it refuses |
| --- | --- |
| Deleted a whole section, and a neighbouring section changed since | The proof *Put back* works from is that today's sections are the ones this one stood beside — then the gap is the only place it fits. An edit next door takes that away, and the undo refuses regardless: a section has no path to recognise it by. |
| Added a section | The row of sections shifted, so every positional address is suspect. The rule is stricter than it needs to be here — appending one at the end is unambiguous — and it still refuses. |
| Reordered sections **that have titles** | The titles no longer line up with the positions, which is precisely the signal the guard looks for. It stops. |
| Renamed a section | A section's own properties are not cards. The change reads as `no card changes`, and the undo says *"this change did not alter any cards."* |

A refusal is the correct outcome for all four — Home Assistant's own
data does not contain the answer, and the design forbids guessing. What
it costs is precision, not content: the whole-state restore recovers
every one of these in full, and a deleted section can also come back on
its own as long as the sections beside it are untouched.

**Writes something nobody asked for — one case:**

Reorder **untitled** sections and change a card in the same save. The
guard compares the number of sections and their titles; with two
untitled sections swapped, the count is unchanged and both titles are
still empty, so the check passes while telling the guard nothing. *Put
back* then files the card into whichever section now occupies that
index — verified: the card lands beside the wrong neighbour, silently.
The undo is not blocked either.

This is not the only situation where the tool can write a state nobody
asked for — there are four in total, worth knowing which:

- **This one**, untitled sections reordered. Needs nothing unusual: the
  editor produces untitled sections by default.
- **A URL path freed and handed to a new view.** Also an ordinary thing
  to do — delete a view, make another with the same path. The old
  cards are then written into the new view, because a path is unique
  at any one moment but not across a history.
- **A pathless view shifted and edited in the same save.** *Put back*
  adds it a second time, in its older form. The refusal below works by
  looking for the view as it was; an edited one no longer looks like
  itself. Needs a view without a URL path, which eight of 67 are, on
  the installation this was measured against.
- **A pathless view whose position another view has taken.** Then the
  item goes into that other view. Needs the same kind of pathless
  view, plus a neighbour that fits — rare, and the only one of the
  four this integration has never been able to catch.

Two things bound this in particular: the trigger is a **reordering**,
not an edit — sections have to change places in the same save as the
card change — and **titles remove it entirely**. With titles the same
situation becomes the honest refusal above. This is the single most
useful thing a user of the sections layout can do for their own safety.

**What would fix it properly, and its status:** an identity chain of
the integration's own — matching each save's views and sections against
the previous one (by path, then identical content, then similarity)
and committing that mapping as a third track beside the dashboard and
its metadata. It is computable retroactively, since every intermediate
state is already a commit. **This is an idea and nothing more** — not
designed, not planned, not built. Nothing here is a commitment.

Writing identifiers into *your* dashboards was considered and ruled
out: Home Assistant offers no extension point before a save, so the
only routes would be replacing its WebSocket command (forbidden by this
project's own rules) or writing back after the event (changes other
people's dashboards, doubles the history, and loses the race against an
open editor).

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

The undo's refusal is deliberately stricter than strictly necessary —
an *added* pathless view blocks it even though its neighbours are still
unambiguous. Refusing too often is the correct error to make here.

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

