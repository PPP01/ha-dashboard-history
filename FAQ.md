# Frequently asked questions

Questions that come up often enough to be worth writing down once —
with the reasoning, not just the rule. Where a decision was made
deliberately, this says what it buys and what it costs, so you can tell
a design choice from something nobody got round to.

The README is the place to start; this is for the things you only wonder
about once you are using it.

## Contents

**Versions**

- [Why can't I change a version number afterwards?](#why-cant-i-change-a-version-number-afterwards)

**Deleting dashboards**

- [Why does forgetting a dashboard take so long?](#why-does-forgetting-a-dashboard-take-so-long)
- [How long does forgetting a dashboard take?](#how-long-does-forgetting-a-dashboard-take)
- [Why is the whole panel locked while one dashboard is forgotten?](#why-is-the-whole-panel-locked-while-one-dashboard-is-forgotten)
- [How much disk space does forgetting a dashboard free?](#how-much-disk-space-does-forgetting-a-dashboard-free)
- [How do I get back a dashboard I forgot for good?](#how-do-i-get-back-a-dashboard-i-forgot-for-good)

## Versions

### Why can't I change a version number afterwards?

Because the number is not a field on the version. It **is** the
version's name.

A version is an annotated git tag called `my-dashboard/v1.2.0`. The
title and the description are text stored inside that tag, which is why
you can rewrite them whenever you like — hover the version and use the
pencil, in either view. The number is the tag's name, and three things
hang off it:

**Going back to a version is done by that name.** Restoring is
`dashboard_history.restore_state` with `my-dashboard/v1.2.0` as the
revision. If you have written that name into an automation, a script or
a note to yourself, renaming the version breaks it — and breaks it
silently, because a name that no longer exists looks exactly like a
typo. Nothing would tell you that the thing you addressed is still
there under a different number.

**The numbers only mean anything because they never move.** A new
version always counts up from the highest number that dashboard already
has, even after you have gone back to an older state. That is what makes
a collision impossible, and it is why a higher number always means a
later decision. Renaming a version downwards would put the same number
on two different states over the life of a dashboard: `v1.0.3` in your
notes from March and `v1.0.3` on the screen today would be two different
things, with nothing in between to say so.

**A tag name is a technical artefact, and its rules are not obvious.**
git will not take a space, a `..`, or any of `~^:?*[` in a ref name. Nor
can a dashboard have a flat tag `my-dashboard` while
`my-dashboard/v1.0.0` exists, because a ref file and a ref directory are
the same path — the attempt fails with a different error depending on
which way round you do it. A dialog that let you type the name would
have to explain all of this, or refuse things for reasons that read as
arbitrary. Three buttons carrying the finished numbers explain
themselves.

#### What to do instead

**Put a second version beside the first.** That is one click, it costs
nothing, and it loses nothing: the old version stays exactly where it
is, still pointing at its state. Two versions on one state is allowed
and normal — after going back to an older state, a fresh name for it is
often precisely what you want.

This works because versions group and never squash. Nothing is
overwritten and nothing is thrown away, so an extra name is never the
destructive option that renaming would be.

**Or take the wrong one away.** Since a version can be removed, a
number that was given out by mistake is not a permanent fixture: remove
the version and the mark is gone, while the state it pointed at stays
in the history exactly where it was. If the one you remove carries the
highest number, that number is free again — the next patch will use it.
And removing it is the short way out of "I clicked patch and meant
minor": take the mistaken version away, then create the one you meant.

What this does not do is move a version. Removing one and creating
another is two acts, and the second is addressed at whatever state you
point it at. That is the difference from renaming a number, and it is
the reason the number still is not typed.

#### What you *can* change, at any time

- The **title** and the **description** of any version, in both views,
  through the pencil on the version — or with the
  `dashboard_history.retitle_version` service.
- A version made automatically keeps its `automatic` label when you
  rename it. The label says who made the version, not what it is
  called.
- Which **state** a version marks never changes. Renaming rewrites the
  wording and touches neither the dashboard nor the history, so it needs
  no confirmation, exactly like describing a change.
- Whether a version exists **at all**, in both views, through the bin on
  the version — or with the `dashboard_history.remove_version` service.
  It asks first, and without `confirm` it answers with the words it
  would take. The state stays either way; what cannot be written back
  is the title and description, so the confirmation is there to be read
  rather than clicked through.

One thing cannot be undone by this route: a version cannot be left
without a title. Emptying the field is refused rather than accepted,
because a version with no name is a row you cannot pick out of a list
again — and because leaving a field blank is not a way of saying
anything. If what you want is for the version to be gone, the bin says
that plainly and asks you first; a form whose emptiness destroys
something would be a trap.

## Deleting dashboards

### Why does forgetting a dashboard take so long?

Because git cannot remove anything without rewriting it.

A commit's identity is a hash of what it contains, including its
parent. Take one file out of one commit and that commit becomes a
different commit — and so does every commit after it, all the way to
the newest. There is no way to cut a dashboard out of the middle and
leave the rest untouched; that is not a shortcoming of this integration
but what a hash chain is.

So `forget` walks the whole history, writes every commit again without
that dashboard's files, moves the version marks onto the new commits,
and finally collects what nothing points at any more. Deleting the
files and leaving it at that is not an option: the old commits would
still be there, and the text you asked to be forgotten would still be
readable.

### How long does forgetting a dashboard take?

**It depends on the size of your whole history, not on the size of the
dashboard you are deleting.** That is the part that surprises people,
and the dialog makes it worse by showing how many states the doomed
dashboard has — nine states cost the same as a thousand, because what
is being rewritten is everything else.

Measured on a real installation with 7403 commits, 70 dashboards and
782 version marks: **14.7 seconds**, split roughly

- 45 % rewriting the commits,
- 45 % collecting what became unreachable,
- 2 % moving the version marks.

A small history is done in a second or two. A much larger one takes
proportionally longer. The panel counts along while it works, so you
can see it moving rather than guess.

*(The version marks used to be the expensive part by far — 58 % of the
whole operation, because each one was written to disk on its own. Since
v0.7.1 they go in a single batch, which is where most of the former
26.6 seconds went.)*

### Why is the whole panel locked while one dashboard is forgotten?

Two reasons, and the second one is the one that is easy to miss.

**Nothing you could do there would be true.** Every revision is
changing while the rewrite runs. A history opened in that moment lists
states by identifiers that are about to stop existing, and a button
pressed there would act on one of them.

**Clicking makes it slower — measured, by a factor of three.** The
rewrite and every question the panel asks are Python running in the
same Home Assistant process, and they take turns. The same forget took
24 seconds when left alone and 76 seconds while the panel kept asking
for histories in the background. Taking the controls away is not
protectiveness; it is what makes the wait as short as it can be.

Home Assistant itself is unaffected throughout — only this page waits.
A dashboard you save in the meantime is recorded as usual, once the
rewrite is out of the way.

### How much disk space does forgetting a dashboard free?

Close to nothing. If clearing space is the reason you are reaching for
it, the numbers are worth seeing first: this is the one step here that
cannot be undone, and it is a poor way to buy a megabyte.

Measured on the same installation as the timings above — 7518 recorded
revisions, **9.2 MB** for the entire history, against 1.1 MB for the
dashboards themselves the way Home Assistant stores them. Two
dashboards were then forgotten, each starting from that same history:

- **The busiest one** — 850 of the 7518 revisions were its own —
  freed **0.71 MB, or 7.7 %**.
- **The largest one** — ten states, 1.6 MB of YAML between them —
  freed **0.47 MB, or 5.1 %**.

Three things keep that small.

**A state that did not change is stored once.** A revision is recorded
whenever anything is saved, but a dashboard nobody touched costs
nothing at that revision: it is the same state, kept once and pointed
at again. A dashboard left alone for a year takes up one copy, not a
year's worth.

**What is kept is compressed and written as differences.** The ten
states of that largest dashboard are 1.6 MB as YAML and 0.18 MB
compressed — and less again stored against each other, because two
consecutive states of the same dashboard usually differ by a line or
two.

**Most of the history is not dashboard text at all.** All the distinct
states of every dashboard together come to 2.8 MB of YAML, inside a
9.2 MB history. The rest is what recording a revision costs whatever
is in it — who, when, and how it hangs off the revision before —
around 0.8 KB each. Forgetting a dashboard reclaims that only for
revisions that existed for it alone, and that, rather than the text,
is where nearly all of the 0.71 MB above came from: 850 such
revisions, against 17 KB of actual content.

So the little you get back follows how often a dashboard was changed,
not how big it is. And if the history really has outgrown its disk,
what to remove is the history, not one dashboard inside it: it is a
single directory, `dashboard_history`, next to your
`configuration.yaml`. Deleting it with Home Assistant stopped gives
back every megabyte at once, and an empty history starts again with
the next save.

### How do I get back a dashboard I forgot for good?

You don't.

*Wat fott es, es fott.*

The only way back is a working backup of your Home Assistant
configuration. This is the one operation in this integration that takes
something away permanently — everything else only ever adds, which is
why it is the only one that asks you twice and says so in bold.

If what you actually want is for a deleted dashboard to stop cluttering
the list, that is what the list's **Deleted** fold is for. It keeps the
history and keeps it out of your way.
