# FitTrack — context log

<!--
FICTIONAL EXAMPLE.

This file is append-only. It holds agent proposals, the user's confirmations
and corrections, evidence follow-ups, and every review decision. A curated
record cites a stable anchor here when its interview notes came from a
conversation rather than from the repository.

Preserve every existing user answer byte-for-byte. Blank answer blocks are
optional enrichment and never block a review.
-->

## 2026-02-02 — agent proposals

### fittrack-candidate-001 — cache consolidation

**Likely context (agent-inferred).** The change lands on a branch named
`hotfix/history-stale` and ships the same day, which suggests a support issue
rather than a planned refactor. Basis: branch name and commit timing.
Uncertain: whether a specific customer report triggered it.

**A:** Yes, support report. Two users logged workouts that disappeared and came
back a day later. We could not reproduce it until we noticed the second cache
was writing after the first.

<a id="fittrack-001"></a>
**Decision anchor:** `fittrack-001` — confirmed 2026-02-04.

### fittrack-candidate-002 — offline queue

**Likely context (agent-inferred).** Last-write-wins looks like a deliberate
simplification rather than an oversight: `conflict.dart` is a single comparison
with tests for both orderings, which is not what an accidental rule looks like.
Basis: implementation shape. Uncertain: what the alternative was.

**A:** Correct. We considered a field-level merge but that needed a server
change we did not own. A workout entry is small and immutable so last-write-wins
was honest rather than lazy.

<a id="fittrack-002"></a>
**Decision anchor:** `fittrack-002` — confirmed with correction 2026-02-04.

### fittrack-candidate-004 — release pipeline

**Question (high-risk).** This one wants `led`. Git shows a single identity
across the whole series, but authorship is not ownership. Did you own this
work, and did anyone else decide its shape?

**A:** I owned it. I proposed it, built it, and documented it. Store listings
and release approvals stayed with the product owner, so it is not end-to-end
release ownership.

<a id="fittrack-004"></a>
**Decision anchor:** `fittrack-004` — `led`, scoped to the pipeline, 2026-02-04.

---

## 2026-02-04 — review-decisions

- `fittrack-candidate-001` → **keep** as `fittrack-001`. Inferred context
  confirmed and moved to `interview_notes`.
- `fittrack-candidate-002` → **keep** as `fittrack-002`. Proposal corrected;
  only the correction stored as user-stated context.
- `fittrack-candidate-003` → **edit**, then keep as `fittrack-003`. The draft
  said "improved performance by 70 percent". Corrected to the measured 31 ms to
  9 ms with its device and build-mode context, because a percentage hides the
  fact that this is a profile-mode figure on one device.
- `fittrack-candidate-004` → **keep** as `fittrack-004` with `involvement: led`
  scoped to the pipeline, per the answer above.
- `fittrack-candidate-005` → **keep** as `fittrack-005` at `contributed`. Three
  identities in the range; the user confirmed shared work.
- `fittrack-candidate-006` → **drop**. "Migrated to null safety" is real but
  routine, has no decision behind it, and would not survive a follow-up
  question.

---

## 2026-03-01 — review-decisions

Incremental run over `4f2a1c9..9c1b0a8` produced no new candidates. The range
contains dependency bumps and copy changes only.

Recorded so the HEAD advances: the next analysis starts from `9c1b0a8` rather
than re-scanning history that has already been judged.
