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

