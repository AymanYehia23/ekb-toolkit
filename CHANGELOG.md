# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Stable professional title in resume headers.** Profiles now record a
  confirmed professional title, and every TXT, DOCX, and PDF resume renders it
  on a centered line directly below the name.
- **Optional cover-letter generation.** Every completed job-targeted resume now
  ends with an opt-in question. The new procedure reuses the screened
  application and selected evidence, follows a three-paragraph framework, and
  keeps candidate claims traceable through private source comments.

## [0.1.0] - 2026-08-02

Initial public release. The evidence, retrieval, and generation layers,
extracted and generalized from a private toolkit.

### Added

- **Evidence layer.** Curated project records carrying `kind` (provenance) and
  `involvement` (participation), each with its evidence, reasoning, and
  limitations. Written only through `prompts/review.md`, append-only, with your
  decisions.
- **Retrieval layer.** A generated evidence index, a job-independent project
  ranking, a derived professional profile, and a per-requirement evidence
  shortlist. All derived; none of them citable as a source.
- **Generation layer.** Interview guides carrying the follow-up questions each
  story invites, single-project bullet banks, professional summaries for five
  venues, and tailored ATS resumes rendered to DOCX and PDF.
- **A source checker** that refuses to render any visible line without an
  eligible source, rejects wording stronger than a record's involvement
  supports, and grades requirement coverage as demonstrated, stated, or
  unsupported.
- **A pre-application screening gate** that always stops for your decision, with
  a domain-exclusion list that ships empty on purpose.
- **`scripts/ekb`**, one entry point for every deterministic operation, plus
  `ekb init`, `ekb doctor`, and `ekb status` for onboarding.
- **Workspace separation.** The toolkit and your knowledge base are different
  trees, so you can pull updates without ever risking your data.
- **The `flutter-engineers` role profile pack**, and the extension point that
  makes a second pack three files and no code.
- **A complete fictional worked example** in `examples/sample-workspace/`: two
  projects, a posting, an evidence shortlist with authored decisions, and a
  resume that validates at 95/100.
- **CI** covering syntax, YAML and JSON parsing, a personal-data guard, the full
  pipeline against the example workspace, a real render, and 105 tests.

[Unreleased]: https://github.com/AymanYehia23/ekb-toolkit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/AymanYehia23/ekb-toolkit/releases/tag/v0.1.0
