# Rank — one global ordering of every curated project

Parameter:

- `PROJECT` — optional. Place one newly curated project without re-scoring the
  whole portfolio.

Follow `AGENTS.md`. This procedure writes `profile/project-ranking.yaml` and
nothing else. It ranks evidence that already exists; it never creates any.

---

## Why a job-independent ranking exists

Selection under time pressure defaults to recency, and recency is a bad proxy
for professional value. The strongest project in a portfolio is often two years
old, and the newest is often a small contract.

Ranking once, away from any specific job, means a later selection can break a
tie in one lookup instead of re-deriving a judgement while also drafting.

**The ranking is private.** No rank, tier, score, or dimension value may appear
in any generated document, and no wording may be derived from one. "A
high-complexity project" is not a supported claim; it is a score talking.

---

## 1. Load

Read every curated `projects/*.yaml`, `profile/professional-profile.yaml`, and
`profile/profile.yaml`. Never read candidate files, generated artifacts, or
target repositories. A project with no curated file cannot be ranked: list it
under `not_ranked` with the reason.

## 2. Score

Nine dimensions, each 0 to 3. Coarse on purpose: the score is a documented basis
for an ordering, not a measurement.

| Dimension | What it reads |
|---|---|
| `complexity` | engineering difficulty and technical depth |
| `architecture` | structural work, layering, testing, delivery practice |
| `scale` | size of the system and of the change surface |
| `maturity` | production reality: released, in use, maintained over time |
| `ownership` | supported involvement (`led` > `implemented` > `contributed`) and authorship share |
| `collaboration` | client, requirements, or cross-functional evidence |
| `distinctiveness` | rarity inside THIS portfolio, not in the industry |
| `resume_value` | how well one bullet survives a recruiter's read |
| `interview_value` | how well it survives fifteen minutes of questions |

Calibration that matters:

- `maturity` — a demo, proof of concept, or never-published build scores at most
  1. An academic build scores 0.
- `ownership` — follows supported involvement, never commit count.
- `distinctiveness` — a common technology can be distinctive here if only one
  project uses it.
- `resume_value` and `interview_value` must fall when a cap forces a qualifier
  to travel with every sentence about the project.

**Do not score business impact.** Unless the user supplied revenue, retention,
adoption, or usage data, estimating it is forbidden by `AGENTS.md`.

## 3. Order

`rank` follows score order and every rank is unique. Record `tie_with` and a
one-sentence `tie_break` whenever scores are equal.

Depart from score order only when a standing placement constraint caps a
project's professional value below its engineering substance. State that
exception in `rank_basis` on the entry, so the divergence reads as deliberate
rather than as an error.

Assign `tier` from the bands in the file header. Set `placement` to
`experience`, `selected-projects`, or `education` from the career map.

`placement` is the **preferred public section, not an eligibility boundary**. A
resume may use a project's evidence elsewhere when that has higher marginal
value, while still avoiding a duplicated accomplishment.

## 4. Carry the caps forward

Every entry repeats, in short form, the limits that bind selection: minority
authorship, demo qualifiers, counting rules, academic placement, unconfirmed
links, and any record that must never reach a resume. Add `never_with` when a
counting rule forbids two projects being cited for the same claim.

Resolve project identity before ranking or selection. Two labels that point to
the same confirmed store URL, repository, white-label base, or underlying
product are not automatically two public projects. Record the canonical project
and a counting or `never_with` rule so a later resume cannot duplicate the work
under different headings.

**A ranking that loses a cap is worse than no ranking**, because it invites a
selection the evidence cannot support.

Fill `links` with the slot names present for that project in `profile.yaml`
`project_links`, and only where `link_status: confirmed`.

## 5. Refresh mode

With `PROJECT` supplied: score that project, insert it at the position its score
earns, renumber the ranks below it, and leave every other entry's dimensions
untouched. Update `basis.curated_projects`, `basis.records_considered`, and
`updated_at`. Note the scoped update in a comment near the header rather than
rewriting `basis.method`.

## 6. Verify

Check mechanically that ranks are unique and gapless, that every
`sum(dimensions)` equals its `score`, that every curated project appears exactly
once, and that every record ID in `best_evidence` exists in the file it names.
`scripts/ekb check` covers all four.

## 7. Deliver

Report the ordering, every change from the previous ranking with its reason, and
any project whose rank now turns on a single unresolved question.

Checkpoint with `scripts/ekb git profile` only if the user asks; this file is
profile-scoped, so profile consent applies.
