# Configuration reference

Everything in `config/` is a safe, shared default. No prompt hardcodes a
preference that belongs to one person's career.

Keep personal settings in `workspace/config/`, outside the public toolkit
repository. A file there with the same name overrides the shipped default, so
you can pull or push the toolkit without carrying your preferences with it.
`EKB_WORKSPACE` is the recommended way to select an external workspace.

| File | Shipped default | Private override |
|---|---|---|
| `toolkit.yaml` | `config/toolkit.yaml` | `workspace/config/toolkit.yaml` after `EKB_WORKSPACE` has selected the workspace |
| `resume-policy.json` | `config/resume-policy.json` | `workspace/config/resume-policy.json` |
| `review-rubric.json` | `config/review-rubric.json` | `workspace/config/review-rubric.json` |
| `capability-tags.yaml` | `config/capability-tags.yaml` | `workspace/config/capability-tags.yaml` |
| `screening-criteria.yaml` | `config/screening-criteria.yaml` | `workspace/profile/screening-criteria.yaml` |

The initial workspace location still comes from `$EKB_WORKSPACE` or the shipped
`config/toolkit.yaml`; a private `toolkit.yaml` cannot select itself. Once the
workspace is selected, it can override the remaining global settings.

---

## `config/toolkit.yaml`

### `paths.workspace`

Where your knowledge base lives. The single most useful setting to change.

```yaml
paths:
  workspace: ~/ekb
```

The default (`./workspace`) keeps everything inside the clone for a frictionless
first run. Once you have more than a few projects, move it out and give it its
own Git repository. `$EKB_WORKSPACE` overrides this at runtime.

### `paths.profile_pack`

Which role profile pack is active. Only `profiles/flutter-engineers` ships
today. See [extending.md](extending.md).

### `analysis.first_capture` / `analysis.incremental_capture`

Attention budgets for one analyze run, as `[min, max]`.

```yaml
analysis:
  first_capture: [3, 7]
  incremental_capture: [0, 3]
```

**These are budgets, not quotas.** A thin repository should produce two records,
not seven padded ones. Raise them if your repositories are unusually dense; the
real limit is how many claims you can defend, not how many the agent can find.

### `analysis.default_depth`

`quick` scans broadly and verifies narrowly. `deep` drops the numeric budget for
one project. Leave this at `quick` and pass `DEPTH=deep` per project — deep mode
on every run is how a knowledge base fills with records nobody will ever use.

### `evidence.eligible_kinds` / `evidence.eligible_involvement`

Which records may support a public claim.

```yaml
evidence:
  eligible_kinds: [repo-verified, user-stated]
  eligible_involvement: [led, implemented, contributed]
```

**Loosening either of these is how a knowledge base stops being defensible.**
Adding `inferred` to `eligible_kinds` means agent guesses can become resume
lines. Adding `unknown` to involvement means work you may not have done can be
claimed as yours.

There is one legitimate reason to tighten them: dropping `contributed` if you
only want sole-authored work in your documents.

### `evidence.limitations`

`warn` (default), `require`, or `off`. Whether a record needs a stated
limitation before it can be curated.

`require` is worth trying for a month. Most records genuinely have one, and
writing it during review takes ten seconds while reconstructing it later is
impossible.

### `resume.default_market`

`europe` renders A4, `north-america` renders Letter. The fallback when a posting
names no location.

### `resume.competing_drafts`

`on-request` (default) or `always`. Whether to build two drafts with different
selection strategies and score them against each other. It costs a second full
selection pass, which a routine application does not earn.

### `cover_letter.target_words` / `cover_letter.maximum_words`

The optional letter aims at 300 words and has a hard 400-word ceiling by
default. A shorter user-requested length wins. These settings change space, not
evidence eligibility: the letter still reuses only the screened application's
selected, validated claims.

### `screening.enabled`

`true` by default. Setting it to `false` lets postings flow straight into a full
tailoring pass. Consider what the gate costs you before turning it off: it reads
three files and stops, and the pass it protects reads everything.

---

## `profile/screening-criteria.yaml` (in your workspace)

What a job posting gets flagged for, and how loudly. **Policy, never evidence:**
it states no fact about you, and every check compares against a fact in
`profile.yaml` referenced by ID.

### `checks[0].domains` — ships empty

The domain-exclusion list is empty on purpose. People decline sectors for
ethical, religious, legal, health, and personal reasons, and a shipped default
would be one person's list imposed on everyone.

Fill in yours:

```yaml
domains:
  - id: screen-domain-001
    label: <the sector you decline>
    severity: blocker            # blocker | warning | note
    signals: [<words a posting in that sector would use>]
    explain: >-
      Optional. What the finding should say beyond naming the sector.
```

Leave it empty and the check reports `not_assessed` with the reason, rather than
silently skipping.

Use `warning` rather than `blocker` for a sector you want surfaced but will
judge case by case. High recall with a low severity is usually the right shape:
the value is never missing the sector on a first read, not automating a
rejection.

### `checks[1].profile_basis` — work authorization

These IDs must exist in your `profile.yaml` under `work_eligibility`:

```yaml
profile_basis:
  - profile-eligibility-001    # citizenship
  - profile-eligibility-002    # authorization and sponsorship need
  - profile-eligibility-003    # relocation intent
```

If they do not exist, the check reports that it could not run. That is the
correct behavior: an absent fact is better than a guessed one.

### `checks[3]` — role alignment

`aligned_anchors` and `misaligned_archetypes` read `from-profile-pack`, so
switching packs switches alignment. Override them here if your work does not
match the pack cleanly.

### `checks[3].seniority.rules`

Adjust `screen-rule-013` to taste. It flags titles implying formal team
leadership. Set it to `blocker` if you never want to see those postings, or
remove it if you do.

### `positive_signals`

Replace the technology-specific entries with your own. A signal that never
fires is noise in the file; a signal that always fires tells you nothing.

### `verdict_rules`

Evaluated top down, first match wins, so the worst applicable outcome is
reported. Mechanical on purpose: the same posting should produce the same
verdict twice.

### `gate`

```yaml
gate:
  always_wait_for_user: true
  auto_proceed_on_clean_report: false
```

Both are the feature. See [concepts.md](concepts.md#the-screening-gate).

---

## `config/resume-policy.json`

Read by both the renderer and the source checker, so a change takes effect in
DOCX, PDF, and validation at once.

### `writing_style`

The forbidden terms and punctuation. **This is a default, not a doctrine.**

The em dash and en dash are on the list because they are the most reliable
visual tell of generated text in a document nobody expects to be typeset. The
word list is the usual filler.

Edit it. Remove a word you actually use well; add one you have seen too often.
The list is small, explicit, and version-controlled so the preference stays
auditable rather than becoming folklore.

### `summary.default_words`

90, across four to six complete sentences. **A ceiling, not a target.** The
summary covers supported professional identity, relevant experience and
expertise, career direction, and applicable confirmed mobility context. It is
also the only place a cross-project fact can live, because a bullet describes
one project. Never pad or invent context to fill the sentence count.

### `emphasis.max_terms`

12. Past roughly a dozen bolded terms nothing stands out any more. Overflow is
reported rather than silently dropped.

### `experience_budget`

Bullets per role, engagements per role, bullets per engagement. Enforced as
warnings, not truncation — the schema bounds are wider on purpose so a genuinely
dense role is not cut by policy.

### `content_density.single_page_minimum_usable_height_ratio`

0.84. A one-page resume using less than 84% of the printable height is
underfilled even with no clipping. The fix is more evidence, never a longer
summary.

### `page_length`

One page through five confirmed years of experience; up to two pages for a
longer career when relevant evidence needs the space. This controls editorial
planning, not a public years-of-experience claim.

### `contact_hygiene` and `languages`

Missing email, phone, professional profile links, and CEFR language levels are
reported as advisory warnings. The renderer never fills those gaps itself:
contact information and proficiency mappings must come from confirmed profile
data.

### `delivery`

The renderer keeps stable `resume.*` files for scripts and writes additional
attachment-ready copies using `FirstName_LastName_TargetRole_CV`. PDF output is
checked to ensure it is selectable and not password-protected.

### `bullets.*_indent_pt`

Geometry tokens consumed by both renderers so DOCX and PDF match. Neither infers
indentation from a viewer default.

### `requirements`

ATS structure: single column, one font family, two sizes, contact in the body,
no tables, no text boxes, no images, selectable PDF text. Change these only if
you know why.

---

## `config/review-rubric.json`

How the private selection score is computed. It measures **how well a resume
used the evidence available to it**, never your fit for the job.

Weights: `required_demonstrated` 45, `critical_demonstrated` 25,
`strongest_evidence_used` 20, `decisions_recorded` 10.

`calibration.observations` is empty and yours to fill. Each time you get an
external review of a generated resume, record its number beside the internal
score from the same run.

**Do not tune the weights after one or two observations, and do not blend the
two scores.** They measure different quantities: coverage grade measures how a
capability is presented, an external per-skill score measures how deep it is.
For commodity skills those are close to orthogonal. `known_limits` in the file
records this.

---

## `config/capability-tags.yaml`

Folds curated tag variants into one canonical capability, so "which records
demonstrate state management" finds `bloc`, `riverpod`, and `cubit` too.

```yaml
synonyms:
  state-management: [riverpod, bloc, cubit, provider]
```

A lookup aid and nothing more. Folding two tags does not make a claim, does not
strengthen a record, and does not change what any record says. If a fold
produces a wrong match during selection, remove it.

**An empty file is valid** and is the right setup for a small knowledge base.
Add your own stack's vocabulary rather than adopting the shipped one wholesale.

---

## Workspace files you own

| File | Written by | Notes |
|---|---|---|
| `profile/profile.yaml` | `prompts/profile.md` | The only link registry. Never hand-edit an ID. |
| `profile/professional-profile.yaml` | `prompts/professional-profile.md` | Derived. Change through the procedure. |
| `profile/project-ranking.yaml` | `prompts/rank.md` | Derived. Private. |
| `profile/screening-criteria.yaml` | you, directly | Policy. Carries no derived state. |
| `EXCLUSIONS.md` | you, directly | Add repository-specific sections before analyzing client code. |
| `.gitignore` | you, directly | Rendered documents are regenerable; decide whether to track them. |
