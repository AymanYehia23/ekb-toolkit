# Resume presentation and layout

How a generated resume **looks**. `prompts/resume.md` decides which evidence the
document uses; this file decides how that evidence is rendered, linked,
emphasized, worded, and laid out.

The split exists because the two concerns compete for attention. Selection is
the judgement that decides whether a resume reads at the level of its evidence,
and it loses space to formatting rules inside a single long procedure.

Read this file at two moments: when writing `resume.json`, and when rendering.

**Nothing here may change what the resume claims.** Every rule below governs the
presentation of prose that selection has already chosen.

---

## 1. Hyperlinks are automatic

Entity labels and contact/profile values may carry a `url`, which renders as a
clickable hyperlink in both DOCX and PDF while the visible text stays whatever
`text` says. A `url` is presentation, not a claim, so it needs no source of its
own.

Narrative prose must never become one large hyperlink. When a bullet or detail
names a linked project, add `link_text` with the exact project-name substring;
the renderer links only that substring. If the prose does not name the project,
omit `url`. The validator rejects a narrative `url` without `link_text`.

Summary prose never carries hyperlinks. Do not attach `url` or `link_text` to a
summary item, even when its source belongs to a project with a confirmed link.

It is also never an invention. `profile/profile.yaml` is the only link registry,
and the source checker rejects any address absent from it or whose entry is not
`link_status: confirmed`.

**Linking is the default, not an option.** Before rendering, walk every entity
the document names and attach the registered address:

- employer and client names → `organization_links`, keyed by exact name;
- project names, including engagement names inside a role → `project_links`,
  one destination per project: the store listing for a shipped app, the
  repository when there is no listing, the documentation or portfolio page when
  that is the better public destination;
- certifications → the `url` on each certification entry;
- contact and profile links → as below.

Leave an entity unlinked only when the registry has no confirmed address. The
validation report warns about each unlinked employer, engagement, project, and
certification, so a missing address surfaces instead of being forgotten.

**Never guess a URL, never construct one from a company name, and never carry a
link over from an old document.**

Follow `preferences.link_style`. The governing rule: every hyperlinked contact
or profile address is hidden behind the human-readable `label` recorded in the
profile. The address remains available as the hyperlink target without adding
visual noise to the header.

- `contact` — a linked email uses the recorded `Email` label. A phone number is
  never linked and always renders as its literal value. Other non-hyperlinked
  values such as location may also remain literal text.
- `profile_links` — use the recorded service or purpose label, such as
  `LinkedIn`, `GitHub`, or `Portfolio`. Never expose the raw address as visible
  text.
- `project_links`, `organization_links`, `certification_links` — a hyperlink
  behind the name is correct. The name carries the meaning on its own, so
  nothing is lost if the annotation is dropped. Never link an entry that is
  `uncurated` or `unconfirmed`.

The renderer makes every live hyperlink visibly recognizable in both formats
using `config/resume-policy.json`: blue text and a single underline. It does not
rely on an application's default hyperlink style, because viewers differ.

Set `layout.hyperlinks` to `off`, or render with `--ats-plain`, only when the
user asks for an export with no annotations at all.

Plain-text exports keep these same labels and omit hyperlink targets because
TXT has no annotation layer. Use DOCX or PDF when the links must remain live.

## 2. Keyword highlighting

Bolding is a render-time pass over prose that already exists. It never changes
wording, never changes selection, and never inserts a term to be bolded. Write
the resume first, then let the renderer highlight it.

The renderer derives highlighted terms from `alignment.requirements`: a term is
bolded only when its requirement is `matched`, which the source checker already
gates on the alias appearing naturally AND on selected eligible evidence. There
is no separate keyword list and no way to bold something the resume cannot
support.

Two controls shape the result:

- set `emphasize: false` on a matched requirement whose emphasis adds noise
  rather than guidance: broad behavioural terms, and anything already carried by
  a section heading;
- write aliases as the noun phrases a recruiter scans for. Aliases are what get
  bolded, so a verb alias produces a bolded verb at the start of a bullet, which
  reads like emphasis on the wrong word.

The render policy also excludes generic product and UI nouns such as `app`,
`mobile`, `screen`, and `widget`. They may remain aliases for retrieval and
coverage, but bolding them adds no meaning and makes ordinary prose look noisy.
Use a more specific phrase such as `Clean Architecture`, `Riverpod`, `REST API`,
or a named integration when emphasis is useful.

The policy bolds each term at most once per section and caps highlighted
requirements at twelve, choosing required-and-critical first. Overflow is
reported, never silently dropped, and never blocks rendering. Past about a dozen
terms nothing stands out. Set `layout.emphasis` to `none` for no bolding.

## 3. The direct-language gate

Every generated resume must avoid generic filler wording and decorative
punctuation. This is a deterministic constraint, not an editorial suggestion:

- never use an em dash, en dash, right arrow, or double right arrow in visible
  text. Use a full stop, colon, comma, parentheses, or an ASCII hyphen;
- never use a term or phrase listed under `writing_style.forbidden_terms` or
  `writing_style.forbidden_phrases` in `config/resume-policy.json`;
- replace a banned term with the concrete feature, action, constraint, or
  verified result. **Do not swap it for another generic adjective**;
- the rule applies to every visible section. Hyperlink targets and private
  alignment notes are not public prose.

The renderer rejects a model that violates this gate. Keep the policy list
small, explicit, and version-controlled so the preference stays auditable — and
edit it. The shipped list is a sensible default, not a doctrine.

Writing should be concise and sound like an experienced engineer:

- prefer specific feature behavior, architecture, integrations, and constraints;
- use target terminology only when it truthfully matches stored experience;
- vary sentence structure naturally;
- omit filler, generic claims, and unsupported adjectives;
- use neutral technical results when no measured business result exists.

## 4. Length and structure budgets

**Summary.** Four to six complete sentences with a 90-word ceiling in every
market. Cover the supported professional identity, relevant experience and
expertise, career direction, and work-authorization context only when applicable
and confirmed. Relocation belongs in the dedicated header line below, so do not
repeat it in the summary. Never pad a sentence or invent context to reach four.
Set `layout.summary_word_limit` between 40 and 120 for a one-document
override without changing market or page size; the four-to-six-sentence rule
still applies. What the summary should SAY is in `prompts/resume.md`.

**Bullets.** Roles stay reverse chronological. For a flat role: three bullets
for current or highly relevant roles, one or two for older roles, four as the
hard maximum. Each achievement bullet is one sentence, ends with terminal
punctuation, and stays within `config/resume-policy.json`
`bullet_quality.maximum_words`. Do not preserve an overlong sentence by
shrinking the font or margins; select one idea and rewrite it at the right
altitude.

**Header.** Keep the confirmed name, professional personal email, phone number,
readable professional-profile address, and location together at the top. On its
own centered line immediately below the contact row, render `basics.mobility`
for every master resume and every job whose `target.location_scope` is
`outside-country`. Use a concise phrasing from the profile relocation entry,
such as `Open to relocation.` Prefer a confirmed destination-specific phrasing
when available; never create one by copying the job country into the claim.
This line is plain text, not a hyperlink, and is not repeated in the summary or
continuation-page header. A missing confirmed relocation phrasing blocks these
resumes rather than being invented. Add work authorization only when it is
relevant to the target and explicitly recorded. Never substitute a previous
employer's email address. Missing contact categories are validation warnings
because the renderer cannot invent them.

**Languages.** Prefer CEFR levels (A1-C2) for European applications when the
profile records one. Never translate “fluent”, “professional working”, or
another user-stated label into CEFR without confirmation. The validation report
flags the missing mapping; it does not manufacture it. Do not use bars, stars,
or charts for proficiency.

**Engagements.** When a role uses `experience[].engagements`: one or two
role-level framing lines, two to four engagements, one or two bullets each.
`experience_budget` in the policy holds these numbers and the renderer reports
overruns as warnings rather than truncating.

**Bullet geometry** comes from the policy and must be identical in DOCX and PDF.
Bullet text starts inside the company or project title margin, wrapped lines
align under the first text line, and the marker is vertically offset to the
body-text baseline. An engagement title aligns with the role bullet text and its
own bullets sit one level deeper, giving three visible depths: employer, named
project, achievement. Do not rely on a viewer's default list indentation.

**Page size and count.** A4 for Europe, Letter for North America. Honor
`profile.preferences.page_target`; the source validator rejects a model that
silently changes it. Default that profile preference to one page through five
confirmed years of experience. For a longer career, use a second page only when
relevant evidence needs it and the preference records that choice. Compact once
when the document overflows, and reject anything longer than two. The
first page must contain contact information in the body; a later page may repeat
only the exact name and contact line in its header. A two-page resume may set
`layout.page_break_before` when visual review shows a deliberate break produces
a materially better-balanced layout.

## 5. Render

```bash
scripts/ekb render <application-id>
```

That resolves the model, profile, projects, and policy from the workspace. Add
`--include-text` for a TXT export, which prints each hyperlink target in
parentheses because plain text has no annotation layer. Add `--ats-plain` for a
copy with no hyperlinks and no bold: the same words with the presentation layer
removed.

The tool must pass source eligibility checks before writing any public
document, then verify DOCX and PDF text extraction and write `validation.json`
plus `validation.md`.

The output directory keeps stable `resume.docx` and `resume.pdf` names for
tooling and also contains attachment-ready copies named
`FirstName_LastName_TargetRole_CV.docx` and `.pdf`. Submit the PDF copy. The
renderer rejects password-protected PDFs.

If `ekb render` reports missing dependencies, run `scripts/ekb doctor`.

## 6. Read the report, then look at the pages

Treat these warnings as work, not noise: unlinked entities that have a confirmed
address, a rank inversion with no stated reason, capped emphasis terms, a
heavily bolded document, and a stale evidence index.

The report carries a **requirement coverage** table showing each requirement's
coverage grade, the strongest record left unused, and any recorded reason. A row
reading `stated` with a strong record in the unused column is the shape of a
resume that will review below its evidence, even when every other check passes.
That is a selection decision: go back to `prompts/resume.md`.

**Render every page to an image and look at it.** Fix clipping, overflow,
awkward page breaks, broken bullets, and inconsistent spacing before delivery.
Do not deliver on a failed validation.

After the first render, inspect page count and page use. A single-page resume
below `content_density.single_page_minimum_usable_height_ratio` is underfilled
even with no clipping. Resolve empty space in this order:

1. add target-relevant technical depth to the existing Selected Projects;
2. add another distinct curated project when it contributes non-redundant
   evidence;
3. restore a stronger relevant Experience detail omitted for space;
4. include another confirmed section only when it helps the target.

**Do not fill a page** with a longer generic summary, repeated claims, broad
skills, weak certifications, or gameable counts. Re-render and inspect after
each meaningful revision. If the eligible evidence genuinely cannot support more
target-relevant content, say so plainly rather than padding.

When a one-page draft overflows, cut in this order: lower-value skills, then
certifications, then older experience, then a Selected Projects detail. Remove a
required project or a target-critical achievement last, and re-run the coverage
audit after every layout-driven cut.
