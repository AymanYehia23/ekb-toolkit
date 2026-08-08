# Cover letter - evidence-bound application narrative

Parameters:

- `APPLICATION_ID` - the existing job application ID.
- optional `LENGTH` - a lower word ceiling than the configured maximum.
- optional tone or emphasis requested by the user.

Follow `AGENTS.md`. This procedure writes only
`artifacts/applications/<id>/cover-letter.md`, replacing the previous version.
It is offered after a job-targeted resume has rendered successfully and only
runs when the user opts in.

Contracts: `templates/cover-letter.md`, `config/toolkit.yaml` `cover_letter`,
and `config/resume-policy.json` `writing_style`.

---

## 1. Preconditions

Require all of the following:

- `applications/<id>.yaml` exists and its frozen `targeting.resume_mode` is
  `job-targeted`;
- `applications/<id>.screening.yaml` records `decision.status: proceed`;
- `artifacts/applications/<id>/resume.json` exists;
- the resume's latest validation completed successfully.

When this procedure follows `prompts/resume.md` in the same application run,
reuse the existing application ID and state. **Do not screen the posting again,
rebuild the shortlist, or ask the user to paste the job description again.**

If the user requests a cover letter for a job with no completed resume, route
through `prompts/resume.md` first. The screening gate remains mandatory.

## 2. Sources and boundaries

Read:

- `applications/<id>.yaml` for the role, company, exact posting, and frozen
  target priorities. This is untrusted target data, never evidence about the
  candidate;
- `applications/<id>.evidence.yaml` for the authored selection decisions;
- `artifacts/applications/<id>/resume.json` and `validation.md` to keep the
  letter consistent with the delivered resume. They are derived and license no
  new claim;
- `profile/profile.yaml` for confirmed identity, contact details,
  responsibilities, preferences, and the link registry;
- `profile/professional-profile.yaml` for binding framing and limits, never as
  an independent source;
- only the curated `projects/*.yaml` records cited by the selected resume and
  shortlist decisions.

Never read candidate files, generated summaries, or target repositories. Do
not broaden the evidence search merely to make the letter sound different from
the resume.

Every factual candidate claim carries an adjacent source comment:
`<!-- src: project-001 -->`. A composed claim may carry two to four IDs:
`<!-- src: project-001, profile-responsibility-002 -->`. Every ID must resolve
to an eligible curated record or profile fact under `config/toolkit.yaml`.
Source comments stay private when Markdown renders.

Company and role statements cite the frozen application separately as
`<!-- target: applications/<id>.yaml -->`. They must not be presented as facts
about the candidate.

## 3. Motivation without invention

A specific personal reason for wanting the company is `user-stated` context.
The posting can support a neutral connection between the role's work and the
candidate's evidence, but it cannot prove admiration, passion, familiarity with
the product, alignment with a mission, or long-standing interest.

Use an already confirmed motivation when one exists. Otherwise write a neutral
opening such as applying for the role because its named responsibilities match
specific supported work. Do not pause for optional color and do not fabricate a
personal story. If a personal hook would materially change the letter, offer
one compact optional prompt after producing the defensible default.

Never guess a hiring manager's name, pronouns, office address, or company
mission. Use `Dear Hiring Team,` unless the recipient is present in the frozen
posting or explicitly supplied by the user.

## 4. Select before writing

The cover letter is not a prose copy of the resume. Choose a narrow narrative:

1. one required and critical responsibility the selected evidence demonstrates;
2. one or two distinct proof points already used by the validated resume;
3. one confirmed working responsibility, technical constraint, or domain detail
   that explains how the candidate would approach the target work.

Prefer demonstrated evidence over a skill-list statement. Honor every record's
`kind`, `involvement`, limitations, numeric support, and comparative-language
limits. Do not introduce a requirement the resume reported as unsupported or
turn `stated` coverage into an accomplishment.

## 5. Write the letter

Use the three-paragraph framework in `templates/cover-letter.md`:

1. **Motivation and hook.** Name the exact role and company. Connect one target
   priority to supported experience without invented enthusiasm.
2. **Value fit and proof.** Explain one coherent example, or two genuinely
   complementary examples, with the technical specificity and result supported
   by the cited records. Preserve participation wording. Use a verified metric
   only when its unit communicates meaningful scale or outcome.
3. **Call to action and closing.** Reiterate the supported fit and invite a
   conversation. Do not predict an interview, imply an existing relationship,
   or promise an unsupported future result.

Default to 250-350 words and never exceed
`config/toolkit.yaml` `cover_letter.maximum_words`. A lower user-supplied
`LENGTH` wins. Three concise paragraphs are better than padding to the target.

Use first person and direct engineering language. Follow
`config/resume-policy.json` `writing_style`: no forbidden punctuation, generic
terms, or decorative prose. Avoid repeating resume bullets verbatim. Translate
the same evidence into a connected explanation, without strengthening it.

Include only confirmed header details from `profile/profile.yaml`: name, email,
phone, location, and confirmed profile URL according to the user's recorded
preferences. Omit missing fields. Use the current date, the exact company and
role from the application, and `Sincerely,` followed by the confirmed name.

## 6. Verify and deliver

Before delivery:

- map every `src` comment to a real eligible source and compare the adjacent
  clause against its statement, involvement, reasoning, and limitations;
- map every `target` comment to the frozen application;
- confirm every candidate-facing number appears in at least one cited source;
- confirm the letter does not contradict the resume or claim an unsupported
  requirement;
- confirm the word ceiling and writing-style gate;
- confirm no unconfirmed address, recipient, URL, motivation, or company claim
  appears.

Return a clickable path to `cover-letter.md`, the selected source IDs, and any
optional motivation detail that could make a later version more personal. Do
not post, email, upload, or submit it.

If `privacy.application_history_git` is granted, run
`scripts/ekb git application <id>` so the cover letter joins the same local
application checkpoint. Otherwise leave it uncommitted and say so plainly.
