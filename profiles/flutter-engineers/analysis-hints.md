# Where career evidence hides in a Flutter repository

Read by `prompts/analyze.md` when this pack is active. These are hints about
where high-value engineering work tends to live in this ecosystem, so a scout
does not rediscover it on every run.

**These are not a checklist.** A hint that does not apply produces nothing at
all. Never write "no evidence found" for a category the repository simply does
not have, and never promote routine work to fill a hint.

The rule that governs all of them: an interesting record needs an engineering
DECISION behind it, not just a technology present in `pubspec.yaml`. "Uses
Riverpod" is inventory. "Replaced three overlapping state solutions with one
after the third caused a rebuild loop in checkout" is a record.

---

## Architecture and structure

- The first commit that introduced a layer boundary, and what forced it.
- A migration between state management approaches. The interesting part is
  usually why the old one stopped working at that codebase's size, and what
  had to be rewritten to move.
- A move from a single package to a monorepo, feature packages, or melos, and
  what problem the split solved.
- Dependency injection introduced or replaced, especially when it changed how
  the app is tested.
- Code generation adopted or removed. Adopting `freezed`, `json_serializable`,
  or `build_runner` changes the team's iteration loop, and abandoning it is a
  more interesting record than adopting it.

## Platform work

- Anything under `android/` or `ios/` beyond the generated defaults. Manifest
  permissions, `Info.plist` entries, Gradle changes, entitlements, and signing
  configuration all mark real platform work.
- Platform channels, FFI, or a written plugin. This is the clearest evidence a
  Flutter engineer worked below the framework.
- Background execution, foreground services, background location, and workmanager
  usage. These are hard, and their bug fixes tell better stories than their
  introductions.
- Deep links and app links, including the association files that make them work.

## Release and delivery

- CI configuration for build, test, and distribution, and every change to it.
- Flavors, build variants, environment configuration, and how secrets are kept
  out of the binary.
- Store submission evidence: version bumps, changelogs, upload metadata,
  rejection fixes. A rejection and its fix is a strong record.
- Code push or over-the-air update tooling, and what constraint made it worth
  adopting.
- Obfuscation, minification, and app size work.

## Data and integration

- The networking layer: interceptors, retries, token refresh, error mapping.
  Token refresh under concurrent requests is a classic hard problem and its
  solution is usually visible in the diff.
- Offline behavior: local persistence, cache invalidation, conflict resolution,
  and what happens on reconnect. Offline-first is claimed often and implemented
  rarely, so real evidence here is distinctive.
- Third-party integrations with a real trust boundary: payments, mapping,
  authentication providers, analytics. Two payment integrations are not
  redundant if they have different failure models.

## Quality

- Widget, golden, and integration tests, especially the first one added and
  what it was protecting.
- A test that pins a bug. `git log` on a test file often names the incident.
- Deterministic time, fake clocks, and controlled randomness in tests.
- Static analysis rules added to `analysis_options.yaml` and the cleanup that
  followed.

## Performance

- Anything with a before and after: a profiling session, a frame timing capture,
  a startup measurement, an app size comparison. These records are rare and
  disproportionately valuable, because they are the only ones that license
  comparative language.
- `const` sweeps, list virtualization, image caching, isolate offloading, and
  rebuild scoping. Look for the commit message that names the symptom.

## Localization and reach

- RTL support, and what broke when it was added. RTL is a genuinely different
  layout problem, not a translation task.
- Accessibility work: semantics, contrast, text scaling, screen reader support.
- Adaptive layout for tablets, foldables, or desktop targets.

---

## What to skip

- Dependency inventories. A list of packages is not engineering evidence.
- Generated files, `.g.dart`, `.freezed.dart`, and lockfiles as content.
- Boilerplate scaffolding from `flutter create`.
- Version bumps with no accompanying change.
- Formatting-only commits and import sorting.
