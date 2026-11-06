# Whole-candidate discovery

For a targeted opportunity, start only after the explicit, current screening
decision. Use the whole frozen posting. This is a private research and
selection pass. Only the profile procedure records user declarations.

## Map the posting

Record each meaningful requirement in `targeting.requirements`. Separate
technical skills, engineering practices, professional capabilities, domain
knowledge and formal qualifications. Keep mandatory and preferred items
distinct. Capture the short verbatim `posting_excerpt`, `why_it_matters`, and
aliases used in the candidate evidence. Distinguish production use, working
knowledge and familiarity when the employer does, using
`minimum_proficiency` when the posting states a level. Keep alternatives in the
posting visible. A requirement with “Python or Ruby” needs one supported option.

Put minimum tenure, degrees, work authorization, location and other formal
criteria in `category: qualification` when they are screening conditions.
Compare against the frozen screening findings and current confirmed profile
facts. Record `assessment.status` as `qualification supported` or
`formal eligibility gap` and `assessment.basis` as the precise posting bar
and candidate fact or screening locator. Leave it open when the fact is
unresolved. A good skills match never compensates for a failed formal check.

## Find the strongest match

Run `ekb shortlist ID --stdout` for a first pass. Read each `mapping` alongside
the ranked project and profile candidates. It lists direct, related and
transferable leads with sources and suggested placement. Verify each lead's
actual semantics, level, participation, context and limits. A broad alias or
related engineering example needs the full source read before selection.

Search the profile, employment responsibilities, legacy skills and confirmed
capabilities. Review existing answers in profile and project context,
interview guides, previous analyses and relevant résumé drafts. Treat derived
materials as pointers. Trace wording back to an actual confirmation or
eligible curated record. Keep contradictory, approximate and uncertain
answers visible. An interview guide can suggest questions or examples.

Compare different ways to make the match. For problem-solving, look for a
failure investigated, the diagnostic step or trade-off, and what changed.
For transferable work, state the observed mechanism and explain the
connection privately. For professional use outside curated projects, check
the employer context and scope. For learning or practice, identify what the
candidate could write, debug or explain today. Confirmed familiarity can be
useful with its level clear. A learning goal never supplies current knowledge.

An empty retrieval result means the match remains unresolved. Record
`assessment.status: genuine gap` with its basis only after discovery establishes
the gap. A confirmed learning target already answers the question at the recorded
scope. For every important requirement record selected refs and a `reason`
that explains why the match fits, the scope it supports, what would go on the
page, and any unresolved clarification. Include the qualification disposition
in the private review. Use `--stdout` to inspect fresh retrieval leads and
reassess the separate reviewed requirement map when its inputs change.

## Ask the fewest useful questions

Reuse answers that cover the same capability and level. If an earlier answer
was uncertain, preserve it and revisit only when a narrower question would
change a material decision. For an important unresolved match, batch related
questions. Give the strongest plausible interpretation and ask about the
specific distinction that matters, such as practical use versus reading,
what the candidate can do without help, or production versus prototype.
Treat silence and uncertainty as unresolved. Use the profile procedure for
explicit confirmations. Then rebuild the shortlist before selecting wording.
