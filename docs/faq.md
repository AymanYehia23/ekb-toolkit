# FAQ

The README carries the common questions. These are the ones that come up once
someone has used the toolkit for a week.

---

**The agent proposed context that is wrong. What happens if I just approve it?**

It becomes `user-stated` and gets treated as fact from then on. Correct it
during review instead — the correction is preserved verbatim in the context
file, and the superseded inference is removed. Correcting costs one line and is
the single highest-value thing you do in a review pass.

**A record is wrong and it is already curated. Can I edit the file?**

Run a review session and record the edit as a decision, so the change is
preserved with its reason. Curated files are append-only with your decisions;
a silent hand edit leaves a record whose history says it was never questioned.

**Why did an analyze run produce nothing?**

Usually because the range genuinely contains dependency bumps and copy changes.
That is a normal outcome and it still advances the baseline, so the same history
is not re-scanned. If you believe there was real work in the range, run with
`DEPTH=deep`.

**Two projects share the same underlying work. How do I stop it being counted
twice?**

A `counting-rule` constraint in the professional profile, plus `never_with` on
both ranking entries. This is exactly the case that is invisible inside either
project file and needs a cross-project rule.

**My best work is under NDA. Can I use it?**

You can record the engineering without naming the client: the architecture, the
constraint, the decision. Add the repository to `EXCLUSIONS.md` for anything
sensitive, and leave the organization out of `organization_links` so it is never
hyperlinked. Whether the code may be sent to your agent's provider at all is a
separate decision, and it is yours.

**Why does the resume refuse to render?**

Read the errors in the validation report. The common ones are: a visible fact
with no source reference, wording stronger than the record's involvement
supports, a number no cited source carries, a URL not in the registry, and a
required requirement with no recorded selection decision. Each of them is the
checker doing its job.

**The selection score is low but the resume looks fine.**

Read the dimensions rather than the total. A high `required_demonstrated` beside
a low `strongest_evidence_used` means coverage is complete while requirements
are being answered by second-best records. Go back to the shortlist and check
what outranked strength in each case.

**The checker keeps warning about the same commodity skill on every
application.**

That is the understatement gate firing where it should not. Identical
`selection_reason` boilerplate appearing on the same requirement across
applications is the signature. Read the warning and move on; it only errors on
`critical` requirements for exactly this reason.

**Can I generate a cover letter?**

Yes. After every successfully delivered job-targeted resume, the agent asks if
you want one. A yes runs `prompts/cover-letter.md` against the same frozen
application, screening decision, shortlist, and validated resume. It writes a
full three-paragraph letter to `artifacts/applications/<id>/cover-letter.md`.

For an opening paragraph without a complete application, use
`prompts/summary.md` with `VENUE=cover-letter` instead.

**Can I run this without an AI agent?**

The deterministic half, yes: index, shortlist, check, skills, validate, render,
checkpoint. Analysis, review, and drafting are judgement work and need an agent.

**How much does a full application cost in tokens?**

The screening gate reads three files. A resume run reads the profile, the
ranking, the index, and the curated records the index points at — not the whole
knowledge base. That is the entire reason the retrieval layer exists.

**Is my knowledge base portable between agents?**

Yes. It is YAML and Markdown with no vendor-specific structure. `AGENTS.md` is
the shared contract, and `CLAUDE.md` and `GEMINI.md` are one-line pointers to
it.

**Why is there no web UI?**

Because local files you own is the design, and a UI is the shortest path to a
hosted version. A read-only local viewer is on the roadmap; anything that stores
your career data somewhere else is not.
