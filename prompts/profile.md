# Profile — the confirmed facts every artifact reuses

Parameters, all optional:

- an existing resume, CV, or profile the user supplies;
- corrections or additions to an existing profile.

Follow `AGENTS.md`. This is a proposal-first workflow, not a form interview.
Run it once; later applications should need no repeated profile questions.

**Never infer an identity, contact, employment, timeline, education, or
certification fact from a repository.** Git configuration is not a source of
truth about a person, and a name in a commit is not a confirmed display name.

---

## 1. Load before asking

Read `profile/profile.yaml` when it exists. Read curated `projects/*.yaml` only
to discover project names and repository facts.

If the user supplied an old resume, extract a draft from it. Mark extracted
items `user-stated` only after the user confirms the compact preview. A
generated artifact or a third-party page is not confirmed profile truth.

## 2. Blocking information only

A complete resume needs:

- a display name;
- a stable professional identity for master-resume headers and summary openings;
- at least one contact method;
- employment entries with organization, title, start date, and end date or
  `present`;
- an association between each project that may appear and the employment it
  belongs to.

Location, links, education, certifications, languages, and summary preferences
are optional. A confirmed current country and relocation intent become blocking
only when generating a master resume or comparing the profile with a job in
another country. Do not ask for another optional section unless the user wants
it or a current application would materially benefit.

Warn without blocking about a timeline gap over three months or two overlapping
full-time roles. The user may have a good reason; the document should just not
present it by accident.

## 3. The link registry

`profile.yaml` is the only place a generated document may take a URL from, so
collecting links belongs here rather than in every application.

When the user names an employer, client, shipped app, repository, documentation
site, or portfolio page, ask once for its public address and record it under
`organization_links` or `project_links` with `link_status: confirmed`.

For every email or profile entry that carries a `url`, keep the literal address
in `value` and `url`, and set `label` to the short text a document will show.
Record an explicit `link_status` on each URL. For an older entry with missing
status, reconcile it against the original user confirmation and record the
status here before drafting. Use `unconfirmed` if the destination is unresolved.
Use `Email`, `LinkedIn`, `GitHub`, `Portfolio`, or the equivalent service name.
A custom `other` link needs a concise descriptive label. Never put an email
address, domain, or URL in a hyperlinked `label`.

Phone is the exception: it always renders as its literal `value`, its `label`
must match that value, and it never carries a `url`. When loading an older
profile whose other hyperlinked labels expose addresses, include their label
migration in the compact confirmation.

- `unconfirmed` — the user is unsure which project an address belongs to.
- `uncurated` — the app is real but has no curated project behind it.

Both are stored and neither is ever rendered. The status is what the source
checker reads; a caveat written only in prose would be lost.

Verify that an address resolves when you first record it and store the date as
`verified_at`. Verification belongs here, once, rather than in the renderer:
rendering must stay deterministic and offline.

**Never record a private or authenticated address.** A developer console URL
identifies the account, not the app, and does not belong in a document.

## 4. Work eligibility

Record these only if the user wants the screening gate to run, and record them
as facts rather than as preferences:

- `profile-eligibility-001` — citizenship or nationality.
- `profile-eligibility-002` — existing work authorization, and which markets
  normally sponsor.
- `profile-eligibility-003` — relocation intent and target markets.

Record the current country explicitly as `country` and its ISO 3166-1 alpha-2
`country_code` on the `contact` entry whose type is `location`. Never derive
current country from citizenship, and never derive citizenship from location.
The resume workflow uses these different facts for different decisions.

For relocation, preserve the user's exact intent and add one or more concise
confirmed `phrasings` suitable for a header, such as `Open to relocation.` or
`Open to relocation within the EU.` Record target countries or regions only
when the user explicitly confirms them. Never invent a destination, move date,
self-funded move, visa status, or sponsorship position. If the user is not open
to relocation, record that truth; do not substitute an affirmative phrase.

A master resume and an application whose confirmed job country differs from the
confirmed current country require a relocation header line. If no truthful,
confirmed relocation phrasing exists, stop and request confirmation instead of
generating the resume.

The screening policy compares against these by ID. A check whose basis cannot
be resolved reports that it could not run, which is why an absent fact is
better than a guessed one.

## 5. One compact confirmation

Present everything missing or extracted in one short batch, including the
proposed project-to-employment associations. Accept one confirmation with
corrections. Ask separately only when an ambiguity would put experience under
the wrong employer or make the document unusable.

Assign stable IDs that survive rewording:

```text
profile-identity-001      profile-title-001           profile-experience-NNN
profile-contact-NNN       profile-education-NNN       profile-award-NNN
profile-link-NNN          profile-certification-NNN   profile-eligibility-NNN
profile-skill-NNN         profile-responsibility-NNN
```

`organization_links` and `project_links` are keyed by name rather than by ID.
They are presentation data, not sources, and nothing cites them.

Write the result using `templates/profile.yaml`. Append material confirmations
or corrections to `profile/profile-context.md`, preserving existing entries.

### Job-matched headlines

For a job-targeted resume, prefer a concise headline matching the advertised
role and supported specialization. Record approved alternatives in
`professional_title.job_targeted_phrasings`, keeping `professional_title.value`
as the general identity. A targeted headline is presentation, not a new
employment title. It must not import an unsupported seniority, qualification,
leadership role or technology from the posting. Ask for one compact confirmation
when a useful variant is not recorded; reuse confirmed variants for later
relevant opportunities.

Record the preference as
`preferences.resume_defaults.job_targeted.headline: job-matched`. Master resumes
retain the general title, and summary openings may use that identity even when
the targeted header differs. Never rewrite employment titles to match a job.

## 6. Responsibilities: the work that leaves no Git trace

`responsibilities` is the only route by which client meetings, requirements
gathering, solution design, production support, mentoring, or a working method
can appear in a document. None of it is in a commit log.

Each entry carries `phrasings`, and text sourced to it may reuse only words
present in that entry. This is deliberate: it stops a responsibility from
quietly growing between applications. If a target role needs an angle the
phrasings do not cover, add the phrasing here first.

Each entry also carries a `cap`. A responsibility describes what the work
involved. It is never a commercial outcome, a title, or a productivity claim.

## 7. Privacy consent

Before the first checkpoint, explain plainly that **Git history preserves
deleted personal information**. A phone number committed once and removed later
is still in the repository.

Ask once whether the user permits:

1. committing profile files locally;
2. committing job descriptions and generated application history locally.

Store each answer explicitly as `granted` or `declined`. A missing answer
behaves as declined. Generation continues either way; only the checkpoint stops.

If profile consent is granted, run `scripts/ekb git profile`. Never push.

## Whole-candidate capability declarations

Use `profile.capabilities` for genuine knowledge and experience that merits
its own declaration alongside project records and legacy skills. Follow the
fields and example in `templates/profile.yaml` and
`config/capabilities.json`. Keep source type, context, proficiency and
interview readiness separate. Record a dated user confirmation and its
locator in `basis.detail`, and preserve the actual answer in
`profile/profile-context.md`. For professional use, capture where and how
the candidate used the capability. For study or independent practice,
capture what they can explain or do. Confidence and readiness are private.

A proposed capability can stay in the opportunity discovery notes or be
recorded as `inferred` with `confirmation_required: true`. Only the user's
explicit answer can make a declaration `user-stated` and clear that flag.
Keep aliases faithful to the same skill. Put adjacent technologies in
private transfer notes. Add concrete examples and limitations when known.
Use stable IDs. Revalidate drafts that cite a changed declaration.


Use `ekb candidate` to reconcile a proposed declaration with existing answers,
education, responsibilities, interview notes and curated proof. Legacy
`core / working / exposure` flags describe evidence inventory and must not be
converted into proficiency. Date confirmations at the time of the candidate's
actual confirmation. Keep prior declarations. For a confirmed progression or
correction, give the new declaration its own ID and list the earlier same-skill
IDs in `supersedes`. State why the scope or level changed in the basis.
A conflict remains unresolved until confirmed. Confirm an absence explicitly
before recording `gap_confirmed: true` on a learning target.
