"""Converte somente variáveis permitidas; não imprime os valores."""
import json
import sys
from pathlib import Path

from dotenv import dotenv_values

REQUIRED = ("DATABASE_URL", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME", "CORS_ORIGINS")
OPTIONAL = ("APP_NAME", "R2_PUBLIC_URL")
values = dotenv_values(sys.argv[1])
missing = [key for key in REQUIRED if not values.get(key)]
if missing:
    raise SystemExit("Variáveis ausentes: " + ", ".join(missing))
selected = {key: values[key] for key in REQUIRED}
selected.update({key: values[key] for key in OPTIONAL if values.get(key)})
# JSON é um subconjunto de YAML; o arquivo temporário é criado pelo mktemp.
Path(sys.argv[2]).write_text(json.dumps(selected), encoding="utf-8")
