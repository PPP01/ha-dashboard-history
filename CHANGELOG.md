# Changelog

## v0.3.0

The release that turns a recorded history into one you can navigate
without reading commit hashes. Needs **Home Assistant 2024.11 or newer**
(0.2.0 claimed 2024.1, which was wrong — the options flow has always
needed 2024.11).

### Versions — names for states worth coming back to

- **Named versions per dashboard**, as annotated git tags such as
  `my-dashboard/v1.2.0`. Every dashboard counts its own, so two can each
  have a `v1.0.0` without colliding. Made from any row in the history;
  you never type the number — three buttons offer the next patch, minor
  and major, already worked out from the highest that dashboard has.
- **Versions that appear on their own**, so the list is never empty: one
  `v1.0.0` per dashboard at the oldest state there is, and one per day on
  the day's last state. A day on which nothing changed gets none, and
  neither does a day that ends on the state the newest version already
  holds. The daily ones can be switched off under *Configure*.
- **Rename a version** at any time — its title and description, never its
  number. The number is the tag's name and the way back is addressed by
  it; the [FAQ](https://github.com/PPP01/ha-dashboard-history/blob/main/FAQ.md) has the full reasoning.
- **Remove a version** again. The mark goes, the state stays exactly
  where it was and remains reachable in the advanced view.
- Going back to a version **keeps the state you are leaving**: it stays in
  the history as its own entry, and the dialog offers to name it too.

### A panel you can actually navigate

- **Two views.** The simple one shows nothing but the versions — for
  *"put it back to how it was on Tuesday"*. The advanced one shows every
  recorded change, twenty-five at a time. Your choice is remembered.
- **Search**, across the loaded changes or the whole recorded past,
  looking at the automatic message, your own notes, and the title,
  description and number of any version.
- **Paging by commit cursor**, so a version never disappears from the
  list just because its commit slid out of the window.
- The state you have now is **set apart and marked** — worked out rather
  than assumed, so a dashboard changed behind Home Assistant's back is
  not crowned. Rows holding the same content say so.

### Three ways back instead of one

- **Undo this change** takes back one save and leaves everything after it
  standing. Offered only where it can be *proved* exact: the card that
  change produced has to be in the dashboard today, byte for byte, and
  there exactly once. Where it cannot, the row says why instead of
  guessing.
- **Put back** reinserts one missing item into the dashboard as it stands.
  Additive by definition — it never overwrites.
- **A whole deleted section** now comes back as *one* thing, not as a row
  of cards that each refused. It goes into the gap it left, and only when
  the sections beside it are as you left them.
- Two views sharing one URL path — which Home Assistant's backend permits
  — no longer lead to a silent write into the surviving view. Both write
  paths refuse.
- A view without a URL path that never moved is no longer offered back
  and duplicated when a *neighbour* was deleted in front of it.

### Words instead of diffs

- **Plain-language history**: *"markdown: Shopping list was deleted"*,
  *"tile: Living room lamp was moved to Kitchen"*. The diff stays one
  click away.
- **Your own description on any change**, as a git note — the commit is
  not rewritten, so every revision you wrote down stays valid.
- Every preview says what it will do before it does it, and nothing that
  writes a dashboard state runs without an explicit confirmation.

### Under the hood

- The history is a git repository this integration owns, written with a
  pure Python implementation — **no `git` binary is required**, on any
  Home Assistant installation type.
- Six modules carry the logic and import nothing from Home Assistant, so
  the test suite runs without an installation. Beside it, 173 checks
  drive a real Home Assistant over HTTP and WebSocket — the parts
  `pytest` structurally cannot reach, and where every defect found in
  this project so far has been.
- Every service is admin-only, and so is every WebSocket command.

### Known limits

Part 2 of the [README](https://github.com/PPP01/ha-dashboard-history/blob/main/README.md) lists them case by case, measured
rather than reasoned about — including the four situations in which the
tool can still write something nobody asked for, and why refusing is the
answer everywhere else. The short version: **no state is ever
unrecoverable**; what the limits cost is the precision of the narrow
tools, never the content.

## v0.2.0

The first published release: every save recorded, a panel in the sidebar,
and the whole-state restore.
