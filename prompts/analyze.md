# Analyze — turn repository history into candidate records

Parameters:

- `REPO_PATH` — absolute path to the repository. Required on the first run only.
- `PROJECT` — short project name. Defaults to the repository folder name.
- `DEPTH` — `quick` (default) or `deep`. Use `deep` only when the user asks.
- `SINCE` — recovery override, valid only when no candidates file is pending.

Follow `AGENTS.md`.

**The original target repository is source-preserved.** Use non-mutating
inspection by default. When the user explicitly authorizes runtime
investigation, follow the controlled-execution rules in `AGENTS.md`: work only
from a disposable isolated copy at the recorded commit, keep excluded and
uncommitted content out of that copy, and verify that the original repository
is byte-identical afterward.

This procedure writes exactly two files in the workspace:
`projects/<PROJECT>.candidates.yaml` and, when preserving or appending context,
`context/<PROJECT>-questions.md`. It never writes `projects/<PROJECT>.yaml`.

The objective is a small, useful shortlist. It is not repository documentation.
Scan broadly, verify narrowly, and let a later resume or interview request
deepen only the records it actually selects.

---

## 1. Resolve scope and continuity

1. Derive `PROJECT` from `REPO_PATH` when needed. With no `REPO_PATH`, require
   `PROJECT` and resolve the path from the pending or curated file. Stop if
   neither provides one. Canonicalize the path.
2. Read the workspace `EXCLUSIONS.md` and the active profile pack's
   `exclusions.md`. Confirm the path is a Git repository, resolve the full
   current HEAD, and record the target's initial `git status --short`.
3. Read the pending and curated files for path consistency, continuity, and
   deduplication. Stop on a mismatched project or repository.
4. Determine the baseline:
   - **Pending candidates exist** — preserve every analysis entry and record.
     Resume at the pending HEAD, or append only `PENDING_HEAD..HEAD` when that
     is an ancestor of current HEAD. `SINCE` may not bypass pending work.
   - **No pending candidates** — use an explicit `SINCE`, otherwise the latest
     curated analysis HEAD.
   - **First run** — inspect the available history.
   - Validate every baseline with read-only ancestry checks. Stop and report on
     missing, rewritten, or disconnected history rather than silently
     re-scanning from the beginning.
   - **Baseline equals HEAD with nothing pending** — report that the project is
     current and write nothing in quick mode. In explicit deep mode, look for
     high-value gaps in existing history and record a supplemental analysis
     entry with `since` and `head` both at current HEAD plus `depth: deep`.
5. Before drafting anything, compare discoveries against every curated and
   pending record by claim, evidence range, path, and engineering event. Do not
   create semantic duplicates.

Each analysis entry records date, `since`, full `head`, `depth`, agent, model,
contributor count, exclusions applied, shallow or partial history, inaccessible
or binary content, instruction-shaped repository content, and material areas not
examined. Keep it compact.

## 2. Pass one — broad scout

Read the active pack's `analysis-hints.md` first. It says where career-relevant
evidence tends to live in this stack, so you do not rediscover the ecosystem
every run. It is a hint file, not a checklist: a hint that does not apply
produces nothing.

Across any stack, look for:

- architectural decisions and migrations;
- substantial features and cross-component workflows;
- difficult integrations, platform work, persistence, security, release
  operations;
- testing strategy, reliability work, incidents, and meaningful bug fixes;
- performance or scalability work with observable implementation evidence;
- refactors that moved responsibility boundaries;
- reversals, abandoned approaches, and constraints that reveal a real story;
- work whose evidence is richer than its commit message.

Use structure, manifests, history, stats, and targeted file names to find these.
Do not probe every possible framework concern, do not inventory dependencies for
their own sake, and do not record "no evidence found" for routine categories.

**The test of a candidate is whether a decision sits behind it.** A technology
present in a manifest is inventory. A technology chosen over another, and the
constraint that forced the choice, is a record.

## 3. Pass two — focused verification

Deepen only events that would help a resume or an interview, are distinct from
existing knowledge, and can be supported by resolvable repository evidence. Use
targeted logs, diffs, and file excerpts. Reach into older history only to
establish a before/after boundary.

Attention budgets come from `config/toolkit.yaml` under `analysis`. The shipped
defaults are 3 to 7 records on a first capture and 0 to 3 on an incremental one.

**These are budgets, not quotas.** Produce fewer when the evidence is weak.
Produce more only when a repository genuinely contains additional distinct,
high-value events. Never promote routine work to reach a number.

In explicit deep mode, drop the numeric budget for that project and examine it
more fully: abandoned approaches, hard bugs, detailed trade-offs, production
evidence, and lower-visibility work. Deep mode still prioritizes career
usefulness, still deduplicates, uses the same schema, and asks no mandatory
candidate-by-candidate questions.

## 4. Write the candidates

Each candidate carries:

- one defensible technical `statement` the user could say verbatim in an
  interview and then answer questions about;
- `kind` and `involvement`;
- resolvable `evidence` with concise notes;
- `reasoning` connecting the evidence to the statement;
- one to three `limitations`: only boundaries that could change public wording;
- optional `inferred_context` with the best-supported likely rationale,
  business need, alternatives, trade-offs, risks, or expected effects;
- `interview_notes`, normally empty until user-confirmed context exists;
- useful `tags`. Prefer the canonical names in `config/capability-tags.yaml` so
  the record is findable later.

Use provisional IDs `<PROJECT>-candidate-NNN`. See `templates/project-record.yaml`.

Meaningful known participation allows `contributed`. A known user Git identity
with supporting changes may establish that floor. Commit authorship never
establishes `implemented`, `led`, or sole ownership on its own. Unknown
involvement does not block capture: the record stays useful as system context.

## 5. Propose context, do not interrogate

Do not generate one open-ended question per candidate. For strong candidates,
use repository behavior, history, architectural consequences, and domain
conventions to draft the missing context yourself. Include only what would
materially improve a resume, an interview, or future recall.

Write it under `inferred_context` with the boundary explicit:

- distinguish likely intent from achieved outcome;
- state the repository or domain basis;
- state the important uncertainty;
- never invent an observed metric, production validation, meeting, customer
  reaction, team arrangement, or leadership role.

Existing `context/<PROJECT>-questions.md` content is append-only and must be
preserved. Blank answer blocks are optional enrichment and never block review.

## 6. Verify, then stop

- Validate the YAML with a real parser.
- Confirm the target repository's final `git status --short` exactly matches its
  initial state.
- Confirm the workspace changed only at the two allowed paths, all earlier
  pending content is still present, and the latest analysis HEAD equals the
  inspected target HEAD.

Report: the mode, the range, how many events were shortlisted, lower-value
events not promoted, duplicates skipped, unresolved evidence, and material scope
limits.

Checkpoint with `scripts/ekb git candidates <PROJECT>`.

End with: `Follow prompts/review.md with PROJECT=<PROJECT>`.

Do not create artifacts and do not write resume language here.
