# Home Assistant Actions (Services) Reference

All panel capabilities are exposed as Home Assistant Actions under the `dashboard_history` domain. You can invoke them via **Developer Tools → Actions**, in scripts, or through automations.

All actions require Home Assistant administrator privileges.

---

## Addressing Dashboards

Dashboards are identified by their **key**:
- The dashboard's `url_path` (e.g. `living-room`, `energy`, `tablet-view`).
- `_default` for Home Assistant's default main dashboard.
- Run the `dashboard_history.debug_snapshot` action to see all recognized keys.

---

## Action Catalog

| Action | Description | Preview by default? |
| :--- | :--- | :---: |
| `dashboard_history.history` | List recorded states for a dashboard (newest first, paged). | Read-only |
| `dashboard_history.search` | Search full history for text across notes, summaries, and version names. | Read-only |
| `dashboard_history.explain` | Returns a plain-language summary of what a specific commit changed. | Read-only |
| `dashboard_history.compare` | Returns the full difference (cards and diff) between any two revisions. | Read-only |
| `dashboard_history.deleted_since` | Lists all cards and views present at a revision that are gone in today's state. | Read-only |
| `dashboard_history.restore_deleted` | Restores one missing item into today's dashboard (additive). | Yes (`confirm: true` to apply) |
| `dashboard_history.undo_change` | Surgically takes back a single change, preserving later edits. | Yes (`confirm: true` to apply) |
| `dashboard_history.restore_state` | Sets a dashboard back to an earlier revision or named version. | Yes (`confirm: true` to apply) |
| `dashboard_history.describe` | Sets or clears a custom note on a specific change. | No |
| `dashboard_history.versions` | Lists all named versions for one or all dashboards. | Read-only |
| `dashboard_history.next_versions` | Returns the next semantic patch, minor, and major version numbers. | Read-only |
| `dashboard_history.create_version` | Names a recorded revision as a version tag. | No |
| `dashboard_history.retitle_version` | Updates the title or description of an existing version tag. | No |
| `dashboard_history.remove_version` | Removes a version tag (underlying dashboard state is retained). | Yes (`confirm: true` to apply) |
| `dashboard_history.forget` | Permanently deletes the Git history of a deleted dashboard. | Yes (`confirm: true` to apply) |
| `dashboard_history.debug_snapshot` | Returns internal state and recognized dashboard keys. | Read-only |

Every action answers with data rather than just doing something, so in a script or automation use `response_variable` to read the answer. In **Developer Tools → Actions** the answer is shown below the button.

---

## Fields

`dashboard` is always the dashboard's key (see above). `revision` is a revision hash from `history`, or — for `restore_state` — a version name such as `living-room/v1.2.0`.

| Action | Fields |
| :--- | :--- |
| `history` | `dashboard` (required); `limit` (default 50, at most 500) |
| `search` | `dashboard`, `text` (both required); `limit` (default 50, at most 1000) — the answer says whether there were more matches |
| `explain` | `dashboard`, `revision` (both required) — the change itself, not the state before it |
| `compare` | `dashboard` (required); `revision_a`, `revision_b` — a side left out means the current live state, and at least one of the two must be a revision |
| `deleted_since` | `dashboard`, `revision` (both required) — every item in the answer carries a `position` for `restore_deleted` |
| `restore_deleted` | `dashboard`, `revision`, `position` (all required); `confirm`; `override_unrecorded_state`; `allow_parking` |
| `undo_change` | `dashboard`, `revision` (both required); `confirm`; `override_unrecorded_state`; `allow_parking` |
| `restore_state` | `dashboard`, `revision` (both required); `confirm`; `override_unrecorded_state`; `keep_as_version` (`title` required inside it; `level`, `description` optional) |
| `describe` | `revision` (required); `text` (an empty text removes the note). No `dashboard`: a revision identifies the change on its own |
| `versions` | `dashboard` (optional; left out, it lists every dashboard's versions) |
| `next_versions` | `dashboard` (required) |
| `create_version` | `dashboard`, `title` (both required); `level` (`patch` by default, `minor`, `major`); `description`; `revision` (default: the most recent recorded state) |
| `retitle_version` | `dashboard`, `name`, `title` (all required); `description` — `name` is the full version name as `versions` reports it, e.g. `living-room/v1.0.0`; the title cannot be emptied |
| `remove_version` | `dashboard`, `name` (both required); `confirm` |
| `forget` | `dashboard`, `confirm` — only for a dashboard that Home Assistant no longer has |
| `debug_snapshot` | none |

Three fields come up on more than one action:

- **`confirm`** — default `false`. Without it a write action only answers with a preview (see below).
- **`allow_parking`** — default `false`. `undo_change` and `restore_deleted` refuse where a card cannot be proven to belong in its old section any more. With `allow_parking: true` they place it instead in the view's "Imported cards" area (the view's own `cards:` list), and a removed whole section is appended as the last section of its view. This is what the asterisk on the panel's button stands for; the answer lists what would be parked.
- **`override_unrecorded_state`** — default `false`. Every restore first records the state it is about to replace. If that recording cannot be made — the repository was unreadable or unwritable at that moment — the write is refused. Setting this to `true` writes anyway, at the cost of the one state that could not be recorded. This is the "Write anyway?" of the panel; see the [FAQ](../FAQ.md#what-does-write-anyway-mean-when-a-restore-is-refused).

`create_version` without a `revision` is also refused while the state the dashboard holds right now has not been recorded (after a recording failed), because the most recent *recorded* state is then not the one you see. Pass a `revision` explicitly, or save the dashboard once more.

---

## Safety & Previews: Two-Step Write Pattern

Any action that writes to a dashboard or rewrites history (`restore_state`, `undo_change`, `restore_deleted`, `remove_version`, `forget`) implements a safety-first contract:

1. **Step 1 (Preview):** Call the action without `confirm: true`. The action writes nothing and returns a response containing the preview, plain-language description, and diff.
2. **Step 2 (Execution):** Call the action with `confirm: true` to execute the change.

---

## Practical YAML Examples

### 1. Tag a milestone before an automated change

```yaml
action: dashboard_history.create_version
data:
  dashboard: living-room
  revision: 939b93231b6f9ea7349d5c3e8a875534865facf3
  title: "Before automated tablet redesign"
  description: "Automated snapshot taken by deployment script"
  level: minor
```

### 2. Surgically undo a specific change

```yaml
# Step 1: Preview the undo
action: dashboard_history.undo_change
data:
  dashboard: living-room
  revision: 939b93231b6f9ea7349d5c3e8a875534865facf3
  confirm: false
```

```yaml
# Step 2: Apply the undo after confirming
action: dashboard_history.undo_change
data:
  dashboard: living-room
  revision: 939b93231b6f9ea7349d5c3e8a875534865facf3
  confirm: true
```

### 3. Restore a deleted dashboard

```yaml
action: dashboard_history.restore_state
data:
  dashboard: old-tablet
  revision: 4f544ba876543210fedcba0987654321abcdef01
  confirm: true
```

### 4. Restore a whole dashboard to a named version and preserve current state

```yaml
action: dashboard_history.restore_state
data:
  dashboard: living-room
  revision: living-room/v1.2.0
  confirm: true
  keep_as_version:
    title: "State before reverting to v1.2.0"
    level: patch
```

### 5. Additively restore a single deleted card

```yaml
# 1. Inspect what was deleted since revision
action: dashboard_history.deleted_since
data:
  dashboard: living-room
  revision: 939b93231b6f9ea7349d5c3e8a875534865facf3

# 2. Put back the card at index position 0
action: dashboard_history.restore_deleted
data:
  dashboard: living-room
  revision: 939b93231b6f9ea7349d5c3e8a875534865facf3
  position: 0
  confirm: true
```

