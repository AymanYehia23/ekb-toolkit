# The workflow, end to end

A worked path from an empty clone to a rendered resume. Every command here runs
against the shipped example, so you can follow it before touching your own data.

---

## Day one: set up

```bash
git clone <repo> && cd ekb-toolkit
pip install -r requirements.txt
scripts/ekb doctor
scripts/ekb init
cd workspace && git init && cd ..
```

Then, in your agent:

```text
Follow prompts/profile.md
```

Twenty minutes. You will be asked for a name, professional title, one contact method, your
employment timeline, and which projects belong to which employer. Everything
else is optional.

Two things are worth doing properly here rather than later:

**Links.** Every URL a document can ever render must be recorded now, with
`link_status: confirmed`. This is the only registry.

**Responsibilities.** The work that leaves no Git trace only exists if you write
it here. Client meetings, requirements gathering, production support, mentoring.

## Day one: your strongest project

```text
Follow prompts/analyze.md with REPO_PATH=/absolute/path/to/repo PROJECT=myapp
```

Ten minutes of agent work, read-only against your repository. You get three to
seven candidate records.

```text
Follow prompts/review.md with PROJECT=myapp
```

Ten minutes of your attention. One batch. Read the statements, confirm the
context proposals, correct what is wrong, drop what is weak.

Be willing to drop things. "Migrated to null safety" is real and routine and
would not survive a follow-up question.

```text
Follow prompts/interview.md with PROJECT=myapp
```

You now have something useful even if you never apply anywhere: three stories
with the evidence to re-read and the questions you will actually be asked.

## Day two: two more projects

Same loop. Then:

```text
Follow prompts/professional-profile.md
Follow prompts/rank.md
```

These need at least two or three projects to say anything. The professional
profile finds what recurs; the ranking orders everything by value rather than by
recency.

Write the standing constraints carefully. A counting rule saying a reused
component is one piece of work, not one per app, is invisible inside any single
project file and binds every document you generate afterwards.

## Ongoing: after each piece of work

```text
Follow prompts/analyze.md with PROJECT=myapp
```

No path needed. It resumes from the HEAD it last reached. Usually zero to three
new records; often zero, and that is a normal outcome that still advances the
baseline.

```text
Follow prompts/review.md with PROJECT=myapp
Follow prompts/bullets.md with PROJECT=myapp
```

Then rebuild what depends on records:

```bash
scripts/ekb index
scripts/ekb check
```

## Applying: the screening gate

```text
Follow prompts/screen.md with JOB_DESCRIPTION=<paste>
```

Under 300 words, then it stops. Read the blockers, the positive signals, and
what the posting does not say. Answer `proceed`, `declined`, or `deferred`.

A declined screening is a completed run. The record stays, and the same posting
is never screened twice.

## Applying: the resume

```text
Follow prompts/resume.md with JOB_DESCRIPTION=<paste>
```

The gate runs first. After `proceed`, the interesting part is the shortlist:

```bash
scripts/ekb shortlist 2026-03-14-northwind-flutter-engineer
```

Open `applications/<id>.evidence.yaml` and read it yourself. For each
requirement it lists the eligible candidates with their strength and signals.
The agent fills in `selected` and `reason`; you can see whether it chose well.

This file is where resume quality comes from. A `required` requirement answered
by a skills line while a `before-after` record sits unused is obvious on paper
and invisible in a finished document.

Then:

```bash
scripts/ekb render 2026-03-14-northwind-flutter-engineer
```

Read `validation.md`. Look at the rendered pages. Fix what the report flags, and
treat a `stated` required requirement with a strong unused record as a selection
problem rather than a layout one.

```bash
scripts/ekb render 2026-03-14-northwind-flutter-engineer --ats-plain
```

Same words, no hyperlinks, no bold, for a submission portal that mangles
formatting.

After a job-targeted resume is delivered, the agent asks whether you want a
cover letter. Answer `yes` to run `prompts/cover-letter.md` against the same
application. It reuses the frozen posting, screening decision, shortlist, and
validated resume, then writes:

```
artifacts/applications/2026-03-14-northwind-flutter-engineer/cover-letter.md
```

The letter follows three paragraphs: motivation and hook, value fit and proof,
then call to action and closing. It does not rerun screening or invent a company
motivation you have not stated.

## Every few months

```bash
scripts/ekb skills          # has your skills list drifted from your evidence?
scripts/ekb check           # cross-file consistency
```

```text
Follow prompts/professional-profile.md
Follow prompts/rank.md
```

Both re-derive from everything you have accumulated since. A strength that was
`supporting` two projects ago may now be `core`.

## Following along with the example

Every step above can be run against the shipped fictional workspace:

```bash
export EKB_WORKSPACE=$PWD/examples/sample-workspace
scripts/ekb status
scripts/ekb index
scripts/ekb check
scripts/ekb shortlist 2026-03-14-northwind-flutter-engineer --refresh
scripts/ekb validate 2026-03-14-northwind-flutter-engineer
```

Read these three files in this order and the design will make sense:

1. `projects/fittrack.yaml` — what a curated record looks like
2. `context/fittrack-questions.md` — the conversation that produced it,
   including the candidate that was dropped and why
3. `applications/2026-03-14-northwind-flutter-engineer.evidence.yaml` — the
   selection decisions, written down
