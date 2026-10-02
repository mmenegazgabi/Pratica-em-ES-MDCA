import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def load_deploy_app():
    spec = importlib.util.spec_from_file_location(
        "mdca_deploy", Path(__file__).parents[1] / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


def test_financial_routes_are_served_by_deploy_app():
    client = TestClient(load_deploy_app())
    response = client.post("/orcamentos", json={
        "projeto_id": "infra-integration",
        "valor_total": 1000,
        "data_inicio": "2026-01-01",
        "data_fim": "2026-12-31",
        "categorias_despesa": ["materiais"],
    })
    assert response.status_code == 201
    detail = client.get("/orcamentos/" + response.json()["id"])
    assert detail.status_code == 200
    assert detail.json()["saldo"] == 1000


def test_liveness_does_not_require_database_connection():
    with patch.dict(os.environ, {}, clear=True):
        client = TestClient(load_deploy_app())
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/db/health").status_code == 503


def test_cors_allows_only_configured_frontend():
    with patch.dict(os.environ, {"CORS_ORIGINS": "https://mdca-example.pages.dev"}):
        client = TestClient(load_deploy_app())
    headers = {"Origin": "https://mdca-example.pages.dev", "Access-Control-Request-Method": "POST"}
    assert client.options("/files", headers=headers).headers["access-control-allow-origin"] == headers["Origin"]
    headers["Origin"] = "https://outro.example"
    assert client.options("/files", headers=headers).status_code == 400


def test_private_r2_bucket_does_not_require_public_url():
    from Shared.storage import get_r2_config
    with patch.dict(os.environ, {
        "R2_ACCOUNT_ID": "account",
        "R2_ACCESS_KEY_ID": "key",
        "R2_SECRET_ACCESS_KEY": "secret",
        "R2_BUCKET_NAME": "mdca-arquivos",
    }, clear=True):
        config = get_r2_config()
    assert config.public_url == ""
