# Guide — the single entry point

Parameters, all optional:

- `PROJECT` — a project name.
- `REPO_PATH` — a repository path, needed only for a project you have not
  analyzed before.
- Plain language such as `analyze`, `update`, `deep dive`, `prepare me for an
  interview`, `bullets`, `screen this job`, `resume`, or `apply`.

Follow `AGENTS.md`. This is the one procedure a user should have to remember.
They must not need to know state names, file paths, or command order.

---

## 1. Route the intent first

Before resolving anything else:

- `resume`, `job`, `apply`, or a pasted posting with stated intent to apply →
  `prompts/resume.md`. A full application resume is cross-project; do not ask
  the user to pick one project.
- `cover letter` for an existing application → `prompts/cover-letter.md`. If
  that application has no completed, validated resume, route through
  `prompts/resume.md` first.
- `screen`, `check this job`, `is this worth applying to`, or a pasted posting
  with no stated intent → `prompts/screen.md` alone. Offer the resume only
  after the decision is `proceed`.
- `bullets` or `project bullets` with a named project → `prompts/bullets.md`.
- `interview` or `prepare me` → `prompts/interview.md`.
- Anything else → resolve a project and continue below.

The screening gate is the one place this file's "continue automatically" rule
does not apply. It always stops for the user's decision, including on a clean
report.

After every successful job-targeted resume delivery, ask the single cover-letter
opt-in question required by `prompts/resume.md`. The question is a user choice,
so stop there. A yes resumes through `prompts/cover-letter.md` without repeating
the screening gate or asking for the posting again.

## 2. Resolve the project

1. Apply `prompts/status.md` internally. Print its table only when several
   projects exist or something needs attention.
2. Take the project from the user's words when they named one.
3. Otherwise:
   - no projects yet → ask only for the repository path and derive the name
     from the folder;
   - one project with an obvious next action → select it, do not ask;
   - several → show names and short states, then ask for one.
4. Reuse the repository path stored in the project file. Never ask for it twice.

## 3. Route by state and keep going

| State | Next |
|---|---|
| No state for this project | `prompts/analyze.md` with the path and name |
| `New commits available` | `prompts/analyze.md` |
| `Capture pending` / `New commits with capture pending` | `prompts/analyze.md` |
| `Ready for batch review` | `prompts/review.md` |
| `Ready to generate artifacts` | infer interview or bullets; if unstated, recommend interview and ask one short question |
| `Reviewed and current` | fulfill a requested artifact, or say the knowledge is current and briefly offer one |
| `Needs attention` | diagnose with read-only checks, explain the concrete problem, ask only for what is needed |

Explicit `deep dive` intent goes to `prompts/analyze.md` with `DEPTH=deep`,
even when the project is already current.

**Continue automatically across steps that need no human judgement.** A
completed capture should normally reach its batch preview in the same turn.

## 4. After a review adds a newly curated project

Run these in order and report nothing unless one fails:

```bash
scripts/ekb index          # rebuild the retrieval table
scripts/ekb check          # cross-file consistency
```

Then offer `prompts/rank.md` with `PROJECT=<name>` to place the new project in
the global ranking. An unranked project cannot compete for a slot in a resume,
which is a silent way to lose good evidence.

## 5. How to talk to the user

- Before asking for context, draft the likely answer from repository evidence,
  history, architecture, and domain conventions. Present it for confirmation or
  correction.
- Group ordinary proposals and candidate decisions into **one** compact batch.
- Ask separately only when an unobservable high-risk fact would materially
  change the output: leadership, an achieved metric or business result,
  production validation, or whether the user participated at all.
- If the user skips or cannot remember, keep the best guess `inferred` and
  continue with what is publishable.
- Meaningful participation permits feature-level "worked on" or "contributed
  to" wording. Do not demand component-by-component attribution.

Never auto-approve candidates and never convert an inference into user-stated
context on your own. One clearly phrased batch confirmation may approve many
records at once; silence may approve none.

## 6. When to stop

Stop when, and only when:

- one compact human judgement is required;
- the screening gate is waiting for a decision;
- the requested artifact is ready;
- the project is current and nothing else was asked;
- a safety or evidence problem blocks the work.

At completion, summarize the outcome and the single human action still
outstanding, if any. Never leave the user to remember the next command.
