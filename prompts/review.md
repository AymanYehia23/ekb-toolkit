# Review — one batch decision turns candidates into knowledge

Parameter:

- `PROJECT` — the project whose candidates are being reviewed.

Follow `AGENTS.md`. **This is the only procedure allowed to write
`projects/<PROJECT>.yaml`.** The target repository stays read-only.

The objective is one compact human judgement pass. Verify the evidence yourself,
carefully, before presenting anything. Do not make the user repeat that forensic
work candidate by candidate.

---

## 1. Preconditions

1. Require `projects/<PROJECT>.candidates.yaml`. Read every analysis entry and
   record. Resolve its repository path and read the exclusions before opening
   any evidence.
2. Read the curated file for continuity and the highest stable numeric ID.
   **Never reuse an ID**, including IDs visible only in Git history.
3. Read `context/<PROJECT>-questions.md` when present. Existing answers,
   attestations, evidence follow-ups, proposals, and past decisions are
   append-only evidence. Blank answer blocks never block review.

## 2. Verify before involving the user

For every unresolved candidate, resolve its evidence with read-only Git and file
inspection. Check that:

- the statement is supported at the stated certainty and scope;
- numbers are counted, measured, or user-provided;
- comparative wording has a real before/after basis;
- expected effects are not presented as measured outcomes;
- feature participation has not been strengthened into leadership or ownership;
- the claim is distinct from curated knowledge;
- limitations contain only boundaries that could change public wording;
- inferred context states its basis and its uncertainty.

Fix purely mechanical wording or schema problems before the preview, when doing
so does not strengthen the claim. **Flag** invalid evidence, unsupported claims,
and judgement-dependent edits instead of silently repairing them.

For a candidate with no `inferred_context`, draft the likely rationale and
trade-offs yourself from its evidence, history, architecture, and domain
conventions, and treat that draft exactly like context created during capture.
Do not hand an open-ended question back to the user as a prerequisite.

## 3. The batch preview

Present all unresolved candidates in one numbered, quickly scannable batch. For
each, show only:

- the proposed statement;
- provenance and involvement;
- one material limitation or risk, if any;
- a short `Likely context (agent-inferred)` when present;
- whether the evidence check passed.

Do not dump diffs by default. Show the excerpt when the evidence check failed,
the claim is high-risk, or the user asks to see it.

Separate ordinary records from **high-risk confirmations**. High risk means a
claim of leadership or sole ownership, an observed metric, achieved business
impact, an unverified production result, or whether the user participated at
all. An architectural or business rationale inferred from the implementation is
not high-risk while it stays labelled as likely intent.

Ask for one batch response, and make the options explicit:

```text
save all and confirm the likely context
save all records; keep the likely context inferred
save all except 2 and 5
edit 3: <correction>
show evidence for 4
```

**Never keep a candidate without a decision.** One batch decision may resolve
many records. If a response resolves only part of the batch, append those
decisions and ask once about the remainder. Do not restart item by item.

Meaningful participation permits feature-level "worked on" or "contributed to"
wording without exact component accounting. Do not ask the user to divide a
shared feature line by line. Ask about participation only when it is not
otherwise supported, or when stronger `implemented` or `led` wording matters to
a claim they want.

## 4. Record the decisions

Before finalizing, append a dated `## review-decisions` entry to
`context/<PROJECT>-questions.md` for every resolved candidate, preserving the
user's exact correction or confirmation. A batch decision still gets one entry
per candidate, so interrupted work resumes deterministically.

For agent-proposed context:

- **confirmed** — preserve the proposal and the confirmation in the context
  file, move the confirmed meaning into `interview_notes` as user-confirmed
  context, add a stable context locator, and remove `inferred_context` from the
  curated record;
- **corrected** — preserve both versions, store only the correction as
  user-stated context, and remove the superseded inference;
- **record approved, proposal not confirmed** — keep `inferred_context` with its
  uncertainty. It may support a labelled interview hypothesis. It may not
  become a resume fact;
- **cannot remember** — inspect the repository yourself and keep whatever
  remains explicitly inferred.

There is no `needs-context` state. When participation is unknown, a safe
technical record may still be curated with `involvement: unknown`. When a
stronger claim cannot be supported, downscope or drop it per the user's
decision rather than blocking unrelated records.

## 5. Finalize

Finalize once every candidate has `keep`, an approved `edit`, or `drop`.

- Merge only kept and approved records into `projects/<PROJECT>.yaml`.
- Assign sequential stable IDs `<PROJECT>-NNN`.
- Preserve existing curated records byte-for-byte unless the user approved a
  disclosed edit.
- Append every new analysis entry in order, including runs that accepted no
  records, so the latest analyzed HEAD becomes the next baseline.
- Delete `projects/<PROJECT>.candidates.yaml` only after decisions, curated
  file, analysis entries, and context log are all complete.
- Validate the YAML with a real parser.

Show the resulting diff, any evidence failures, dropped candidates, and any
inferred context that remains provisional.

Checkpoint with `scripts/ekb git snapshot <PROJECT>`, which creates the next
`<PROJECT>/vN` tag locally and never pushes.

Then rebuild what depends on curated records:

```bash
scripts/ekb index
scripts/ekb check
```

End with: `Follow prompts/interview.md with PROJECT=<PROJECT>`, and mention that
`prompts/rank.md` should place a newly curated project in the global ranking.
