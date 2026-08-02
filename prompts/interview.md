# Interview — stories you can actually defend

Parameters:

- `PROJECT` — one project.
- optional target role, topic, or job context to guide selection.

Follow `AGENTS.md`. This procedure is a **read-only consumer** of curated
knowledge. It writes only `artifacts/interview/<PROJECT>.md`, replacing the
previous version.

---

## Sources

- Facts come from `projects/<PROJECT>.yaml`. Never read candidate files and
  never read the target repository.
- Read `profile/professional-profile.yaml` for standing framing and limits. Its
  `constraints`, `counting_rules`, and `do_not_claim` entries bind this artifact
  in addition to each record's own limitations. It supplies no facts of its own.
- Consult `context/<PROJECT>-questions.md` only through stable locators already
  cited by a curated record.
- Rephrase and reorder freely. **Never strengthen** certainty, causality,
  achieved impact, involvement, or scope beyond the record.
- Keep source comments as `<!-- src: PROJECT-NNN -->` so output stays traceable
  without showing provenance labels in readable prose.

## Select before writing

Rank records internally by distinctiveness, technical substance, evidence
quality, usable involvement, and relevance to any supplied target. Do not expose
a numeric score. Prefer a small coherent selection over broad coverage.

Involvement governs what a story may claim:

- `contributed` — "worked on" or "contributed to", followed by an accurate
  description of the whole feature;
- `implemented` — direct implementation wording, without implying nobody else
  contributed;
- `led` — leadership wording inside the confirmed scope;
- `team-context` and `unknown` — usable for understanding the system, not as a
  personal accomplishment unless participation is otherwise supported.

Exact component-by-component attribution is not required. Never translate
ordinary contribution into "led", "owned end-to-end", or "built alone".

## The stories

Generate the three strongest by default. Fewer if fewer records are useful.
**Never pad the guide** — a fourth weak story makes the first three worse.

Each story carries:

- **Feature context** — what the complete feature or change did.
- **Likely motivation** — user-confirmed context when available, otherwise the
  best curated `inferred_context`, explicitly labelled `Provisional inference`.
- **Participation** — the supported involvement level, without artificial
  line-by-line attribution.
- **Decision and action** — the architecture, implementation, integration, or
  investigation, grounded in the record.
- **Result** — delivered technical behavior, or a real measured outcome. Do not
  demand a business metric and do not convert expected benefit into achieved
  impact.
- **Trade-offs and limits** — only material boundaries.
- **Evidence to re-read** — the commits, ranges, and files behind it, so the
  user can refresh the details the night before.
- **Likely follow-up questions** — the three an interviewer would actually ask.
  This is the part that turns a story into preparation.
- its source comment.

The follow-up questions are worth real effort. A story that survives its own
telling and collapses on the first "why not the other approach?" has not helped
anyone.

## Supporting fact bank

After the stories, add a compact fact bank from other useful curated records.
Keep these to short facts, not additional stories. It exists so a question about
an unexpected corner of the project has something behind it.

## Provisional points

End with `Provisional points to confirm` **only** when selected material still
contains inferred context. Present your best guess and what would settle it, not
a blank questionnaire.

## Verify and finalize

Map every source comment to a real curated record. Compare every sentence
against its statement, kind, evidence, reasoning, limitations, involvement,
confirmed notes, and any provisional inference. Confirm that every hypothesis is
visibly labelled as one.

Report the output path and the selected record IDs. Checkpoint with
`scripts/ekb git artifact <PROJECT> interview`.

Offer a deeper story or a bullet bank if either would help, and stop.
