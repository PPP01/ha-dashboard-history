# Frequently asked questions

Questions that come up often enough to be worth writing down once —
with the reasoning, not just the rule. Where a decision was made
deliberately, this says what it buys and what it costs, so you can tell
a design choice from something nobody got round to.

The README is the place to start; this is for the things you only wonder
about once you are using it.

## Contents

- [Why can't I change a version number afterwards?](#why-cant-i-change-a-version-number-afterwards)

## Why can't I change a version number afterwards?

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

### What to do instead

**Put a second version beside the first.** That is one click, it costs
nothing, and it loses nothing: the old version stays exactly where it
is, still pointing at its state. Two versions on one state is allowed
and normal — after going back to an older state, a fresh name for it is
often precisely what you want.

This works because versions group and never squash. Nothing is
overwritten and nothing is thrown away, so an extra name is never the
destructive option that renaming would be.

### What you *can* change, at any time

- The **title** and the **description** of any version, in both views,
  through the pencil on the version — or with the
  `dashboard_history.retitle_version` service.
- A version made automatically keeps its `automatic` label when you
  rename it. The label says who made the version, not what it is
  called.
- Which **state** a version marks never changes. Renaming rewrites the
  wording and touches neither the dashboard nor the history, so it needs
  no confirmation, exactly like describing a change.

One thing cannot be undone by this route: a version cannot be left
without a title. Emptying the field is refused rather than accepted,
because a version with no name is a row you cannot pick out of a list
again — and unlike a description, there is nothing that would put a name
back.
