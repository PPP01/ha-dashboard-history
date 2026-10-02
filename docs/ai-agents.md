# AI Agents Using This Integration

Guidance for AI agents — not human contributors — that change Home
Assistant dashboards through the API: Claude through an MCP server, or
any other tool that goes through `lovelace/config/save`.

## Why this matters

A dashboard change made through the API is recorded by this integration
exactly like a change made by hand in the UI (see the README's "What It
Tracks & Solves"), but it lands as an unnamed, automatic entry — nothing
calls `create_version` for it, and nothing calls `describe`. If you just
changed a dashboard, use the actions below to leave a real name and
description behind, so the change can be found and understood later.

## After changing a dashboard

1. Call `dashboard_history.history` for the dashboard you just changed
   to find the revision your change produced — or skip this and rely on
   `create_version`'s own default, which marks the most recent revision.
2. Call `dashboard_history.create_version` with a `title` and a
   `description` of what changed and why, using your own knowledge of
   the edit you just made. This integration has no way to infer intent
   from a diff on its own — that's exactly the part only you know.

Two details that are easy to miss:
- `create_version` needs no `confirm`. It only tags an already-recorded
  state; nothing on the dashboard changes because of it. It does need an
  admin-level token, like every other action here.
- Without a `revision`, `create_version` refuses with "not recorded yet"
  when the most recent recorded state is not what the dashboard holds —
  the recording of your change failed. Save the same configuration once
  more and try again; the Home Assistant log says why it failed
  ("Could not record dashboard …").
- `dashboard` always means the dashboard's `url_path`, never its visible
  title. Run `dashboard_history.debug_snapshot` first if you don't know
  it.

## Other actions worth knowing about

- `dashboard_history.explain` turns one recorded change into a
  plain-language summary — useful raw material for a `create_version`
  description instead of re-deriving one from a raw diff.
- `dashboard_history.compare` gives the full difference between any two
  states of a dashboard, including its current live state.
- `dashboard_history.describe` attaches a note to a change after the
  fact, for a change you didn't create a version for.

Full reference for every action, with all fields and examples:
[Home Assistant Actions (Services)](services.md).
