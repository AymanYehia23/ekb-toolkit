# Checkpoint — save progress locally

Parameters:

- `MODE` — `candidates`, `snapshot`, `artifact`, `profile`, `application`, or
  `screening`.
- `PROJECT` — for project-scoped modes.
- `KIND` — `interview` or `bullets`, for artifact mode.
- `APPLICATION_ID` — for application and screening modes.

Follow `AGENTS.md`. This procedure changes only the **workspace** Git history.
Never run a Git write command in a target repository, and never push.

---

Use the helper. Do not hand-roll Git commands.

```bash
scripts/ekb git candidates  <project>            # after a verified analyze run
scripts/ekb git snapshot    <project>            # after review, candidates deleted
scripts/ekb git artifact    <project> interview  # after generating an artifact
scripts/ekb git artifact    <project> bullets
scripts/ekb git profile                          # needs profile consent
scripts/ekb git application <id>                 # needs application consent
scripts/ekb git screening   <id>                 # needs application consent
```

## What the helper guarantees

- It refuses to run when the Git index already holds staged changes, so an
  unrelated edit cannot ride along inside a checkpoint.
- It validates names before touching anything.
- It stages **only** the named paths for the selected mode. There is no broad
  `git add` anywhere in it.
- It unions on-disk and tracked paths, so a deleted file is recorded as a
  deletion rather than silently left behind.
- Profile, application, and screening modes require explicit consent recorded in
  `profile/profile.yaml`, and scan the changed files for credential-shaped
  content before committing. That scan **fails closed**: no scanner available
  means no checkpoint.
- It never pushes.

## What each mode produces

**`candidates`** — a commit preserving the proposed records, including ones that
will later be rejected. That history is why a dropped candidate is still
auditable after the candidates file is deleted.

**`snapshot`** — the curated knowledge and its context log, then the next unused
`<project>/vN` tag. Tags mark accepted knowledge snapshots.

**`artifact`** — the generated file only, and **no tag**. Artifacts are
disposable: they can always be rebuilt from the tagged curated YAML, so a tag
would mark nothing.

**`profile`** — the confirmed profile, the derived professional profile, the
ranking, the screening policy, and their context logs, then the next
`profile/vN` tag.

**`application`** — the frozen posting, its screening record, its evidence
shortlist, and the rendered outputs.

**`screening`** — the frozen posting and its screening record only. It requires
no rendered artifact, so a declined opportunity can be saved without a resume.

## If it fails

If the helper reports no changes, the step was already saved. If it fails for
any other reason, **show the error plainly**. Do not replace it with a broader
`git add`, a manual commit, a tag, a reset, or a push.

The failure modes it reports are the ones worth stopping for: a dirty index,
missing consent, a pending review, or credential-shaped content in a file about
to enter permanent history.
