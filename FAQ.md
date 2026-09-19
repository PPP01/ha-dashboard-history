# Frequently asked questions

Questions that came up often enough to be worth writing down once —
with the reasoning behind them, not just the rule. Where I decided
something deliberately, I say what it buys and what it costs, so you
can tell a design decision from something I never got round to.

The README is the place to start; this picks up where it leaves off —
whether you need this at all beside a backup or a git repository, and
the things you only wonder about once you are using it.

## Contents

**Backups and git**

- [I already have Home Assistant backups. Why this too?](#i-already-have-home-assistant-backups-why-this-too)
- [My Home Assistant is already in a git repository. Why this too?](#my-home-assistant-is-already-in-a-git-repository-why-this-too)

**Versions**

- [Why can't I change a version number afterwards?](#why-cant-i-change-a-version-number-afterwards)

**Deleting dashboards**

- [Why does forgetting a dashboard take so long?](#why-does-forgetting-a-dashboard-take-so-long)
- [How long does forgetting a dashboard take?](#how-long-does-forgetting-a-dashboard-take)
- [Why is the whole panel locked while one dashboard is forgotten?](#why-is-the-whole-panel-locked-while-one-dashboard-is-forgotten)
- [How much disk space does forgetting a dashboard free?](#how-much-disk-space-does-forgetting-a-dashboard-free)
- [How do I get back a dashboard I forgot for good?](#how-do-i-get-back-a-dashboard-i-forgot-for-good)

## Backups and git

### I already have Home Assistant backups. Why this too?

Because the two answer different questions, and I want both.

My backup answers "the installation is gone" — dead SD card, an update
that went sideways, a move to new hardware. Mine has saved me once
already; that story is in the next question. What it is bad at is the
other question, the one I have far more often: "the installation is
fine, but the card I had yesterday is not." To get that one card out of
a backup I have to take the whole of last night with it, including
everything I got right this morning.

Two things make that worse than it sounds.

**A backup only knows the moments it ran.** Nightly, for most of us.
Whatever you built and then lost between two of those runs was never in
a backup at all — and that is often the half hour it happens in, when
you are rearranging a view, watching the layout rather than what you
just dragged off the screen, and you save. This integration writes a
revision at the moment a dashboard is saved. Every save, nothing to
remember.

**The smallest thing a backup can hand back is a whole file, and Home
Assistant has to be stopped for it.** Home Assistant keeps its
dashboards in memory and does not re-read `.storage` while it runs, so
a file copied back behind its back changes nothing until the next
restart. Here the smallest thing is a single card, put back from the
panel, with everything else carrying on.

Where the two do not compete at all is disk. The history is one
directory, `dashboard_history`, next to your `configuration.yaml`, and
Home Assistant's backup takes it along: the exclusion list drops logs,
caches, temporary files and — if you ask for it — the database, and
nothing of this. A backup you restore a year from now brings the whole
history with it. They stack; they don't overlap.

And to be plain about the other direction: **this is not a backup, and
it is not trying to become one.** It keeps dashboards and nothing else
— no automations, no scripts, no entity registry — and it lives on the
same disk as the installation it belongs to. If that disk dies, this
dies with it. Keep your backups. I keep mine.

### My Home Assistant is already in a git repository. Why this too?

Before anything else: **check whether your dashboards are in that
repository at all.** Mine were not! :-( And, as is so often the case, 
I only realised it when I really needed it.

Dashboards you built in the UI are not part of `configuration.yaml`.
Each one is a JSON file in `.storage`, next to `auth`,
`auth_provider.homeassistant`, `http.auth` and `core.config_entries` —
refresh tokens, password hashes and the credentials of every
integration you have set up. That’s why I’d excluded the whole directory in my `.gitignore` without giving it a second thought — dashboards and all. So what I thought was my safety net turned out to be shit, and I regretted it rather bitterly. I was able to restore it from a backup (Proxmox, thankfully), but it was still a real nuisance. That was the start of this project. I’ve since realised that I’m not the only one in this situation, having seen it in a few shared `.gitignore` files. So please check the following:

```bash
# Is anything from .storage tracked at all? No output means no.
git ls-files .storage

# And if not, which rule is dropping it?
git check-ignore -v .storage/lovelace.my-dashboard
```

If the first command prints nothing, your dashboards are not in your
repository, and the second one names the line and the file that keep
them out.

If you write your dashboards by hand in YAML instead, then git really
does have them — and in that case this integration is not for you at
all. YAML dashboards fire no save event, so nothing of them is ever
recorded. That boundary is in the README too, and I would rather say it
here than have you install this and wait for a history that never
appears.

If your dashboards *are* in the repository, three differences are left.
None of them is a reason to drop git — I still have mine.

**git only ever knows what somebody committed.** An add-on that commits
on a schedule knows what was there when it ran; a commit I make by hand
knows what I had reached when I remembered to make it. A save here is
recorded as it happens, and there is nothing to remember.

**A diff of the file is not a diff of the dashboard.** One of my own
dashboards is 8244 lines of JSON — 28 views, 484 cards, 312 KB. git
will faithfully tell you that it changed. What it cannot tell you is
that a card moved from one view into another, because in the file that
is a block gone from one place and a very similar block turning up in
another, and Lovelace cards carry no identifier that would tie the two
together (I counted: 661 cards, 0 with an `id`). Recognising them by
their content is most of what this thing does, and it is why the answer
comes out as a sentence about a card instead of a hunk of JSON.

**And it happens where you noticed the problem.** You are standing at
the tablet in the hallway, something is missing, and you put it back
from there: the history, the comparison, one button for that one card.
The same move through git is find the commit, check out one file, stop
Home Assistant, copy it in, start it again — and starting it again is
not optional, for the reason in the question above.

So: both, if you like. git for the configuration as a whole, coarse and
complete; this for dashboards, fine-grained and without a shell.

## Versions

### Why can't I change a version number afterwards?

Because the number is not a field on the version. It **is** the
version's name.

A version is an annotated git tag called `my-dashboard/v1.2.0`. The
title and the description are text stored inside that tag, which is why
you can rewrite them whenever you like — hover the version and use the
pencil, in either view. The number is the tag's name, and that is the
one thing I deliberately left out of your reach. Three things hang off
it:

**You go back to a version by that name.** Restoring is
`dashboard_history.restore_state` with `my-dashboard/v1.2.0` as the
revision. If you have written that name into an automation, a script or
a note to yourself, renaming the version breaks it — and breaks it
silently, because a name that no longer exists looks exactly like a
typo. Nothing would tell you that the thing you addressed is still
there under a different number.

**The numbers only mean anything because they never move.** A new
version always counts up from the highest number that dashboard already
has, even after you have gone back to an older state. That is what
makes a collision impossible, and it is why a higher number always
means a later decision. Renaming a version downwards would put the same
number on two different states over the life of a dashboard: `v1.0.3`
in your notes from March and `v1.0.3` on the screen today would be two
different things, with nothing in between to say so.

**A tag name is a technical artefact, and its rules are not obvious.**
git will not take a space, a `..`, or any of `~^:?*[` in a ref name.
Nor can a dashboard have a flat tag `my-dashboard` while
`my-dashboard/v1.0.0` exists, because a ref file and a ref directory
are the same path — and the attempt fails with a different error
depending on which way round you do it. A dialog that let you type the
name would have to explain all of that to you, or refuse things for
reasons that read as arbitrary. Three buttons with the finished numbers
on them explain themselves.

#### What to do instead

**Put a second version beside the first.** That is one click, it costs
nothing and it loses nothing: the old version stays exactly where it
is, still pointing at its state. Two versions on one state is allowed
and normal — after going back to an older state, a fresh name for it is
often precisely what you want.

This works because versions group and never squash. Nothing is
overwritten and nothing is thrown away, so an extra name is never the
destructive option that renaming would be.

**Or take the wrong one away.** Since a version can be removed, a
number you handed out by mistake is not a permanent fixture: remove the
version and the mark is gone, while the state it pointed at stays in
the history exactly where it was. If the one you remove carries the
highest number, that number is free again — the next patch will use it.
And it is the short way out of "I clicked patch and meant minor": take
the mistaken version away, then create the one you meant.

What this does not do is *move* a version. Removing one and creating
another is two acts, and the second is aimed at whatever state you
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
  wording and touches neither the dashboard nor the history, so it
  needs no confirmation, exactly like describing a change.
- Whether a version exists **at all**, in both views, through the bin
  on the version — or with the `dashboard_history.remove_version`
  service. It asks first, and without `confirm` it answers with the
  words it would take. The state stays either way; what cannot be
  written back is the title and the description, so that confirmation
  is there to be read rather than clicked through.

One thing this route cannot undo: a version cannot be left without a
title. Emptying the field is refused rather than accepted, because a
version with no name is a row you cannot pick out of a list again — and
because leaving a field blank is not a way of saying anything. If what
you want is for the version to be gone, the bin says that plainly and
asks you first; a form whose emptiness destroys something would be a
trap.

## Deleting dashboards

### Why does forgetting a dashboard take so long?

Because git cannot remove anything without rewriting it.

A commit's identity is a hash of what it contains, including its
parent. Take one file out of one commit and that commit becomes a
different commit — and so does every commit after it, all the way to
the newest. There is no way to cut a dashboard out of the middle and
leave the rest untouched. That is not something I got wrong; it is what
a hash chain is.

So `forget` walks the whole history, writes every commit again without
that dashboard's files, moves the version marks onto the new commits,
and finally collects whatever nothing points at any more. Deleting the
files and leaving it at that was never an option: the old commits would
still be sitting there, and the text you asked me to forget would still
be readable.

### How long does forgetting a dashboard take?

**It depends on the size of your whole history, not on the size of the
dashboard you are deleting.** That catches everybody out, and my own
dialog makes it worse by showing how many states the doomed dashboard
has — nine states cost the same as a thousand, because what is being
rewritten is everything else.

Measured on my own installation, with 7403 commits, 70 dashboards and
782 version marks: **14.7 seconds**, split roughly

- 45 % rewriting the commits,
- 45 % collecting what became unreachable,
- 2 % moving the version marks.

A small history is done in a second or two. A much larger one takes
proportionally longer. The panel counts along while it works, so you
can watch it move instead of guessing.

*(The version marks used to be the expensive part by far — 58 % of the
whole operation, because each one was written to disk on its own. Since
v0.7.1 they go in a single batch, which is where most of the former
26.6 seconds went.)*

### Why is the whole panel locked while one dashboard is forgotten?

Two reasons, and the second one I did not see coming.

**Nothing you could do in there would be true.** Every revision is
changing while the rewrite runs. A history opened in that moment lists
states by identifiers that are about to stop existing, and a button
pressed there would act on one of them.

**Clicking makes it slower — measured, by a factor of three.** The
rewrite and every question the panel asks are Python running in the
same Home Assistant process, and they take turns. The same forget took
24 seconds when left alone and 76 seconds while the panel kept asking
for histories in the background. Taking the controls away is not me
being protective; it is what makes your wait as short as it can be.

Home Assistant itself is unaffected throughout — only this page waits.
A dashboard you save in the meantime is recorded as usual, once the
rewrite is out of the way.

### How much disk space does forgetting a dashboard free?

Close to nothing. If clearing space is why you are reaching for it,
look at the numbers first: this is the one step in here that cannot be
undone, and it is a poor way to buy a megabyte.

Measured on the same installation as the timings above — 7518 recorded
revisions, **9.2 MB** for the entire history, against 1.1 MB for the
dashboards themselves the way Home Assistant stores them. I then forgot
two dashboards, each time starting again from that same history:

- **The busiest one** — 850 of the 7518 revisions were its own —
  freed **0.71 MB, or 7.7 %**.
- **The largest one** — ten states, 1.6 MB of YAML between them —
  freed **0.47 MB, or 5.1 %**.

Three things keep that small.

**A state that did not change is stored once.** A revision is recorded
whenever anything is saved, but a dashboard nobody touched costs
nothing at that revision: it is the same state, kept once and pointed
at again. A dashboard you leave alone for a year takes up one copy, not
a year's worth.

**What is kept is compressed and written as differences.** The ten
states of that largest dashboard are 1.6 MB as YAML and 0.18 MB
compressed — and less again stored against each other, because two
consecutive states of the same dashboard usually differ by a line or
two.

**Most of the history is not dashboard text at all.** All the distinct
states of every dashboard together come to 2.8 MB of YAML, inside a
9.2 MB history. The rest is what recording a revision costs whatever is
in it — who, when, and how it hangs off the revision before — around
0.8 KB each. Forgetting a dashboard reclaims that only for revisions
that existed for it alone, and that, rather than the text, is where
nearly all of the 0.71 MB above came from: 850 such revisions, against
17 KB of actual content.

So what little you get back follows how often a dashboard was changed,
not how big it is — the opposite of what it feels like it should be.
And if your history really has outgrown its disk, then what to delete
is the history, not one dashboard inside it: it is a single directory,
`dashboard_history`, next to your `configuration.yaml`. Stop Home
Assistant, delete it, and you have every megabyte back at once; an
empty history starts again with the next save.

### How do I get back a dashboard I forgot for good?

You don't.

*Wat fott es, es fott.*

The only way back is a working backup of your Home Assistant
configuration. This is the one operation in here that takes something
away permanently — everything else only ever adds, which is why it is
the only one that asks you twice and says so in bold.

The two kinds of "gone" are worth keeping apart, because they are easy
to mix up. A dashboard **deleted in Home Assistant** is not gone from
here at all: its history stays, you can read it, and you can bring the
dashboard back. I have done exactly that, after a cleanup script in my
own test suite deleted the dashboard I was working in — restored with
this integration, title, icon and all three cards, nothing left over.
`forget` is the other kind. It removes the history itself, and that is
the one there is no button for.

If what you actually want is for a deleted dashboard to stop cluttering
the list, that is what the list's **Deleted** fold is for. It keeps the
history and keeps it out of your way.
