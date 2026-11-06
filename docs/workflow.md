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
scripts/ekb bullet-audit   # after a full bullet-bank quality pass
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

The gate runs first. After `proceed`, confirm the active candidate view and
compare live evidence for the complete posting.

```bash
scripts/ekb candidate
scripts/ekb shortlist ID --stdout
scripts/ekb requirement-map ID --skeleton
```

The shortlist contains retrieval leads. Follow the [application decision
procedure](../prompts/application-decisions.md) to record every reviewed
fit, placement, source and material gap in `applications/ID.requirements.yaml`.
Draft from that file and use `ekb requirement-map ID --alignment` for the
model's layout projection. The model, validation report and private packet
identify the same map revision. Changing the profile, frozen requirements or
curated records makes the prior map stale.

### Private drafts and existing PDFs

Use `ekb validate ID --draft DRAFT.json --editorial-packet` after screening,
then follow [the editorial procedure](../prompts/resume-editorial.md).
Keep the packet and the validation reports private. A passing render has
`delivery_status: private_draft_human_approval_required`. Approve delivery
only after a human reviews the claims, inspects every page and confirms the
exact PDF against the frozen opportunity. The reviewer keeps the receipt
outside the bundle and runs `ekb verify-review ID --approval RECEIPT.json`.

For an update, keep a separate draft and pass the current manifest's
`--base-generation`. The updater locks the application and tests the real
destination filesystem with disposable nonempty directories. macOS uses
`renamex_np(RENAME_SWAP)` and Linux uses `renameat2(RENAME_EXCHANGE)` when
the system library, kernel and filesystem provide the operation. A fresh
path uses one directory rename. An existing path requires exchange and a
failed probe leaves it in place. Use a verified local volume for further
private drafting if exchange is unavailable.

After an interrupted update, use the published application directory as the
source of truth. Read its `validation.json` and check its `generation`,
`primary_pdf`, every SHA-256 under `outputs`, and `report_sha256` for
`validation.md`. A normal update checks the previous manifest before
proceeding. Ignore hidden `.ekb-resume-*` and `.ekb-exchange-probe-*`
directories while recovering. Clean them up only when no render is active.
Use the manifest's primary PDF when legacy copies also exist.

The exchange is the commit point for a single directory generation. Review
and hash the same generation before delivery. A reader opening separate files
across a concurrent swap must recheck the generation and hashes. Guarantees
cover cooperating writers and process interruptions on tested volumes.
Power loss, filesystem or storage failures, and untested network or sync
providers are outside that verification.

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

Inspect the shipped fictional workspace without rewriting the saved shortlist:

```bash
export EKB_WORKSPACE=$PWD/examples/sample-workspace
scripts/ekb status
scripts/ekb check
scripts/ekb shortlist 2026-03-14-northwind-flutter-engineer --stdout
unset EKB_WORKSPACE
```

Read these three files in this order and the design will make sense:

1. `projects/fittrack.yaml` — what a curated record looks like
2. `context/fittrack-questions.md` — the conversation that produced it,
   including the candidate that was dropped and why
3. `applications/2026-03-14-northwind-flutter-engineer.evidence.yaml` — the
   historical selection decisions

The [sample README](../examples/sample-workspace/README.md#reproduce-the-example-pdf)
describes the disposable PDF replay.

### Whole-candidate matching

After screening, use the [discovery procedure](../prompts/capability-discovery.md)
and inspect `ekb shortlist ID --stdout`. The requirement map combines project
leads, existing profile sources, confirmed broader capabilities, and related
engineering examples. Record the selected refs and rationale before drafting.
See the [controlled-use policy for capabilities](controlled-use-capabilities.md)
for review, interview preparation, and delivery.
