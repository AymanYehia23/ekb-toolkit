# Roadmap

Ordered by how likely each is to actually happen. Nothing here is a commitment.

---

## Near term

**`ekb verify`.** Re-resolve every record's evidence against the current
repository and report what has drifted: a commit range that no longer exists
after a rebase, a file path that moved, a record whose supporting diff is gone.
Today a knowledge base can silently decay against its own sources.

**Prompt regression fixtures.** A fixed repository, a fixed posting, and an
assertion about which records selection should land on. This is the largest gap
in the project: the scripts are tested and the judgement is not.

## Medium term

**Additional role profile packs.** Backend, frontend, Android, iOS, DevOps, QA,
and data engineering are all plausible. The architecture is ready; the content
is not. See [extending.md](extending.md) — this is the most useful thing anyone
can contribute.

**Multi-pack workspaces.** For engineers whose work genuinely spans two
disciplines. Needs a rule for how alignment anchors combine without producing a
gate that accepts everything.

**Resume import.** Extract a first profile draft from an existing resume, so the
initial session is a correction pass rather than a blank form. The risk is
obvious: an old resume's claims must arrive as proposals, never as confirmed
facts.

**A Python port of the source checker.** Removes the Ruby dependency for people
who do not have it.

## Longer term, and uncertain

**A read-only local viewer.** Browse records, see which are cited where, find
the evidence behind a bullet. Read-only and local, or not at all.

**Application outcome tracking.** Record which applications led to interviews
and see which evidence correlates. Genuinely useful, and genuinely easy to turn
into superstition on a sample of eleven applications. Would need to state its
own confidence honestly, which is most of the work.

**Team knowledge bases.** Shared engineering records for a team, with per-person
involvement. A different product with a different privacy model, and probably a
different repository.

## Explicitly out of scope

- **Anything that submits.** No applications, no posts, no platform accounts, no
  automated outreach.
- **Any hosted or multi-user version.** Local files you own is the point.
- **Scoring your fit for a job.** The toolkit scores its own selection, never
  you. A fit score implies precision the evidence cannot provide and would be
  believed anyway.
- **Making claims easier.** Every request that amounts to "let it say more with
  less evidence" is a request to break the one thing this does.

## How to influence this

Open an issue describing the problem rather than the feature. The most useful
issues so far in the design of this toolkit have been of the form "here is a
resume it generated that was worse than the evidence supported, and here is
why", which is how the retrieval layer came to exist at all.
