# Your workspace

This directory holds YOUR knowledge base. Nothing here belongs to the toolkit.

Run `scripts/ekb init` to scaffold it:

    profile/         confirmed facts about you, and the derived profiles
    projects/        one curated YAML file per analyzed repository
    context/         the conversation behind each project's records
    applications/    frozen job postings, screenings, evidence shortlists
    artifacts/       generated interview guides, bullet banks, resumes
    index/           the generated evidence index
    EXCLUSIONS.md    what analyzers must never read

Everything except this file is gitignored by the toolkit, so pushing the
toolkit can never carry your career data with it.

**Give this directory its own Git repository.** Your knowledge base has a
version history worth keeping, and it should be separate from the toolkit's:

    cd workspace && git init

Or point `paths.workspace` in `config/toolkit.yaml` somewhere outside this
clone entirely, which is the better setup once you have more than a few
projects.
