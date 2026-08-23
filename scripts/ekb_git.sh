#!/usr/bin/env bash
#
# Local checkpoints for the knowledge base.
#
# This script commits inside your WORKSPACE, which is a separate Git repository
# from the toolkit. It never pushes, never touches a repository you analyzed,
# and never runs a broad `git add`. Every mode stages an explicit list of paths
# so an unrelated edit sitting in your working tree cannot ride along.
#
#   candidates <project>   after an analyze run
#   snapshot   <project>   after review, creates the next <project>/vN tag
#   artifact   <project> interview|bullets
#   profile                privacy-gated, creates the next profile/vN tag
#   application <id>       privacy-gated, the frozen posting and its outputs
#   screening   <id>       privacy-gated, a screened opportunity with no resume
#   policy                 workspace resume-policy override only
#   index                  generated evidence index only
#   bullet-audit           generated cross-application bullet audit only
#
# Usage:  scripts/ekb_git.sh snapshot fittrack

set -euo pipefail

die() {
  printf 'ekb git: %s\n' "$*" >&2
  exit 1
}

usage() {
  die "usage: ekb_git.sh candidates PROJECT | snapshot PROJECT | artifact PROJECT interview|bullets | profile | application ID | screening ID | policy | index | bullet-audit"
}

[[ $# -ge 1 ]] || usage
mode="$1"

# --- locate the workspace ---------------------------------------------------
toolkit_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace="${EKB_WORKSPACE:-}"
if [[ -z "$workspace" ]]; then
  workspace="$(python3 -c 'import sys;sys.path.insert(0,sys.argv[1]+"/scripts");from ekb_paths import workspace_root;print(workspace_root())' "$toolkit_root" 2>/dev/null || true)"
fi
[[ -n "$workspace" && -d "$workspace" ]] ||
  die "cannot locate the workspace; set EKB_WORKSPACE or paths.workspace in config/toolkit.yaml"
cd "$workspace"

git rev-parse --show-toplevel >/dev/null 2>&1 ||
  die "the workspace is not a Git repository; run 'git init' in $workspace first"

[[ -d projects && -d profile ]] ||
  die "$workspace does not look like an EKB workspace (expected projects/ and profile/)"

git diff --cached --quiet ||
  die "the Git index already contains staged changes; unstage or commit them first"

commit_if_changed() {
  local message="$1"
  shift
  git add -A -- "$@"
  if git diff --cached --quiet; then
    printf 'ekb git: no changes to commit\n'
    return 1
  fi
  git commit -m "$message"
}

next_tag() {
  # Highest existing <prefix>/vN plus one. Tags mark accepted knowledge
  # snapshots; artifacts get none because they can always be regenerated.
  local prefix="$1" max=0 version
  while IFS= read -r existing; do
    version="${existing#"$prefix"/v}"
    if [[ "$version" =~ ^[0-9]+$ ]] && ((version > max)); then max="$version"; fi
  done < <(git tag --list "$prefix/v*")
  printf '%s/v%d\n' "$prefix" "$((max + 1))"
}

require_name() {
  [[ $# -ge 2 ]] || usage
  name="$2"
  [[ "$name" =~ ^[a-z0-9][a-z0-9_-]*$ ]] ||
    die "name must use lowercase letters, digits, hyphens, or underscores"
}

require_consent() {
  # Git history is permanent. Personal data enters it only with recorded
  # consent, and a missing answer reads as declined.
  local key="$1"
  [[ -f profile/profile.yaml ]] || die "profile/profile.yaml does not exist"
  python3 - "$key" <<'PY' || die "privacy consent is not granted in profile/profile.yaml"
import sys, yaml
key = sys.argv[1]
with open("profile/profile.yaml", encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}
sys.exit(0 if (data.get("privacy") or {}).get(key) == "granted" else 1)
PY
}

add_if_present() {
  # Union of on-disk and tracked paths, so a deleted file is staged as a
  # deletion instead of being silently left behind.
  local candidate
  for candidate in "$@"; do
    if [[ -e "$candidate" ]] || git ls-files --error-unmatch "$candidate" >/dev/null 2>&1; then
      paths+=("$candidate")
    fi
  done
}

scan_for_secrets() {
  # The last gate before personal data becomes permanent. It FAILS CLOSED: no
  # scanner available means no checkpoint, not a silent pass.
  local pattern='-----BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY-----|(api[_-]?key|client[_-]?secret|access[_-]?token|password)[[:space:]]*[:=][[:space:]]*[^[:space:]#]{8,}|https?://[^/@[:space:]]+:[^/@[:space:]]+@'
  local changed=() line found status=0

  while IFS= read -r line; do
    [[ -n "$line" && -e "$line" ]] && changed+=("$line")
  done < <({ git diff --name-only -- "$@"; git ls-files --others --exclude-standard -- "$@"; } | sort -u)

  [[ ${#changed[@]} -gt 0 ]] || return 0

  if command -v rg >/dev/null 2>&1; then
    found="$(rg -li --hidden --glob '!*.docx' --glob '!*.pdf' -e "$pattern" -- "${changed[@]}")" || status=$?
  elif command -v grep >/dev/null 2>&1; then
    found="$(grep -rIliE --exclude='*.docx' --exclude='*.pdf' -e "$pattern" -- "${changed[@]}")" || status=$?
  else
    die "no secret scanner available (install ripgrep or grep); refusing to checkpoint unscanned files"
  fi

  # Both tools exit 1 for "no matches", which is the success case here.
  ((status <= 1)) || die "secret scan failed with status $status; refusing to checkpoint unscanned files"
  [[ -z "$found" ]] ||
    die "possible credential-like content in: $found (inspect these before committing)"
}

case "$mode" in
candidates)
  require_name "$@"
  [[ $# -eq 2 ]] || usage
  [[ -f "projects/$name.candidates.yaml" ]] || die "projects/$name.candidates.yaml does not exist"
  paths=("projects/$name.candidates.yaml")
  add_if_present "context/$name-questions.md"
  commit_if_changed "$name: capture analysis candidates" "${paths[@]}" || exit 0
  ;;

snapshot)
  require_name "$@"
  [[ $# -eq 2 ]] || usage
  [[ -f "projects/$name.yaml" ]] || die "projects/$name.yaml does not exist"
  [[ ! -e "projects/$name.candidates.yaml" ]] ||
    die "candidate review is still pending; refusing to snapshot"
  paths=("projects/$name.yaml")
  add_if_present "context/$name-questions.md" "projects/$name.candidates.yaml"
  if commit_if_changed "$name: update curated knowledge" "${paths[@]}"; then
    tag="$(next_tag "$name")"
    git tag "$tag"
    printf 'ekb git: created snapshot %s at %s\n' "$tag" "$(git rev-parse --short HEAD)"
  fi
  ;;

artifact)
  require_name "$@"
  [[ $# -eq 3 ]] || usage
  kind="$3"
  [[ "$kind" == "interview" || "$kind" == "bullets" ]] || die "artifact kind must be interview or bullets"
  [[ -f "artifacts/$kind/$name.md" ]] || die "artifacts/$kind/$name.md does not exist"
  commit_if_changed "$name: regenerate $kind artifact" "artifacts/$kind/$name.md" || exit 0
  ;;

profile)
  [[ $# -eq 1 ]] || usage
  require_consent profile_git
  paths=()
  add_if_present profile/profile.yaml profile/profile-context.md \
    profile/professional-profile.yaml profile/professional-profile-context.md \
    profile/project-ranking.yaml profile/screening-criteria.yaml
  [[ ${#paths[@]} -gt 0 ]] || die "no profile files to commit"
  scan_for_secrets "${paths[@]}"
  if commit_if_changed "profile: update confirmed facts" "${paths[@]}"; then
    tag="$(next_tag profile)"
    git tag "$tag"
    printf 'ekb git: created snapshot %s at %s\n' "$tag" "$(git rev-parse --short HEAD)"
  fi
  ;;

application)
  require_name "$@"
  [[ $# -eq 2 ]] || usage
  [[ -f "applications/$name.yaml" ]] || die "applications/$name.yaml does not exist"
  require_consent application_history_git
  paths=("applications/$name.yaml")
  add_if_present "applications/$name.evidence.yaml" "applications/$name.screening.yaml" \
    "artifacts/applications/$name"
  scan_for_secrets "${paths[@]}"
  commit_if_changed "application: $name" "${paths[@]}" || exit 0
  ;;

screening)
  require_name "$@"
  [[ $# -eq 2 ]] || usage
  [[ -f "applications/$name.screening.yaml" ]] || die "applications/$name.screening.yaml does not exist"
  require_consent application_history_git
  paths=("applications/$name.screening.yaml")
  add_if_present "applications/$name.yaml"
  scan_for_secrets "${paths[@]}"
  commit_if_changed "screening: $name" "${paths[@]}" || exit 0
  ;;

policy)
  [[ $# -eq 1 ]] || usage
  [[ -f config/resume-policy.json ]] || die "config/resume-policy.json does not exist"
  commit_if_changed "workspace: update resume policy" config/resume-policy.json || exit 0
  ;;

index)
  [[ $# -eq 1 ]] || usage
  [[ -f index/evidence-index.yaml ]] || die "index/evidence-index.yaml does not exist"
  commit_if_changed "index: rebuild evidence index" index/evidence-index.yaml || exit 0
  ;;

bullet-audit)
  [[ $# -eq 1 ]] || usage
  [[ -f artifacts/bullets/impact-audit.json ]] || die "artifacts/bullets/impact-audit.json does not exist"
  commit_if_changed "bullets: rebuild impact audit" artifacts/bullets/impact-audit.json || exit 0
  ;;

*)
  usage
  ;;
esac
