# Engineering Knowledge Base Toolkit

Turn your Git history into career evidence you can defend in an interview.

The EKB Toolkit helps Flutter engineers build a private, structured record of
their work, then use it to prepare interview stories, project bullets, tailored
resumes, and cover letters. An AI coding agent examines repository history,
proposes evidence, and asks you to confirm anything it cannot observe.

The toolkit keeps three things separate:

- what the repository proves;
- what you confirm from your own experience; and
- what the agent only infers.

Only repository evidence and facts you confirm may support a public claim.
Everything is stored as local YAML and Markdown files that you own.

## Quick start

You need Git, Python 3.10+, and an AI coding agent that can read files and run
commands, such as Codex, Claude Code, Gemini CLI, or Cursor.

### 1. Install the toolkit

```bash
git clone https://github.com/AymanYehia23/ekb-toolkit.git
cd ekb-toolkit
pip install -r requirements.txt
scripts/ekb doctor
```

`ekb doctor` reports any missing dependencies. Ruby 3.0+ is also needed for
resume source validation and rendering.

### 2. Create your private workspace

By default, the workspace lives inside the clone. To store it somewhere else,
change `paths.workspace` in [`config/toolkit.yaml`](config/toolkit.yaml) before
running `init`.

```bash
scripts/ekb init
```

The workspace stores your profile, project evidence, job postings, and generated
documents. It is ignored by the toolkit's Git repository. Give it a separate
local Git repository if you want version history; keep any remote private.

For the default workspace location:

```bash
git -C workspace init
```

### 3. Create your profile once

Open your AI agent in the toolkit directory and say:

```text
Follow prompts/profile.md
```

This records the career facts that Git cannot provide, such as your employment
timeline, responsibilities, and confirmed links.

### 4. Use the guide for everything else

For your first project, you can give it the repository immediately:

```text
Follow prompts/guide.md and analyze /absolute/path/to/my-project
```

From then on, the guide checks your workspace, chooses the next step, and asks
only for the information it needs. You do not need to memorize the other prompts
or the file layout.

The agent reads the target repository without modifying it or running its code,
builds a small batch of candidate evidence, and pauses for your review. Nothing
is approved without your confirmation.

## Common tasks

You can keep using the guide in plain language:

| Goal | Tell your agent |
|---|---|
| Add your first project | `Follow prompts/guide.md and analyze /path/to/repo` |
| Capture new commits | `Follow prompts/guide.md and update my-project` |
| Prepare for an interview | `Follow prompts/guide.md and prepare me to discuss my-project` |
| Create project bullets | `Follow prompts/guide.md and create bullets for my-project` |
| Check a job posting | `Follow prompts/guide.md and screen this job: <paste posting>` |
| Tailor a resume | `Follow prompts/guide.md and create a resume for: <paste posting>` |
| Create a cover letter | `Follow prompts/cover-letter.md with APPLICATION_ID=<existing-id>` |

The usual workflow is:

1. **Capture** — the agent examines a repository and proposes evidence.
2. **Review** — you confirm, correct, or discard the proposals as one batch.
3. **Generate** — the toolkit creates interview stories or project bullets.
4. **Tailor** — when applying, it screens the posting before selecting evidence,
   rendering a resume, and optionally generating a cover letter.

The job-screening step always stops for your `proceed`, `declined`, or
`deferred` decision, even when it finds no blockers.

For a complete walkthrough, see [`docs/workflow.md`](docs/workflow.md).

## What the toolkit creates

Your workspace grows into a reusable engineering knowledge base:

```text
workspace/
├── profile/        confirmed career facts and cross-project context
├── projects/       reviewed evidence from each repository
├── context/        your answers and review decisions
├── applications/   job screenings and evidence selections
├── artifacts/      interview guides, bullets, resumes, and cover letters
├── index/          generated evidence index
└── EXCLUSIONS.md   paths the agent must never read
```

Generated documents are disposable. If a resume, cover letter, or interview
guide is wrong, correct the underlying record and regenerate it instead of
editing the output.

## Before using a private repository

- Confirm that your employer or client permits the code to be sent to your AI
  agent's provider. The toolkit itself does not upload anything, but your agent
  may send repository content to its model provider.
- Add sensitive files and directories to `EXCLUSIONS.md` in your workspace.
  Excluded paths must never be read, quoted, or stored.
- The analyzer treats target repositories as read-only. It does not run builds,
  tests, hooks, package managers, or project scripts, and it checks that Git
  status is unchanged when analysis finishes.
- Git authorship can support that you contributed. It cannot prove that you led
  or solely owned the work. Stronger participation claims require your explicit
  confirmation.
- Performance gains, business results, and comparative wording require actual
  before-and-after evidence or measurements you provide.

These rules are the core of the toolkit, not optional writing preferences. See
[`docs/concepts.md`](docs/concepts.md) for the evidence model and its reasoning.

## Try the example first

The repository includes a fictional workspace with two projects, interview
material, a screened job posting, and a validated resume model.

```bash
export EKB_WORKSPACE=$PWD/examples/sample-workspace
scripts/ekb status
scripts/ekb check
scripts/ekb validate 2026-03-14-northwind-flutter-engineer
```

See [`examples/sample-workspace/README.md`](examples/sample-workspace/README.md)
for a guided tour. Start a new shell or unset `EKB_WORKSPACE` before returning
to your own workspace.

## CLI reference

The AI agent handles work that requires judgement. `scripts/ekb` handles the
repeatable operations:

```text
scripts/ekb init                    create a workspace
scripts/ekb doctor                  check dependencies and setup
scripts/ekb status                  show workspace state
scripts/ekb index [--check]         rebuild the evidence index
scripts/ekb shortlist <app-id>      build an application evidence shortlist
scripts/ekb check                   check cross-file consistency
scripts/ekb skills [--tags]         check the evidence behind profile skills
scripts/ekb validate <app-id>       validate sources without rendering
scripts/ekb render <app-id>         validate and create DOCX and PDF files
scripts/ekb compare a.json b.json   compare two resume drafts
scripts/ekb git <mode> [...]        create a local workspace checkpoint
```

Run `scripts/ekb` without arguments to see the current command help.

## Documentation

| Guide | Use it when you want to... |
|---|---|
| [Workflow](docs/workflow.md) | follow the full process from setup to a tailored resume |
| [Concepts](docs/concepts.md) | understand provenance, participation, and claim eligibility |
| [Configuration](docs/configuration.md) | change paths, evidence rules, screening, or resume policy |
| [Architecture](docs/architecture.md) | understand how evidence, retrieval, and generation fit together |
| [FAQ](docs/faq.md) | troubleshoot common workflow and validation questions |
| [Extending](docs/extending.md) | add support for another engineering discipline |
| [Roadmap](docs/roadmap.md) | see planned and explicitly out-of-scope work |

The current role profile is designed for Flutter engineers. Most of the toolkit
is stack-agnostic, but other disciplines need their own profile pack for the
best analysis and selection results.

## Contributing

Contributions are welcome, especially new role profile packs. A change must not
make it easier to publish a claim the user cannot defend.

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

MIT. See [`LICENSE`](LICENSE).
