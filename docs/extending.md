# Extending: adding a role profile pack

The toolkit ships one pack, `flutter-engineers`. Everything else is
stack-agnostic. A second pack is the highest-value contribution you can make,
and it is four files of content rather than a fork.

---

## What a pack is

A pack describes **one engineering discipline**. It states no fact about any
person, which is why it can live in a public repository and still be useful to
everyone working in that discipline.

```
profiles/<your-pack>/
├── pack.yaml            metadata, alignment anchors, misaligned archetypes
├── analysis-hints.md    where career evidence hides in this stack
└── exclusions.md        what an analyzer must never read in this stack
```

Optionally, a `capability-tags.yaml` with your stack's vocabulary folds.

Nothing outside `profiles/` names a discipline. If you find yourself wanting to
change a prompt or a script to add your pack, that is a bug in the architecture
and worth raising as an issue.

## Start

```bash
cp -r profiles/flutter-engineers profiles/backend-engineers
```

Then rewrite all three files. Do not adapt them line by line — the Flutter pack
is an example of the shape, not a base to inherit from.

## 1. `pack.yaml`

### `aligned_anchors`

What the screening gate treats as in-scope work. Coarse on purpose: this is an
in-or-out judgement made **before any retrieval**, not an assessment.

Write them as the work, not as technologies:

```yaml
aligned_anchors:
  - distributed service design and inter-service communication
  - relational data modelling and query performance
  - API design and versioning for external consumers
  - production operability: observability, on-call, incident response
```

Not `- PostgreSQL`. A technology list makes the check fire on any posting that
mentions the word once.

### `misaligned_archetypes`

Roles that are a different discipline. Each carries a severity and, where the
call is genuinely close, an `explain` that says what transfers and what does
not.

```yaml
- id: pack-misalign-003
  label: Data engineering or analytics engineering as the whole role
  severity: warning
  explain: >-
    Pipeline and schema work overlaps. The warehouse tooling, modelling
    conventions, and batch orchestration depth do not.
```

Use `blocker` when the disciplines genuinely do not overlap. Use `warning` when
domain knowledge transfers but required depth does not. **Err toward `warning`:**
a false blocker silently costs someone an opportunity, and a false warning costs
them ten seconds.

## 2. `analysis-hints.md`

The most valuable file in the pack, and the hardest to write well.

It tells an analyzer where career-relevant work **hides** in your ecosystem, so
a scout does not rediscover the stack on every run.

The rule that makes hints good:

> **An interesting record needs an engineering DECISION behind it, not a
> technology present in a manifest.**

"Uses Kafka" is inventory. "Moved from a shared topic to per-tenant topics after
a noisy-neighbour incident, accepting the partition-count cost" is a record.

Write hints as places to look, grouped by concern:

```markdown
## Data and persistence

- The first migration that changed a hot table's shape, and how it was rolled
  out. Online schema changes on a large table are hard and their commit
  messages usually say so.
- An index added in response to something. `git log` on a migration directory
  often names the incident.
- A query rewritten after a plan changed. The interesting part is how it was
  noticed.
```

Two sections make the file honest:

**A "what to skip" section.** Dependency inventories, generated code, formatting
commits, version bumps with no change. Without this, an analyzer records
everything it sees.

**An explicit statement that hints are not a checklist.** A hint that does not
apply produces nothing at all. Never write "no evidence found" for a category
the repository simply does not have.

## 3. `exclusions.md`

Three categories, in this order of importance:

**Secrets.** Every credential shape your ecosystem produces: key files,
environment files, service-account JSON, signing material, config that embeds
tokens. Be generous. A false positive costs one record; a false negative puts a
credential in a knowledge base.

**Build output and caches.** No signal, enormous noise.

**Generated source.** Nameable and countable, but its contents are not evidence
of a decision. The decision lives in whatever generated it.

Include a commented example of a repository-specific section, and a closing note
that no exclusion list decides whether a private repository may be sent to a
third-party model in the first place.

## 4. Test it

Point the toolkit at two real repositories in your discipline — ideally one
mature and one small.

```bash
# in config/toolkit.yaml
paths:
  profile_pack: profiles/backend-engineers
```

Then run an analyze pass and judge the output against three questions:

1. **Did it find the work that matters?** If the strongest thing you did in that
   repository is missing, a hint is missing.
2. **Could you defend every statement in an interview?** If not, the hints are
   pointing at inventory rather than decisions.
3. **Did it record what it could not see?** A clean analysis header on a
   repository with squashed history is a bug.

Then screen three real postings in your discipline and check that the alignment
anchors do not produce a false blocker.

## Submitting

Open a pull request with:

- the three files;
- a short note on which repositories you tested against, described generically
  ("a mature Django monolith, a small Go service");
- the postings you screened, and what the gate said.

**Do not include any real career data, any private repository content, or any
identifying detail about an employer.** A pack describes a discipline.

## What a pack may not do

- **State a fact about any person.** No names, no timelines, no skills claims.
- **Weaken an evidence rule.** A pack supplies vocabulary and search hints. It
  cannot change what may be claimed, what counts as eligible, or what a number
  may assert.
- **Require a change outside `profiles/`.** If it does, raise an issue instead;
  the extension point is wrong and should be fixed for everyone.

## Beyond packs

Other contributions worth making, roughly in order of value:

**Prompt regression fixtures.** A fixed repository, a fixed posting, and an
assertion about which records selection should land on. This repository has no
harness for evaluating prompts, which is its largest gap.

**Renderer improvements.** Layout, ATS parity, and accessibility of the output
documents.

**A second checker implementation.** The source checker is Ruby. A Python port
would remove a dependency for people who do not have Ruby.

See [`CONTRIBUTING.md`](../CONTRIBUTING.md).
