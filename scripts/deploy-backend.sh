#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_file="${MDCA_ENV_FILE:-$repo_dir/Backend/.env}"
project="${GCP_PROJECT:-pratica-em-es-mdca}"
region="${GCP_REGION:-southamerica-east1}"
service="${CLOUD_RUN_SERVICE:-pratica-em-es-mdca}"
python_cmd="${MDCA_PYTHON:-$repo_dir/.venv/bin/python}"

if [[ ! -f "$config_file" ]]; then
  printf 'Configuração ausente: %s\n' "$config_file" >&2
  exit 1
fi
config_yaml="$(mktemp "${TMPDIR:-/tmp}/mdca-env.XXXXXX")"
trap 'rm -f "$config_yaml"' EXIT

"$python_cmd" "$repo_dir/scripts/export-cloudrun-env.py" "$config_file" "$config_yaml"
gcloud run deploy "$service" \
  --project "$project" \
  --region "$region" \
  --source "$repo_dir/Backend" \
  --clear-base-image \
  --env-vars-file "$config_yaml" \
  --quiet

gcloud run services describe "$service" --project "$project" --region "$region" \
  --format='value(status.url)'
