# Bullets — a single-project resume bullet bank

Parameters:

- `PROJECT` — one project.
- optional target role or job context to guide selection.

Follow `AGENTS.md`. This is a **lightweight single-project bullet bank**, not a
complete application resume. Route `resume`, `job`, or `apply` intent to
`prompts/resume.md` instead.

The bank exists so wording is distilled once, close to the evidence, rather than
re-invented inside every application. The evidence index lifts these phrasings
later as suggestions for resume drafting.

This procedure is a read-only consumer of curated knowledge. It writes only
`artifacts/bullets/<PROJECT>.md`.

---

## Sources and limits

Identical to `prompts/interview.md`:

- facts from `projects/<PROJECT>.yaml` only;
- `profile/professional-profile.yaml` for standing constraints, which bind in
  addition to each record's own limitations;
- never strengthen certainty, causality, achieved impact, involvement, or scope
  beyond the record;
- source comments as `<!-- src: PROJECT-NNN -->`.

**Omit unconfirmed `inferred_context` entirely.** A bullet bank is public prose.
An inference laundered into a bullet is the exact failure this system prevents,
and it is easier to do here than anywhere else because bullets are short.

## Write the bullets

Three to five, from the strongest records. Add a second variant for a record
only when it represents a genuinely useful concise-versus-technical choice, not
as a routine duplicate.

Rules:

- precise engineering language, natural sentence variation;
- direct verbs when involvement supports them;
- feature-level "worked on" or "contributed to" for meaningful shared
  participation, without demanding component boundaries;
- neutral technical results are allowed without a metric: "introduced",
  "consolidated", "replaced", "enabled";
- confirmed purpose wording such as "to support..." is allowed, but intent is
  not achieved impact;
- never prefix a publishable bullet with a provenance label;
- never invent a number, metric, business result, responsibility, or leadership
  claim;
- honor `config/resume-policy.json` `writing_style`: no em dash, en dash, or
  arrow, and none of the listed generic terms.

Put the source comment immediately after each bullet.

## Not selected

End with a compact `Not selected` section listing record IDs only, grouped by
reason: low relevance, redundant coverage, unknown participation, insufficient
support.

This is an internal selection audit, not extra resume content. It is here so a
later reader can see that a record was considered and passed over, rather than
wondering whether it was missed.

## Verify and finalize

Map every source comment to a real curated record. Compare every bullet against
its statement, evidence, limitations, and involvement. Confirm no provisional
inference reached the public text.

Report the output path and the selected record IDs. Checkpoint with
`scripts/ekb git artifact <PROJECT> bullets`.

Ask the user to review the short selection. Do not ask them to review every
curated record.
