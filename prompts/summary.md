# Summary — professional summaries for any venue

Parameters:

- `VENUE` — `resume`, `profile-headline`, `profile-about`, `portfolio`, or
  `cover-letter`. Defaults to `resume`.
- `TARGET` — optional role, company, or pasted posting to aim at.
- `LENGTH` — optional word budget, overriding the venue default.

Follow `AGENTS.md`. This procedure writes
`artifacts/summaries/<venue>[-<target>].md` and nothing else.

---

## Why this is its own procedure

A summary is the one piece of career writing with no single record behind it. It
is inherently cross-project, which is exactly why it is the easiest place for an
unsupported claim to appear: no individual sentence looks like it belongs to a
project, so nothing obviously fails a source check.

The rule is therefore stricter here, not looser. **Every clause still cites
something.** A cross-project claim uses composed sources; see `prompts/resume.md`
section 5.

## Sources

- `profile/professional-profile.yaml` for what holds across projects: which
  strengths are `signature`, what the standing constraints cap, what must never
  be claimed. It supplies framing, never facts.
- `profile/profile.yaml` for identity, timeline, responsibilities, and skills.
  Responsibilities are the only route by which client-facing work, requirements
  gathering, mentoring, or a working method can appear at all.
- Curated `projects/*.yaml` for anything specific.
- `profile/project-ranking.yaml` to decide which specifics earn the space.

Never read candidate files, generated artifacts, or target repositories.

## Venue budgets

| Venue | Budget | Voice | Notes |
|---|---|---|---|
| `resume` | 40 words | third person, implied subject | Ceiling, not a target. Governed by `prompts/resume-presentation.md`. |
| `profile-headline` | 15 words | noun phrase | Role identity plus the one specialization the evidence supports. |
| `profile-about` | 120 words | first person | The only venue where first person reads naturally. |
| `portfolio` | 80 words | third person | Written for someone who arrived from a project page and wants context. |
| `cover-letter` | 150 words | first person | Opening paragraph only. Never generate a full letter here. |

## What a summary should carry

**Spend the words on what no project page or bullet can carry.**

- shipping and delivery scale across the whole portfolio;
- domain breadth, when it is real breadth and not one project each;
- the client-facing and requirements work that leaves no Git trace;
- the specialization every other artifact supports;
- the working method, when it is confirmed and distinctive.

Do not repeat a fact a selected bullet already carries. Cite it once, in the
place a reader reads first.

**Do not state a years-of-experience figure.** A timeline states it better, and
a stated figure invites arithmetic.

## Targeting

With no `TARGET`, weight by the actual eligible body of work: the dominant
specialization gets the largest share, then the strongest distinct fields. Raw
project count is not enough — weight by depth, supported involvement, strength
tier, distinctiveness, and rank. Breadth does not mean equal space for
everything.

With a `TARGET`, lead with the capabilities it asks for and the evidence
supports. Narrow unrelated domains. **Never inflate a small exposure because the
target names it.** If the target's central requirement has no eligible evidence,
say so at delivery rather than writing around it.

If the target is a full posting rather than a role name, run `prompts/screen.md`
first.

## Writing

Follow `config/resume-policy.json` `writing_style`. No em dash, en dash, or
arrow. None of the listed generic terms.

Beyond the mechanical rules:

- open with the professional identity, not with an adjective;
- one concrete specific beats three abstractions. A named integration, a real
  constraint, or a delivered surface says more than "experienced";
- vary sentence length. Three sentences of identical shape read as generated;
- do not describe the reader's problem back to them;
- do not claim enthusiasm. Nobody has ever been hired for asserting passion.

## Deliver

Produce the requested venue, plus one shorter variant when the venue has an
obvious constrained form (a headline beside an about section, for instance).

Below the output, list privately:

- the source ID behind every clause;
- any constraint from the professional profile that shaped a phrasing;
- anything true that was left out for space, so the user can trade it in.

Never post, publish, or send a summary anywhere. Output is ready-to-paste text
for the user to place themselves.
