# Changelog

## v0.6.0

The README was one long page trying to be five different things at
once. It is now four, plus a short front page: what it does, how to
install it, and the essentials of using it - with everything it used
to cover in depth split into documents of their own.

### One README, several audiences

- The README is now a short overview, with the detail split into
  `docs/user-guide.md`, `docs/how-it-works.md`, `docs/limitations.md`,
  `docs/services.md`, and `docs/development.md`, linked from a
  Documentation Hub table.
- Nothing measured was thrown away: the detailed, case-by-case
  reasoning behind the sections and pathless-view limits - every
  measurement and refusal message - now lives as a full appendix in
  `docs/limitations.md`, for whoever wants to read past the summary.
- New, neutral screenshots throughout, including the Replace overlay
  and Compare mode, which had none before.

## v0.5.1

The current-state ring now means the same thing wherever it appears.

### One colour, one meaning

Blue used to mark "current state" in the simple view but "unclean,
nothing saved matches" in the advanced one — the same colour saying two
different things depending on which view happened to be open. It now
answers one question everywhere: does anything recorded hold what the
dashboard holds right now. Orange where nothing does, blue where a
version does — including a version section that is also the newest
change, which used to carry no colour of its own at all.

## v0.5.0

One action bar instead of three separate controls on a history card,
and one overlay instead of two for replacing the whole dashboard. No
change to the Home Assistant version floor — still **2024.11 or
newer**.

### One action bar, not three

- **Undo this change**, **Version up to here** and **Replace the
  whole dashboard** used to be three separately stacked blocks on a
  card, one of them an expander easy to mistake for the technical-diff
  one right above it. All three now sit in a single row, in that
  order, and Replace is a plain button that opens a dialog rather than
  an expander of its own.
- **Replace the whole dashboard** combines what used to be two
  independent buttons — "back to the state before" and "back to the
  state after" this change — into one overlay with a choice between
  them. Both states' previews are fetched together when the overlay
  opens, so switching the choice never waits on the network again.
- The **technical-details** disclosure — the fold that shows the raw
  diff — is one shared, pill-shaped control now, identical wherever it
  appears: the card, the confirm dialog, the Replace overlay, and the
  compare dialog. It used to be a plain link with the browser's own
  triangle in some of those places and something else again in others.
- The sentence a confirmation dialog opens with (what applying it
  does, or that nothing is lost) reads as one line before the itemised
  list of card changes, not after it — and the button that carries the
  action out is named for what it does: **Undo this change**, **Put
  back**, or the state it goes to, never a bare "Apply" that could
  belong to any of them.
- The "nothing is lost" reassurance used to sit in a tinted, bordered
  box inside a dialog's body, behind a second click to reveal it. It
  is a quiet strip between the body and the buttons now, always
  visible when it applies — read once, not toggled.

### Put back, for a state already known to be current

Put back inside the compare dialog used to require the newer side to
be the literal pinned "Current state" pick. It is now offered whenever
the newer side is *known* to hold today's content — a row or version
already marked current — which a dashboard whose newest change already
carries a version could reach without ever landing on that exact pick.

## v0.4.0

A deliberate way to compare two states, and a steadier panel around it.
No change to the Home Assistant version floor — still **2024.11 or
newer**.

### Compare mode, in place of a guess

- Replaces the row-level "Also missing since then" list, which
  reappeared under every row a deletion could reach and repeated
  itself down the whole history. Tick any two rows instead — including
  **Current state** — and see what changed between them: plain
  language first, the technical diff a click away.
- **Put back** is offered wherever one side of the comparison is the
  current state. Which side is actually older is decided by the
  history itself, never guessed from the order the two rows were
  ticked in — and where both land in the same second, the repository's
  own tie-free commit order settles it instead of a timestamp that
  cannot.
- What is still missing is now **grouped by the view it came from**,
  the same way the plain-language diff above it already groups its own
  lines — one heading per view, not a repeated badge on every row.
- Putting an item back closes the dialog rather than leaving stale
  positions behind for a second click to land on the wrong one.
- A targeted undo that has to refuse — the card it would take back
  cannot be proven to sit exactly once, unchanged, in today's state —
  now points at compare mode instead of ending in a dead end.

### A steadier panel

- **Simple** and **Advanced** are a real segmented control now, not a
  single toggle button, and it follows the panel's own theme rather
  than the operating system's.
- Version sections stand apart from ordinary changes at a glance: an
  accent border, a disclosure chevron, a guide line for the changes
  nested under an open one — drawn with the one chevron the panel uses
  everywhere else, not a second glyph of its own.
- The confirmation dialogs for restore, undo and put-back share one
  simplified layout: a two-segment toggle for the technical diff and
  the current-state note, and the version-naming field appears only
  once you ask to keep the state you are leaving.
- Dialog toggle buttons now tell assistive technology what they open
  (`aria-expanded` and `aria-controls`), instead of announcing a bare
  "pressed" state with no subject.

### Faster

- Dashboards are parsed through libyaml instead of pure Python's own
  parser — measured 8 to 9 times faster on a real dashboard, which
  speeds up every one of the panel's own slow calls at once, since all
  of them parse the same YAML.
- An undo's full preview — the diff and the plain-language explanation
  — is computed only where it is actually shown, not on every row you
  merely expand.
- Expanding a row now caches its answers; collapsing and reopening the
  same row costs no further round trip.
- A failing `undo_change` no longer blocks the explanation rendering
  beside it, or the other way around.

### A few things that were quietly wrong

- Undo used to be asked for even on the oldest recorded change, where
  the answer could never be anything but "no".
- A dropped network call was remembered as though it were a real
  answer — asking again now genuinely asks again, rather than
  repeating the same "the answer did not arrive" forever.
- When an undo's answer truly did not arrive, the row said "no reason
  given" instead of the actual cause already sitting in the banner
  above it.
- The technical diff no longer opens on "No difference" for a change
  that plainly has one, and it keeps its scroll position across a
  background re-render instead of jumping back to the top.
- The loading spinner no longer freezes under reduced motion.

### A new brand icon

Solid colors on a transparent ground, with dedicated light and dark
variants, replacing the old solid-purple one.

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
