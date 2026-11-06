# Editorial review and delivery

Follow `AGENTS.md`, the screening gate in `prompts/screen.md`, and the
selection and presentation procedures. Keep this work private.

## Prepare the review

Run `ekb validate ID --draft DRAFT.json --editorial-packet` after screening.
Read the claim manifest with the cited curated records, exact source
excerpts, provenance, involvement, evidence locations and limitations. The
packet's source excerpts are limited to cited records. Look up unused candidates separately
when deciding whether the current bullet deserves its space. Check the
frozen posting and alignment for qualification gaps.

For each material accomplishment, answer these questions.

1. What is the strongest claim this evidence supports?
2. What did the candidate personally contribute?
3. What did the team or other contributors do?
4. Which engineering decision, constraint, or complexity makes the work substantial?
5. What outcome is directly supported, and in what environment?
6. What precise qualification would keep a valuable accomplishment usable?
7. Why does it matter for this role?
8. Which equally accurate formulation would make it more compelling?
9. What does it add beyond the other bullets?
10. What would an interviewer reasonably ask about the decision, trade-offs, or results?

## Record material findings

Classify each finding as an **evidence defect**, **unsupported claim**,
**ambiguous contribution**, **wording problem**, **editorial opportunity**,
**target-role mismatch**, or **qualification gap**. Use more than one label
where useful. Keep machine errors and human editorial findings identifiable.

Give the reviewer the original wording and model path, the exact supporting
excerpt and stable source IDs, the individual and team contributions, and
any limitation or uncertainty. Recommend the strongest supportable wording
and explain what it gains in precision, relevance, or engineering detail.
State whether human confirmation is needed and which fact it would resolve.
When two readings are defensible, retain both formulations and explain what
each asserts or leaves open. Resolve evidence defects in the owning procedure.
Try narrower or more concrete wording before recommending omission.

Record the agreed wording and clause-specific basis in the model as specified
in `prompts/resume.md`. Ask for human confirmation only when needed for a
material fact or the final editorial decision. A current fingerprint shows
that the review describes the current statement and sources. The human
reviewer judges the interpretation and strength of the writing.

## Approve the delivery copy

1. Check that the intended employer, role, application ID, and frozen posting
   match the reviewed draft and screening decision. Make any material
   qualification gap explicit in the private decision.
2. Render the private PDF and inspect every page and the extracted text.
   Resolve technical or visual defects and repeat review for changed claims.
3. Have the reviewer record approval using the
   [exact PDF receipt](application-decisions.md#verify-the-human-receipt).
   Confirm the receipt with `ekb verify-review`. A new generation needs its
   own inspection and approval.

## Whole-candidate review

Read `requirement_map` and `requirement_coverage` from the same generated
packet. If their basis is stale, reopen the application decision before drafting. For each important
requirement, record its exact posting wording and priority, the selected basis
and level, whether the match is direct or partial, the proposed public
wording, and any confirmation still needed. Keep qualification decisions
explicit. The packet separates project evidence, employment and other profile
facts, and capability declarations. A declaration carries its original basis
and limits, including study, independent practice, employment or uncertainty.

Use `capability_interview` for questions and answer material tied to the
exact skill wording and source. Check the complete résumé aloud for generic phrases, repetitive structures,
and copied or repeated terms. Keep the candidate's actual technical choices,
diagnostic steps and collaboration visible. Compare the selected skills and
claims with the application interview guide. Note any skill that needs
preparation or clarification before the interview. Review exact claim wording
and proficiency headings and record the human delivery decision as above.
