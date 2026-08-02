# Contributing

Thanks for looking. Contributions are welcome, particularly role profile packs.

---

## The one rule

> **A change that makes it easier to claim something you cannot defend is not an
> improvement, however much nicer the output reads.**

Every constraint in this repository exists because the alternative produced a
document that collapsed under a follow-up question. If a rule looks arbitrary,
it probably has a failure behind it that the comment does not fully explain —
ask before removing it.

Concretely, a pull request will not be merged if it:

- adds `inferred` to eligible evidence kinds, or `unknown` to eligible
  involvement;
- lets a derived file (`professional-profile.yaml`, `project-ranking.yaml`,
  `evidence-index.yaml`, `<id>.evidence.yaml`) be cited as a source;
- lets a URL be rendered that is not confirmed in the link registry;
- allows an estimated percentage, an invented gain, or business impact with no
  supplied data;
- allows a gameable count (tests, files, lines, commits) into a document;
- lets the screening gate auto-proceed;
- makes a target repository writable, or executes anything inside one.

## What is most useful

**1. A role profile pack.** Backend, frontend, Android, iOS, DevOps, QA, data.
Four files of content, no code. See [`docs/extending.md`](docs/extending.md).

**2. Prompt regression fixtures.** The scripts are tested; the judgement is not.
A fixed repository, a fixed posting, and an assertion about which records
selection should land on would be the single largest improvement to this
project's reliability.

**3. A real failure.** The most valuable issues are of the form: *here is a
generated resume that was worse than the evidence supported, and here is why.*
The retrieval layer exists because of exactly one such report.

**4. Renderer and checker work.** Layout, ATS parity, accessibility. A Python
port of `resume_source_check.rb` would remove the Ruby dependency.

## Never include personal data

No real names, contact details, employers, client names, repository paths, or
career facts — in code, fixtures, examples, issues, or commit messages.

The example workspace is entirely fictional and every address in it points at
`example.com`. Keep it that way. If you need a new example, invent one.

## Setup

```bash
git clone <your-fork> && cd ekb-toolkit
pip install -r requirements.txt
scripts/ekb doctor
```

Run everything against the shipped example rather than your own data:

```bash
export EKB_WORKSPACE=$PWD/examples/sample-workspace
scripts/ekb index
scripts/ekb check
scripts/ekb validate 2026-03-14-northwind-flutter-engineer
```

## Tests

```bash
python3 -m pytest tests/            # if pytest is available
ruby tests/test_resume_module.rb
ruby tests/test_resume_coverage.rb
```

CI runs these plus a syntax check on every script and a YAML/JSON parse of every
config, template, and example file.

If you change the source checker or the renderer, add a test. If you change a
prompt, say in the pull request what output you compared before and after — a
prompt change with no observed effect on real output is a guess.

## Style

**Scripts.** Match the surrounding code. The existing scripts explain *why* a
rule exists in a comment near the rule, not in a separate document, because a
rule whose reason is elsewhere gets deleted by the next person.

**Prompts.** Written for a language model, but readable by a person deciding
whether to trust the toolkit. Imperative, specific, and honest about what a step
cannot do. State the failure a rule prevents; a prompt full of unexplained
prohibitions gets partially ignored.

**Docs.** Say what the thing is, then what it is not, then why. Do not sell.

**Commits.** Present tense, one concern per commit.

## Pull requests

Describe the problem before the change. Include:

- what failure this addresses;
- what you tested it against;
- for a prompt change, output before and after;
- for a pack, which repositories and postings you validated with, described
  generically.

Small and specific gets reviewed fast. A sweeping refactor of the evidence rules
gets a long conversation first, which is the correct outcome.

## Code of conduct

Be decent. Assume good faith. Disagree about the work rather than about the
person. Maintainers may remove anything that makes this a worse place to
contribute.
