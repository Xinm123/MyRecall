# OpenSpec JSON Output Reference

**Source**: [Fission-AI/OpenSpec v1.2.0](https://github.com/Fission-AI/OpenSpec) (commit: afdca0d5dab1aa109cfd8848b2512333ccad60c3)

Official documentation: https://openspec.dev/

---

## JSON Structure Overview

OpenSpec CLI exposes two main JSON-formatted command outputs:
1. **`openspec status --json`** — Artifact completion status
2. **`openspec instructions apply --json`** — Task implementation instructions

Both are defined in the TypeScript type system and used for automation.

---

## 1. `openspec status --json`

### Command
```bash
openspec status --change <name> [--schema <schema>] --json
```

### Output Type: `ChangeStatus`

**Source**: [instruction-loader.ts:105-116](https://github.com/Fission-AI/OpenSpec/blob/afdca0d5dab1aa109cfd8848b2512333ccad60c3/src/core/artifact-graph/instruction-loader.ts#L105-L116)

```typescript
export interface ChangeStatus {
  /** Change name */
  changeName: string;
  /** Schema name */
  schemaName: string;
  /** Whether all artifacts are complete */
  isComplete: boolean;
  /** Artifact IDs required before apply phase (from schema's apply.requires) */
  applyRequires: string[];
  /** Status of each artifact */
  artifacts: ArtifactStatus[];
}

export interface ArtifactStatus {
  /** Artifact ID */
  id: string;
  /** Output path pattern */
  outputPath: string;
  /** Status: done, ready, or blocked */
  status: 'done' | 'ready' | 'blocked';
  /** Missing dependencies (only for blocked) */
  missingDeps?: string[];
}
```

### Example Output

```json
{
  "changeName": "add-dark-mode",
  "schemaName": "spec-driven",
  "isComplete": false,
  "applyRequires": ["proposal", "design"],
  "artifacts": [
    {
      "id": "proposal",
      "outputPath": "proposal.md",
      "status": "done"
    },
    {
      "id": "design",
      "outputPath": "design.md",
      "status": "ready"
    },
    {
      "id": "tasks",
      "outputPath": "tasks.md",
      "status": "blocked",
      "missingDeps": ["design"]
    }
  ]
}
```

### Key Fields Explained

| Field | Type | Meaning |
|-------|------|---------|
| `schemaName` | string | Workflow schema used (e.g., "spec-driven"). **Determines artifact definitions.** |
| `isComplete` | boolean | `true` when ALL artifacts are `"done"`. |
| `applyRequires` | string[] | Artifact IDs that must be complete **before the apply phase unlocks**. Comes from schema's `apply.requires` field. If no apply config, defaults to all artifact IDs. |
| `artifacts[].status` | enum | One of: `"done"` (file exists), `"ready"` (no unmet dependencies), `"blocked"` (has missing dependencies). |
| `artifacts[].missingDeps` | string[] | Only present if `status === "blocked"`. Lists artifact IDs that must be completed first. |

### Status Flow Logic

**Source**: [instruction-loader.ts:317-362](https://github.com/Fission-AI/OpenSpec/blob/afdca0d5dab1aa109cfd8848b2512333ccad60c3/src/core/artifact-graph/instruction-loader.ts#L317-L362)

```
1. If artifact's generated file exists → status = "done"
2. Else if all dependencies are "done" → status = "ready"
3. Else → status = "blocked" + missingDeps = [list of incomplete dependencies]
```

---

## 2. `openspec instructions apply --json`

### Command
```bash
openspec instructions apply --change <name> [--schema <schema>] --json
```

### Output Type: `ApplyInstructions`

**Source**: [shared.ts:24-38](https://github.com/Fission-AI/OpenSpec/blob/afdca0d5dab1aa109cfd8848b2512333ccad60c3/src/commands/workflow/shared.ts#L24-L38)

```typescript
export interface ApplyInstructions {
  changeName: string;
  changeDir: string;
  schemaName: string;
  contextFiles: Record<string, string>;  // artifact ID → full path
  progress: {
    total: number;    // total tasks in tracking file
    complete: number; // tasks marked with [x] or [X]
    remaining: number; // total - complete
  };
  tasks: TaskItem[];
  state: 'blocked' | 'all_done' | 'ready';
  missingArtifacts?: string[];  // only if state === 'blocked'
  instruction: string;
}

export interface TaskItem {
  id: string;        // "1", "2", ... (sequential)
  description: string;
  done: boolean;
}
```

### Example Output

```json
{
  "changeName": "add-dark-mode",
  "changeDir": "/home/user/project/openspec/changes/add-dark-mode",
  "schemaName": "spec-driven",
  "contextFiles": {
    "proposal": "/home/user/project/openspec/changes/add-dark-mode/proposal.md",
    "design": "/home/user/project/openspec/changes/add-dark-mode/design.md"
  },
  "progress": {
    "total": 8,
    "complete": 2,
    "remaining": 6
  },
  "tasks": [
    {
      "id": "1",
      "description": "Add dark mode CSS variables",
      "done": true
    },
    {
      "id": "2",
      "description": "Update theme context",
      "done": true
    },
    {
      "id": "3",
      "description": "Create toggle component",
      "done": false
    },
    {
      "id": "4",
      "description": "Add localStorage persistence",
      "done": false
    },
    {
      "id": "5",
      "description": "Test on mobile",
      "done": false
    },
    {
      "id": "6",
      "description": "Document theme system",
      "done": false
    },
    {
      "id": "7",
      "description": "Update storybook stories",
      "done": false
    },
    {
      "id": "8",
      "description": "Run accessibility tests",
      "done": false
    }
  ],
  "state": "ready",
  "instruction": "Read context files, work through pending tasks, mark complete as you go.\nPause if you hit blockers or need clarification."
}
```

### State Values Explained

**Source**: [instructions.ts:307-399](https://github.com/Fission-AI/OpenSpec/blob/afdca0d5dab1aa109cfd8848b2512333ccad60c3/src/commands/workflow/instructions.ts#L307-L399)

| State | Meaning | Trigger | Action |
|-------|---------|---------|--------|
| `"blocked"` | **Cannot apply yet** — required artifacts missing or tracking file missing | Missing artifact files in change dir (checked via `artifactOutputExists()`) OR tracking file configured but doesn't exist OR tracking file empty | Show `missingArtifacts` list; use `openspec-continue-change` to create missing artifacts |
| `"ready"` | **Ready to apply** — all required artifacts exist, tasks are in progress | All required artifacts present AND (no tracking file OR tracking file exists with tasks) | Read context files, work through tasks, mark complete |
| `"all_done"` | **All tasks complete** — ready to archive | Tracking file exists AND all tasks marked `[x]` OR `[X]` | Suggest running tests/review before archiving |

### Key Logic Points

**Source**: [instructions.ts:360-387](https://github.com/Fission-AI/OpenSpec/blob/afdca0d5dab1aa109cfd8848b2512333ccad60c3/src/commands/workflow/instructions.ts#L360-L387)

```typescript
// Determine state
if (missingArtifacts.length > 0) {
  state = 'blocked';
  // instruction: "Cannot apply this change yet. Missing artifacts: ..."
} else if (tracksFile && !tracksFileExists) {
  state = 'blocked';
  // instruction: "The {tracksFile} file is missing and must be created..."
} else if (tracksFile && tracksFileExists && total === 0) {
  state = 'blocked';
  // instruction: "The {tracksFile} file exists but contains no tasks..."
} else if (tracksFile && remaining === 0 && total > 0) {
  state = 'all_done';
  // instruction: "All tasks are complete!..."
} else if (!tracksFile) {
  state = 'ready';
  // instruction: {schema's apply.instruction or default}
} else {
  state = 'ready';
  // instruction: "Read context files, work through pending tasks..."
}
```

### Task Parsing Rules

**Source**: [instructions.ts:217-238](https://github.com/Fission-AI/OpenSpec/blob/afdca0d5dab1aa109cfd8848b2512333ccad60c3/src/commands/workflow/instructions.ts#L217-L238)

Tasks are parsed from the tracking file (e.g., `tasks.md`). Format:
- **Pattern**: `- [ ] Task description` or `- [x] Task description` or `- [X] Task description`
- **Done detection**: Checkbox char is `x` or `X` (case-insensitive)
- **Task ID**: Sequential number (1, 2, 3, ...) assigned during parsing

Example tracking file:
```markdown
- [x] First task
- [x] Second task
- [ ] Third task
- [ ] Fourth task
```

Parses to:
```json
{
  "tasks": [
    { "id": "1", "description": "First task", "done": true },
    { "id": "2", "description": "Second task", "done": true },
    { "id": "3", "description": "Third task", "done": false },
    { "id": "4", "description": "Fourth task", "done": false }
  ]
}
```

---

## 3. No-Changes Case

When no active changes exist, `openspec status --json` returns:

```bash
$ openspec status --json
```

```json
{
  "changes": [],
  "message": "No active changes."
}
```

**Source**: [status.ts:48-50](https://github.com/Fission-AI/OpenSpec/blob/afdca0d5dab1aa109cfd8848b2512333ccad60c3/src/commands/workflow/status.ts#L48-L50)

---

## Implementation Automation Checklist

When parsing these JSON outputs for automation:

### For `openspec status --json`:

- [ ] Extract `schemaName` to validate workflow type
- [ ] Check `isComplete` to decide if change is ready for archival
- [ ] Check `artifacts[].status === "blocked"` to identify blocked paths
- [ ] Read `artifacts[].missingDeps` to show which artifacts to create next
- [ ] Compare `applyRequires` against `done` artifacts to determine if apply phase is unlocked

### For `openspec instructions apply --json`:

- [ ] **If `state === "blocked"`**: Stop execution, show `missingArtifacts`, guide user to create them
- [ ] **If `state === "all_done"`**: Congratulate user, suggest archiving change
- [ ] **If `state === "ready"`**: Show context files, load tasks, work through remaining items
- [ ] Parse `progress: { complete, total, remaining }` for progress reporting
- [ ] Parse `tasks[]` and look for `done: false` items to show work queue
- [ ] Use `contextFiles` to read artifact content for AI context injection

### Schema Detection:

- `schemaName` determines artifact definitions
- Common schemas: `"spec-driven"` (default)
- Different schemas may have different artifact structures and apply phase requirements
- Always use `schemaName` when resolving artifact paths

---

## References

| File | Purpose |
|------|---------|
| [status.ts](https://github.com/Fission-AI/OpenSpec/blob/afdca0d5dab1aa109cfd8848b2512333ccad60c3/src/commands/workflow/status.ts) | Status command implementation & output formatting |
| [instructions.ts](https://github.com/Fission-AI/OpenSpec/blob/afdca0d5dab1aa109cfd8848b2512333ccad60c3/src/commands/workflow/instructions.ts) | Apply instructions command & JSON schema generation |
| [shared.ts](https://github.com/Fission-AI/OpenSpec/blob/afdca0d5dab1aa109cfd8848b2512333ccad60c3/src/commands/workflow/shared.ts) | Shared types: `ApplyInstructions`, `TaskItem` |
| [instruction-loader.ts](https://github.com/Fission-AI/OpenSpec/blob/afdca0d5dab1aa109cfd8848b2512333ccad60c3/src/core/artifact-graph/instruction-loader.ts) | Core types: `ChangeStatus`, `ArtifactStatus`, status formatting logic |

---

**Last Updated**: 2026-03-12 (OpenSpec v1.2.0, commit afdca0d5dab1)
