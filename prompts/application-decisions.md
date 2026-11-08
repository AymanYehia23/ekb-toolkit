# Application decisions

Run this procedure for a version 2 job-targeted application after the
explicit proceed gate in [screening](screen.md). Use [profile](profile.md) for
candidate updates and [résumé selection](resume.md) for editorial work.

## Inventory and match

1. Read the frozen posting in full. Record each meaningful responsibility,
   screening or evaluation criterion under `targeting.requirements` in the
   frozen intake's targeting section. Keep the original posting text intact.
   Give each row a distinct term, exact posting excerpt, priority, critical
   flag, category, aliases and an optional minimum proficiency. Keep separate
   environments and distinct qualifications separate. If the posting permits
   alternatives, keep one requirement and record which option answers it.
2. Run `ekb candidate` and `ekb shortlist ID --stdout`. Check previous answers
   through [capability discovery](capability-discovery.md) before asking a new
   question. Compare underlying sources and limitations. A retrieval hit alone
   establishes neither proficiency nor qualification.
   Read `project_leads` for the complete set of eligible project matches to
   each requirement. The candidate display limit applies to the detailed
   examples. Search curated records independently for relevant work missed by
   the alias search.
3. Run `ekb requirement-map ID --skeleton` and author the reviewed copy at
   `applications/ID.requirements.yaml`. Fill `reviewed_by`, `inventory_review`
   and `positioning` after checking the entire posting and deciding what the
   opening should prove. Record a concrete reason and stable source IDs on
   every row. Use the private reason to preserve scope, the remaining gap or
   the reason a stronger alternative took the space. Preserve all row IDs.

| Reviewed fit | Required basis |
| --- | --- |
| `directly-demonstrated` | Eligible project proof of the exact required mechanism, context and scope |
| `broader-professional` | Confirmed professional declaration at the required level, or directly relevant confirmed responsibility |
| `practical` | Confirmed hands-on practice outside employment |
| `working-knowledge` | Confirmed ability to explain or use the skill at the declared level |
| `familiarity` | Confirmed familiarity sufficient for the explicit expectation |
| `transferable` | Supported adjacent work and a specific transfer rationale |
| `partial` | Relevant evidence and a stated difference in proficiency, environment, scale, responsibility or scope |
| `needs-confirmation` | Unresolved or insufficient evidence, with a compact reason |
| `skill-gap` | Confirmed absence recorded as a learning target with `gap_confirmed: true` |
| `formal-eligibility-met` or `formal-eligibility-gap` | A screening finding with exact posting excerpt, matching `qualification_fit` and confirmed profile basis IDs |

Use dispositions `included`, `omitted`, `unresolved` and `gap`. A partial
match can be included when its narrower scope earns space. A requirement
waiting for a decision uses `unresolved`. Confirmed gaps use `gap`.
For time bars, cite the confirmed employment entries that count toward the
requirement and explain the context that makes them count. Recheck those facts
and the finding together when anything changes.

Record `discovery: {question, reason}` when a specific answer could change
the reviewed fit or preparation. Use `discovery: {reason}` when prior evidence
or the posting makes further questioning unnecessary. The editorial packet
carries these questions even when the related work stays off the page.

Record `project_review` keyed by project for each selected project and the
credible alternatives. Each entry has `disposition` (`selected`, `reserve`
or `omitted`), `refs`, `requirement_ids` and a concrete `reason` comparing
scope, contribution and marginal value. Treat general rank as a tiebreaker.
Make the judgment before drafting so the coverage and interview packet show
the same decisions.

## Set the claim plan

Use `claim_plan` to map each summary sentence, experience bullet, project
detail and skills item to its intended model path. Each entry carries
`refs` in citation order and `scope` describing the factual commitment and
any material limit. For example:

```yaml
claim_plan:
  'resume.experience[1].bullets[0]':
    refs: [sample-004]
    scope: Contributed acknowledged writes for negotiated-MTU Bluetooth LE chunks. Controller ownership stayed shared.
```

Every included technical, engineering, professional or domain requirement
names its planned `claim_paths`. Qualifications can be handled privately.
Copy the output of `ekb requirement-map ID --alignment` into the résumé
model. The alignment exists for layout. The map supplies the reviewed
classification to coverage and the editorial packet.

When rerendering, keep the plan, map and decisions. Rewrite sentences as
needed while retaining the same facts, scope and placement. Change a material
choice through a review of the map and refresh affected claim assessments.
If the intake, confirmed profile, curated corpus, screening or relevant
policy changes, obtain a new skeleton and reassess the previous map before
using it again. A new hash by itself does not perform that assessment.

## Verify the human receipt

Review the exact generated `editorial.json` and primary PDF using
[the editorial procedure](resume-editorial.md). Keep the human-authored JSON
receipt outside the bundle. It contains these fields:

- `application_id`, `generation`, `posting_sha256`, `primary_pdf`,
  `pdf_sha256` from the editorial packet.
- `validation_sha256` and `editorial_sha256` from the exact files.
- `requirement_map_sha256` from `requirement_map.revision_sha256`, or JSON null
  for an untargeted master or verified historical replay.
- `reviewer`, `reviewed_at` in ISO date form, and affirmative booleans
  `material_claims_approved`, `exact_pdf_inspected` and `gaps_reviewed`.
  Record the reviewer's handling of any material gaps alongside the receipt.

Run `ekb verify-review ID --approval RECEIPT.json`. The tool verifies current
screening, sources, generation and bundle bytes. It performs no delivery.

For legacy replay, work in a disposable copy. Use `--legacy-replay` only with a
verified exact posting and its recorded proceed decision. If the pairing cannot
be established, obtain a current screening decision. Version 2 intakes always
use the map. Leave historical snapshots intact.
