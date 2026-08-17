# Professional profile — what holds across projects

Parameters, all optional:

- `SCOPE` — `full` (default) or `project:<name>` to weigh one newly curated
  project into an existing profile without re-deriving everything.

Follow `AGENTS.md`. This procedure writes
`profile/professional-profile.yaml` and logs its reasoning in
`profile/professional-profile-context.md`. It writes nothing else.

---

## What this file is for

A curated record says what happened on one project. A resume summary, a
LinkedIn-style headline, a cover letter, and an interview opener all need
something a single record cannot supply: **what is true about this engineer
across projects**.

Deriving that fresh inside every generation turn produces a different answer
every time and quietly launders single-project facts into career-level claims.
This file makes the derivation happen once, on purpose, with its basis written
down.

## What this file is not

**It is derived. It is never an independent source of facts.**

A strength named here still needs an eligible curated record or a confirmed
profile fact behind any public claim. The professional profile guides selection
and framing. It never substitutes for a source reference, and an ID defined
here is not usable as one.

If it reveals that a target-critical fact exists nowhere citable, that is a
finding, not a bridge. Route a reusable fact through `prompts/profile.md` or a
project fact through `prompts/review.md` before selection. Do not silently
substitute weaker evidence and do not let the derived file carry the claim.

---

## 1. Read everything, then count

Read every curated `projects/*.yaml`, `profile/profile.yaml`, and the previous
version of this file. Never read candidate files, generated artifacts, or target
repositories.

Record in `current_coverage` how many curated projects and records this pass
actually weighed, and the date. Staleness must be readable without a full
re-read: a project curated after the last pass should leave a visible trace.

## 2. Derive strengths

A **strength** is a capability that recurs across projects and that the evidence
supports at a stated depth. Each entry carries:

- a plain statement of the capability;
- a `tier`: `signature`, `core`, or `supporting`;
- the record IDs behind it, from at least two projects for `core` and above;
- `resume_usage` — the altitude and phrasing that stay honest;
- the boundary where the evidence stops.

Tier is about evidentiary weight, not enthusiasm.

- `signature` — several projects, deep records, supported involvement, and
  distinctive inside this portfolio. This is what the engineer leads with.
- `core` — solid recurring evidence.
- `supporting` — real but thin, or narrow, or mostly `contributed`.

**Do not invent a strength to round out a picture.** A portfolio with two
signature strengths and nothing else is an accurate portfolio.

## 3. Derive the professional brand and summary strategy

Determine what kind of engineer the complete evidence actually shows. This is
selection, not a compressed inventory of every project.

Write `resume_summary_strategy` with:

- `master_brand` — the supported professional identity, primary technical
  specialization, and the few differentiators that recur strongly enough to
  survive a short recruiter scan;
- `master_resume` — what a general summary should lead with, which scale or
  delivery proof is worth the space, and which true details belong lower in the
  document;
- `targeted_resume` — how targeting may narrow or reorder that identity without
  inflating a small exposure;
- `venue_carryover` — what must remain consistent across resume, profile,
  portfolio, cover-letter, and interview-introduction variants.

Start from confirmed role nouns, timeline, skills, and responsibilities in
`profile.yaml`, then weigh recurring project evidence. Never infer a seniority
label from technical depth or project volume. Express technical strength as a
coherent thesis, such as architecture plus a distinctive integration context,
not as a package inventory.

Look for the professional meaning behind activities. Confirmed requirements
meetings, feature discussions, and demos may show the ability to understand an
operating problem, translate it into product and technical decisions, and carry
the result through delivery. They do not create a product title, commercial
outcome, or leadership claim.

Store the strategy, not a polished reusable paragraph. Exact prose is generated
for each venue, and every public clause still needs citable profile facts or
eligible curated records.

## 4. Derive the career map

Place every curated project under exactly one context: an employer, independent
work, or academic work. This is what stops a personal project drifting into
employment history in a generated resume.

Every project must appear exactly once, and the map must agree with
`profile.yaml` `experience[].projects`. `scripts/ekb check` enforces both.

## 5. Derive standing constraints

This is the most valuable section and the one most likely to be skipped.

A **constraint** is a rule that binds every artifact, in addition to each
record's own limitations. Constraints exist because some truths are only
visible across projects:

- **counting rules** — a component reused across a fleet is one piece of work,
  counted once, not once per project. A product line with many white-label
  builds is one claim, not many.
- **never together** — two projects that must not both be cited for the same
  claim because they share the same underlying work.
- **placement** — work that must appear in a specific section, such as academic
  work that may never sit inside Experience.
- **do not claim** — anything the evidence cannot support that a generator would
  otherwise be tempted by.
- **unlocks** — the rare inverse: a specific measurement that DOES license
  comparative language for one specific claim.

Every constraint states its reason. A constraint with no reason gets removed by
someone six months from now who cannot tell whether it still applies.

## 6. Character

Recurring working traits, each with the record IDs that show them. Traits are
the hardest thing here to keep honest, because every adjective sounds true.

The test: **name the records where the trait is visible, and name the projects
where it is not.** A trait that cannot fail this test is a compliment, not an
observation.

## 7. Scoped mode

With `SCOPE=project:<name>`, weigh only that project into the existing profile:

- update `current_coverage` and note what the project added, or that it added
  nothing;
- amend `resume_summary_strategy` only when the project materially changes the
  durable professional identity or its evidence weighting; otherwise record
  that the strategy was tested and stayed unchanged;
- amend only the strengths, constraints, and career map entries it touches;
- leave `validation_basis` recording the last FULL derivation, and do not
  rewrite it.

A project that adds no new capability is a normal outcome. Record that it was
weighed and what it did not change, so the next pass does not re-litigate it.

## 8. Verify and log

Check mechanically that every record ID cited here exists in a curated file,
that no superseded record is still cited, that every curated project appears in
exactly one career-map context, and that any stated count matches its list.
`scripts/ekb check` does all of this.

Append the reasoning to `profile/professional-profile-context.md`: what changed,
what evidence moved it, and what was considered and rejected. The context file
is why a future session can tell a deliberate decision from a drift.

Report what changed and what stayed. Checkpoint with `scripts/ekb git profile`
only if the user asks; profile consent applies.
