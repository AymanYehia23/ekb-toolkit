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
- omit every record with `resume_eligible: false`; it is retained for technical
  or interview history and may not source public bullet prose;
- never strengthen certainty, causality, achieved impact, involvement, or scope
  beyond the record;
- source comments as `<!-- src: PROJECT-NNN -->`.

**Omit unconfirmed `inferred_context` entirely.** A bullet bank is public prose.
An inference laundered into a bullet is the exact failure this system prevents,
and it is easier to do here than anywhere else because bullets are short.

## Write the bullets

Default to three to five bullets from the strongest records. Keep only two when
only two survive the quality gate; never pad a project with a weak third bullet.
Add a second variant only when it is a genuinely useful concise-versus-technical
choice, not a routine duplicate.

Write every publishable bullet as a top-level Markdown list item beginning with
`- `. Continuation lines and the bullet's source or variant comments must stay
inside that list-item block. The validator treats other prose as context, not as
a publishable bullet, and rejects a bank that cites records but contains no
parseable list items.

Store an approved alternative as
`<!-- variant concise: Complete alternative sentence. -->` inside the same
bullet block after its source comments. The variant obeys every wording rule
and uses the same sources; never create a second top-level bullet for it.

After the source comments, add exactly one private semantic review comment:

```html
<!-- quality: {"level":"impact","result_type":"delivery","change":"Testers can use one installed build across declared environments.","metric":{"status":"not-applicable"},"checks":{"specificity":"pass","ownership":"pass","result":"pass","evidence":"pass","metric":"not-applicable","relevance":"pass","readability":"pass","credibility":"pass"}} -->
```

Use single-line valid JSON. The review is an auditable decision, not public
resume prose. `level` must be `outcome`, `impact`, or `scope`; activity-only
work is not publishable. A scope-level bullet also needs
`scope_justification`. Classify `result_type` as user, product, business,
engineering, delivery, reliability, team, scale, security, or other.

Record the metric decision rather than merely scanning for digits:

- `used` with the exact evidence basis;
- `available-not-used` with the basis and why the number adds no value;
- `not-applicable` when no useful defensible number exists;
- `estimated-not-used` with observed basis, assumptions, calculation,
  confidence, and `resume_use: false` until the estimate is confirmed through
  the normal evidence-review workflow.

All eight checks must pass, except metric may be `not-applicable`. `result`
asks what became possible, different, safer, more reliable, broader, or
measurably better. Intent alone (`to improve...`) does not pass. `evidence`
means every part of that answer is licensed by the cited curated record and its
limitations. `credibility` means the user could defend the wording without
adding a fact that is absent from the record.

This procedure is stack-agnostic. Apply the same judgement to mobile, web,
backend, data, desktop, embedded, infrastructure, developer tooling, and any
other engineering work. A framework name can explain the work; it is not the
achievement by itself.

### Select at the right altitude

Evaluate each candidate in this order:

1. **Outcome**: a measured or observed change supported by before/after evidence.
2. **Impact**: a verified user, product, operational, reliability, delivery, or
   organizational consequence.
3. **Scope**: a materially broad system, workflow, migration, integration, or
   reusable capability.
4. **Activity**: implementation work with no demonstrated consequence or useful
   scope.

Prefer Outcome over Impact, Impact over Scope, and Scope over Activity. Drop an
activity-only record when stronger evidence exists. Do not manufacture an
outcome or force a "so that" clause merely to make an activity sound important.
When no measured result exists, a precise structural result such as
"consolidated four request paths into one endpoint" is stronger and safer than
"improved performance."

Reject as primary bullets:

- routine configuration, dependency updates, isolated fixes, and narrow UI
  details unless they removed a meaningful constraint or carried unusual risk;
- counts of lines, files, classes, commits, or tests presented as the result;
- a framework or architecture inventory with no delivered capability;
- duplicate examples of a capability already represented by stronger evidence;
- a list of everything changed in a commit or feature.

### Write one defensible achievement

Use this semantic shape, not a rigid sentence template:

> direct contribution + delivered or changed capability + verified consequence
> or meaningful scope + only the distinguishing technical proof

Lead with what changed, not the technology used. Name the affected workflow,
system boundary, user, or operational process when the source supports it. Keep
one main idea per bullet and select at most two or three technical mechanisms
that explain why the work is non-trivial. If the sentence becomes a
comma-separated inventory, choose the decisive details and remove the rest.

Calibration examples show the altitude, not wording to copy:

| Weak shape | Better shape |
|---|---|
| Built a mobile app using Framework X and state management Y. | Unified two reservation types in one booking workflow with server-validated cancellation rules. |
| Worked on backend APIs with Runtime X and Database Y. | Consolidated four catalog lookups into one typed endpoint shared by product and checkout flows. |
| Implemented CI/CD using several cloud tools. | Automated signed release builds and internal distribution with deterministic versioning and rollback controls. |
| Created a data pipeline with queues and object storage. | Isolated malformed records while preserving valid batches for retryable downstream processing. |

The better shape is eligible only when the cited evidence supports every part.

Every publishable bullet must:

- be one sentence and at most `bullet_quality.maximum_words` words;
- end with terminal punctuation;
- make sense to an engineer outside the original codebase;
- avoid vague duty openings listed in
  `config/resume-policy.json` `bullet_quality.forbidden_openings`;
- use no more than `bullet_quality.maximum_sources` independently eligible
  sources;
- survive the counterfactual question: *what capability, constraint, or result
  would be missing if this work had not happened?*

Rules:

- precise engineering language, natural sentence variation;
- direct verbs when involvement supports them;
- scoped contribution wording for meaningful shared participation; name the
  contributed component when the evidence supports that boundary, and use
  feature-level "contributed to" only when it does not;
- neutral technical results are allowed without a metric: "introduced",
  "consolidated", "replaced", "enabled";
- confirmed purpose wording such as "to support..." is allowed, but intent is
  not achieved impact;
- never prefix a publishable bullet with a provenance label;
- never invent a number, metric, business result, responsibility, or leadership
  claim;
- honor `config/resume-policy.json` `writing_style`, `quantifier_quality`, and
  `bullet_quality`;
- never use "improved", "reduced", "accelerated", "simplified", or equivalent
  comparative language without a supported before/after basis;
- do not begin with "Used <technology>" or "Built with <technology>" when the
  delivered capability can lead instead.

Put the source comment immediately after each bullet.
Put its quality comment immediately after the source and variant comments.

## Not selected

End with a compact `Not selected` section listing record IDs only, grouped by
reason: resume-excluded, low relevance, redundant coverage, unknown
participation, insufficient support.

This is an internal selection audit, not extra resume content. It is here so a
later reader can see that a record was considered and passed over, rather than
wondering whether it was missed.

## Verify and finalize

Map every source comment to a real curated record. Compare every bullet against
its statement, evidence, limitations, and involvement. Confirm no provisional
inference reached the public text. Confirm the quality comment answers all eight
checks and records the metric decision. Then run `scripts/ekb check`; do not
checkpoint a bank that fails its bullet-quality checks.

Report the output path and the selected record IDs. Checkpoint with
`scripts/ekb git artifact <PROJECT> bullets`.

Ask the user to review the short selection. Do not ask them to review every
curated record.
