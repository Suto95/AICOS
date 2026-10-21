#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

timestamp="$(date +%Y%m%d_%H%M%S)"
branch_name="backup/$timestamp"
tag_name="snapshot/$timestamp"

current_branch="$(git rev-parse --abbrev-ref HEAD)"
current_commit="$(git rev-parse --short HEAD)"

git branch "$branch_name"
git tag -a "$tag_name" -m "Safety snapshot before migration changes ($timestamp)"

printf '%s\n' "Created safety snapshot from branch: $current_branch"
printf '%s\n' "Commit: $current_commit"
printf '%s\n' "Backup branch: $branch_name"
printf '%s\n' "Backup tag: $tag_name"
printf '%s\n' "Rollback reference: git checkout $tag_name"