# Exclusions — Flutter and Dart repositories

Paths and content an analyzer must never read, quote, or store. `ekb init`
copies these into your workspace `EXCLUSIONS.md`, where you add your own
repository-specific entries.

Paths are relative to the target repository root.

## Secrets — never read, never quote, never store

Reference the LOCATION of a credential if it matters to a record. Never
reproduce its value, not even partially, and not in a commit message quote.

- `**/.env`, `**/.env.*`
- `**/*.jks`, `**/*.keystore`, `**/*.p12`, `**/*.pem`, `**/*.key`, `**/*.mobileprovision`
- `**/google-services.json`
- `**/GoogleService-Info.plist`
- `**/key.properties`
- `**/service-account*.json`
- `**/firebase_options.dart` (contains project API keys)
- `android/app/**/upload-keystore*`
- `fastlane/*.json`, `fastlane/Appfile`

## Build output and tooling caches — no signal, high noise

- `.dart_tool/`
- `build/`
- `.flutter-plugins`, `.flutter-plugins-dependencies`
- `coverage/`
- `ios/Pods/`, `macos/Pods/`
- `ios/.symlinks/`
- `android/.gradle/`, `android/local.properties`
- `.idea/`, `.vscode/`
- `node_modules/`, `vendor/`
- `.git/objects/`

## Generated source — inventory only

These may be counted or named, but their contents are not evidence of a
decision. The decision lives in the file that generated them.

- `**/*.g.dart`
- `**/*.freezed.dart`
- `**/*.gr.dart`
- `**/*.mocks.dart`
- `**/generated_plugin_registrant.*`
- `**/l10n/*.arb` beyond the source locale

## Lockfiles

`pubspec.lock`, `Podfile.lock`, and `gradle.lockfile` may be inventoried by
filename and used to establish which version of a dependency was in use. Do
not quote embedded repository URLs or credentials from them.

## Repository-specific exclusions

Add a heading with the repository's absolute path or project name before
analyzing any employer or client code. Anything under that heading is excluded
in addition to the global list above.

<!--
#### /absolute/path/to/repository

- `lib/proprietary/`
- `docs/client-contracts/`
- Topic: customer names, production endpoints, and internal identifiers
-->

## Before analyzing employer or client code

Confirm that the repository may be processed by your agent's provider at all.
A private client repository sent to a third-party model is a disclosure, and
no exclusion list makes that decision for you.
