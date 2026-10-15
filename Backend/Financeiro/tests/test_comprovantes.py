"""T-11 · US-03 — Armazenamento de comprovantes acessível apenas via API autenticada."""

import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from Financeiro.comprovantes import (
    TAMANHO_MAXIMO_BYTES,
    ArmazenamentoEmMemoria,
    ArmazenamentoR2,
    chave_valida,
    detectar_tipo,
    gerar_chave,
    limpar_nome_original,
    TIPOS_ACEITOS,
)
from Financeiro.main import app
from Financeiro.routers.comprovantes import obter_armazenamento

TOKEN = "token-de-teste-123"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64
HEIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"\x00" * 64

client = TestClient(app)


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    armazenamento = ArmazenamentoEmMemoria()
    app.dependency_overrides[obter_armazenamento] = lambda: armazenamento
    yield armazenamento
    app.dependency_overrides.clear()


def enviar(conteudo=JPEG, nome="nota.jpg", content_type="image/jpeg", headers=AUTH):
    return client.post(
        "/comprovantes",
        files={"arquivo": (nome, conteudo, content_type)},
        headers=headers,
    )


# --- Critério 1: acessível apenas via API autenticada -----------------------


def test_upload_autenticado_salva_no_bucket_e_retorna_201(ambiente):
    resposta = enviar()

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert chave_valida(corpo["chave"])
    assert corpo["chave"] in ambiente.objetos
    assert corpo["content_type"] == "image/jpeg"
    assert corpo["tamanho"] == len(JPEG)


def test_comprovante_enviado_e_lido_pela_api_com_autenticacao():
    chave = enviar(conteudo=PDF, nome="recibo.pdf", content_type="application/pdf").json()["chave"]

    resposta = client.get(f"/{chave}", headers=AUTH)

    assert resposta.status_code == 200
    assert resposta.content == PDF
    assert resposta.headers["content-type"] == "application/pdf"
    assert resposta.headers["cache-control"] == "private, no-store"
    assert resposta.headers["x-content-type-options"] == "nosniff"


def test_resposta_do_upload_nao_expoe_url_publica_do_bucket():
    corpo = enviar().json()

    assert corpo["url"] == f"/{corpo['chave']}"
    assert "r2.cloudflarestorage.com" not in corpo["url"]
    assert "r2.dev" not in corpo["url"]


# --- Critério 2: acesso sem autenticação é negado ---------------------------


def test_upload_sem_token_retorna_401(ambiente):
    resposta = enviar(headers={})

    assert resposta.status_code == 401
    assert resposta.headers["www-authenticate"] == "Bearer"
    assert ambiente.objetos == {}


def test_leitura_sem_token_retorna_401_mesmo_com_arquivo_existente():
    chave = enviar().json()["chave"]

    resposta = client.get(f"/{chave}")

    assert resposta.status_code == 401
    assert resposta.content != JPEG


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer token-errado"},
        {"Authorization": f"Basic {TOKEN}"},
        {"Authorization": "Bearer "},
        {"X-Token": TOKEN},
    ],
)
def test_token_invalido_ou_em_formato_errado_retorna_401(headers):
    chave = enviar().json()["chave"]

    assert client.get(f"/{chave}", headers=headers).status_code == 401
    assert enviar(headers=headers).status_code == 401


def test_sem_token_configurado_no_servidor_nada_e_aceito(monkeypatch):
    chave = enviar().json()["chave"]
    monkeypatch.delenv("FINANCEIRO_API_TOKEN")

    assert client.get(f"/{chave}", headers=AUTH).status_code == 503
    assert enviar().status_code == 503


@pytest.mark.parametrize(
    "caminho",
    [
        "/comprovantes/2026/10/arquivo.txt",
        "/comprovantes/2026/10/" + "a" * 32 + ".exe",
        "/comprovantes/gestao/docs/" + "a" * 32 + ".pdf",
    ],
)
def test_chave_fora_do_padrao_nao_le_outras_pastas(caminho):
    assert client.get(caminho, headers=AUTH).status_code == 404


def test_comprovante_inexistente_retorna_404():
    caminho = "/comprovantes/2026/10/" + "0" * 32 + ".jpg"

    assert client.get(caminho, headers=AUTH).status_code == 404


# --- Critério 3: uso controlado (camada gratuita) e validação ---------------


def test_arquivo_vazio_retorna_400():
    assert enviar(conteudo=b"").status_code == 400


def test_arquivo_maior_que_5mb_retorna_413_e_nao_e_salvo(ambiente):
    grande = JPEG + b"\x00" * TAMANHO_MAXIMO_BYTES

    resposta = enviar(conteudo=grande)

    assert resposta.status_code == 413
    assert ambiente.objetos == {}


def test_arquivo_no_limite_de_5mb_e_aceito():
    no_limite = JPEG + b"\x00" * (TAMANHO_MAXIMO_BYTES - len(JPEG))

    assert enviar(conteudo=no_limite).status_code == 201


def test_arquivo_disfarcado_de_imagem_e_recusado(ambiente):
    resposta = enviar(conteudo=b"<script>alert(1)</script>", nome="foto.jpg")

    assert resposta.status_code == 400
    assert ambiente.objetos == {}


@pytest.mark.parametrize(
    "conteudo, content_type_detectado",
    [
        (JPEG, "image/jpeg"),
        (PNG, "image/png"),
        (WEBP, "image/webp"),
        (HEIC, "image/heic"),
        (PDF, "application/pdf"),
    ],
)
def test_tipos_aceitos_usam_o_tipo_detectado_e_nao_o_enviado(conteudo, content_type_detectado):
    resposta = enviar(conteudo=conteudo, content_type="application/octet-stream")

    assert resposta.status_code == 201
    assert resposta.json()["content_type"] == content_type_detectado


def test_falha_no_armazenamento_retorna_503(ambiente):
    def falhar(*_args, **_kwargs):
        raise RuntimeError("R2 fora do ar")

    ambiente.salvar = falhar

    assert enviar().status_code == 503


def test_sem_configuracao_do_r2_retorna_503(monkeypatch):
    app.dependency_overrides.clear()
    for nome in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"):
        monkeypatch.delenv(nome, raising=False)

    assert enviar().status_code == 503


# --- Regras puras -----------------------------------------------------------


def test_chave_gerada_fica_na_pasta_de_comprovantes_por_ano_e_mes():
    agora = datetime(2026, 10, 14, tzinfo=timezone.utc)

    chave = gerar_chave(TIPOS_ACEITOS["pdf"], agora)

    assert re.fullmatch(r"comprovantes/2026/10/[0-9a-f]{32}\.pdf", chave)
    assert chave_valida(chave)


def test_nome_original_e_limpo_para_metadados_e_cabecalho():
    assert limpar_nome_original('../../recibo "março".pdf') == "recibo__mar_o_.pdf"
    assert limpar_nome_original(None) == "comprovante"


def test_detectar_tipo_recusa_formatos_fora_da_lista():
    assert detectar_tipo(b"GIF89a" + b"\x00" * 10) is None
    assert detectar_tipo(b"<svg></svg>") is None


def test_armazenamento_r2_envia_objeto_privado_com_tipo_e_metadados(monkeypatch):
    from botocore.stub import Stubber

    for nome, valor in {
        "R2_ACCOUNT_ID": "conta",
        "R2_ACCESS_KEY_ID": "id",
        "R2_SECRET_ACCESS_KEY": "segredo",
        "R2_BUCKET_NAME": "mdca-arquivos",
    }.items():
        monkeypatch.setenv(nome, valor)
    r2 = ArmazenamentoR2()
    chave = "comprovantes/2026/10/" + "a" * 32 + ".jpg"

    with Stubber(r2._client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "mdca-arquivos",
                "Key": chave,
                "Body": JPEG,
                "ContentType": "image/jpeg",
                "Metadata": {"nome-original": "nota.jpg"},
            },
        )
        r2.salvar(chave, JPEG, "image/jpeg", "nota.jpg")
