# Status — where every project stands and what to do next

Parameter:

- `PROJECT` — optional. Omit to inspect every known project.

Follow `AGENTS.md`. This is **read-only**: never modify workspace files or
target repositories.

Discover projects from curated and candidate YAML. Ignore `.gitkeep` and never
treat a generated artifact as canonical knowledge.

---

## Inspect

For each project:

1. Read the pending and curated files. Resolve the repository path from pending
   state first.
2. Read the context file when present. Count unresolved review decisions and
   provisional inferred context. **Blank answer blocks are not blockers.**
3. Without reading repository content, use read-only Git metadata to resolve the
   current HEAD and verify that the newest recorded HEAD exists and is an
   ancestor. Report missing or disconnected history rather than guessing.
4. Check whether curated records and generated artifacts exist. Do not infer
   artifact freshness from file timestamps.

## Classify

First matching state wins:

1. **`Needs attention`** — malformed YAML, inconsistent paths, a missing
   repository, an unresolvable recorded commit, or disconnected history.
2. **`New commits with capture pending`** — candidates exist and their HEAD is
   an ancestor of, but differs from, the repository HEAD.
3. **`Capture pending`** — candidates exist but their analysis entry is
   incomplete or invalid.
4. **`Ready for batch review`** — valid candidates at the repository HEAD,
   regardless of blank optional context.
5. **`New commits available`** — no candidates, and the curated HEAD is an older
   ancestor of the repository HEAD.
6. **`Ready to generate artifacts`** — curated records exist, the repository is
   current, and interview or bullet output is absent.
7. **`Reviewed and current`** — curated HEAD equals repository HEAD.

If no project state exists at all, report `No projects yet` and show the first
capture invocation, which needs a repository path and a name.

## Generated indexes

Run `scripts/ekb index --check` and `scripts/ekb check`. Both are read-only.

Report a stale index on its own line with the rebuild command. Neither is a
project state and neither blocks any workflow.

## Output

A compact table: `Project`, `State`, `Repository HEAD`, `Recorded HEAD`,
`Provisional`, `Interview`, `Bullets`, `Next action`.

`Provisional` reports unconfirmed inferred-context items for awareness, never as
a gate. Explain only the attention items; a healthy row needs no commentary.

Every row ends with one exact action:

```text
Follow prompts/analyze.md with PROJECT=<name>
Follow prompts/review.md with PROJECT=<name>
Follow prompts/interview.md with PROJECT=<name>
Follow prompts/bullets.md with PROJECT=<name>
```

For a first capture: `Follow prompts/analyze.md with REPO_PATH=/absolute/path
PROJECT=<name>`.
