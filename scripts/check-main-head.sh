#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_REPOSITORY:?Repositório não informado}"
: "${GITHUB_SHA:?Commit testado não informado}"
: "${GITHUB_OUTPUT:?Arquivo de outputs não informado}"

latest_sha="$(gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/main" --jq '.object.sha')"
if [[ "$latest_sha" == "$GITHUB_SHA" ]]; then
  printf 'current=true\n' >> "$GITHUB_OUTPUT"
else
  printf 'current=false\n' >> "$GITHUB_OUTPUT"
  printf 'Deploy ignorado: existe um commit mais recente na main.\n'
fi
