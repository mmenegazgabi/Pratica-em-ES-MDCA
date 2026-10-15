"""T-12 · US-03 — POST /lancamentos com upload de comprovante."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from Financeiro.comprovantes import TAMANHO_MAXIMO_BYTES, ArmazenamentoEmMemoria, chave_valida
from Financeiro.main import app
from Financeiro.orcamento import Orcamento, StatusLancamento
from Financeiro.routers.comprovantes import obter_armazenamento
from Financeiro.routers.orcamentos import _orcamentos

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
    _orcamentos.clear()
    _orcamentos.append(
        Orcamento(
            id="orcamento-1",
            projeto_id="projeto-1",
            valor_total=1000,
            data_inicio=date(2026, 1, 1),
            data_fim=date(2026, 12, 31),
            categorias_despesa=["materiais", "transporte"],
        )
    )
    armazenamento = ArmazenamentoEmMemoria()
    app.dependency_overrides[obter_armazenamento] = lambda: armazenamento
    yield armazenamento
    app.dependency_overrides.clear()
    _orcamentos.clear()


def orcamento():
    return _orcamentos[0]


def dados(**overrides):
    base = {
        "orcamento_id": "orcamento-1",
        "valor": "150.75",
        "descricao": "Lanche da oficina",
        "categoria": "materiais",
        "data_despesa": "2026-10-10",
    }
    base.update(overrides)
    return base


def enviar(conteudo=JPEG, nome="nota.jpg", content_type="image/jpeg", headers=AUTH, **campos):
    arquivos = None if conteudo is None else {"comprovante": (nome, conteudo, content_type)}
    return client.post("/lancamentos", data=dados(**campos), files=arquivos, headers=headers)


def nada_foi_criado(armazenamento):
    return orcamento().lancamentos == [] and armazenamento.objetos == {}


# --- Critério 1: comprovante obrigatório ------------------------------------


def test_lancamento_sem_comprovante_retorna_400_e_nao_cria_nada(ambiente):
    resposta = enviar(conteudo=None)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Comprovante obrigatório."
    assert nada_foi_criado(ambiente)


def test_lancamento_com_arquivo_vazio_e_tratado_como_sem_comprovante(ambiente):
    resposta = enviar(conteudo=b"")

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Comprovante obrigatório."
    assert nada_foi_criado(ambiente)


# --- Critério 2: lançamento válido nasce "Pendente de aprovação" ------------


def test_lancamento_valido_com_comprovante_e_criado_como_pendente(ambiente):
    resposta = enviar()

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["status"] == "pendente"
    assert corpo["status_descricao"] == "Pendente de aprovação"
    assert corpo["orcamento_id"] == "orcamento-1"
    assert corpo["valor"] == 150.75
    assert corpo["descricao"] == "Lanche da oficina"
    assert corpo["categoria"] == "materiais"
    assert corpo["data_despesa"] == "2026-10-10"

    [lancamento] = orcamento().lancamentos
    assert lancamento.id == corpo["id"]
    assert lancamento.status == StatusLancamento.PENDENTE
    assert lancamento.comprovante_chave == corpo["comprovante"]["chave"]


def test_comprovante_vai_para_o_bucket_e_fica_ligado_ao_lancamento(ambiente):
    corpo = enviar(conteudo=PDF, nome="recibo.pdf", content_type="application/pdf").json()

    chave = corpo["comprovante"]["chave"]
    assert chave_valida(chave)
    assert ambiente.objetos[chave].conteudo == PDF
    assert corpo["comprovante"]["url"] == f"/{chave}"
    assert corpo["comprovante"]["nome_original"] == "recibo.pdf"


def test_comprovante_do_lancamento_pode_ser_lido_pela_api_autenticada():
    corpo = enviar(conteudo=PNG, nome="foto.png", content_type="image/png").json()

    resposta = client.get(corpo["comprovante"]["url"], headers=AUTH)

    assert resposta.status_code == 200
    assert resposta.content == PNG


def test_lancamento_pendente_nao_altera_o_saldo():
    enviar(valor="400")

    assert orcamento().saldo == 1000


def test_lancamento_criado_pode_ser_aprovado_e_entao_debita_o_saldo():
    lancamento_id = enviar(valor="400").json()["id"]

    resposta = client.post(f"/orcamentos/orcamento-1/lancamentos/{lancamento_id}/aprovar")

    assert resposta.status_code == 200
    assert resposta.json()["saldo"] == 600


# --- Critério 3: tipo (imagem/PDF) e tamanho máximo -------------------------


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
def test_aceita_imagens_e_pdf(conteudo, content_type_detectado):
    resposta = enviar(conteudo=conteudo, content_type="application/octet-stream")

    assert resposta.status_code == 201
    assert resposta.json()["comprovante"]["content_type"] == content_type_detectado


@pytest.mark.parametrize(
    "conteudo, nome",
    [
        (b"<script>alert(1)</script>", "nota.jpg"),
        (b"GIF89a" + b"\x00" * 16, "nota.gif"),
        (b"PK\x03\x04" + b"\x00" * 16, "nota.docx"),
    ],
)
def test_tipo_de_arquivo_nao_aceito_retorna_400_e_nao_cria_nada(ambiente, conteudo, nome):
    resposta = enviar(conteudo=conteudo, nome=nome)

    assert resposta.status_code == 400
    assert "Tipo de arquivo não aceito" in resposta.json()["detail"]
    assert nada_foi_criado(ambiente)


def test_arquivo_maior_que_5mb_retorna_413_e_nao_cria_nada(ambiente):
    resposta = enviar(conteudo=JPEG + b"\x00" * TAMANHO_MAXIMO_BYTES)

    assert resposta.status_code == 413
    assert nada_foi_criado(ambiente)


def test_arquivo_exatamente_no_limite_de_5mb_e_aceito():
    no_limite = JPEG + b"\x00" * (TAMANHO_MAXIMO_BYTES - len(JPEG))

    assert enviar(conteudo=no_limite).status_code == 201


# --- Dados da despesa -------------------------------------------------------


@pytest.mark.parametrize(
    "campos, trecho_da_mensagem",
    [
        ({"valor": "0"}, "maior que zero"),
        ({"valor": "-10"}, "maior que zero"),
        ({"valor": "nan"}, "maior que zero"),
        ({"categoria": "aluguel"}, "Categoria não pertence ao orçamento"),
        ({"data_despesa": "2025-12-31"}, "fora da vigência"),
        ({"descricao": "   "}, "Descrição obrigatória"),
    ],
)
def test_dados_invalidos_retornam_400_sem_enviar_arquivo(ambiente, campos, trecho_da_mensagem):
    resposta = enviar(**campos)

    assert resposta.status_code == 400
    assert trecho_da_mensagem in resposta.json()["detail"]
    assert nada_foi_criado(ambiente)


@pytest.mark.parametrize("campo", ["orcamento_id", "valor", "descricao", "categoria", "data_despesa"])
def test_campo_obrigatorio_ausente_retorna_422(ambiente, campo):
    corpo = dados()
    del corpo[campo]

    resposta = client.post(
        "/lancamentos",
        data=corpo,
        files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
        headers=AUTH,
    )

    assert resposta.status_code == 422
    assert nada_foi_criado(ambiente)


def test_orcamento_inexistente_retorna_404_sem_enviar_arquivo(ambiente):
    resposta = enviar(orcamento_id="nao-existe")

    assert resposta.status_code == 404
    assert ambiente.objetos == {}


# --- Autenticação e falhas --------------------------------------------------


def test_sem_token_retorna_401_e_nao_cria_nada(ambiente):
    resposta = enviar(headers={})

    assert resposta.status_code == 401
    assert nada_foi_criado(ambiente)


def test_falha_ao_salvar_no_bucket_retorna_503_e_nao_cria_lancamento(ambiente):
    def falhar(*_args, **_kwargs):
        raise RuntimeError("R2 fora do ar")

    ambiente.salvar = falhar

    resposta = enviar()

    assert resposta.status_code == 503
    assert orcamento().lancamentos == []


def test_comprovante_enviado_como_texto_e_nao_como_arquivo_e_recusado(ambiente):
    resposta = client.post(
        "/lancamentos",
        data={**dados(), "comprovante": "nao-sou-um-arquivo"},
        headers=AUTH,
    )

    assert resposta.status_code in (400, 422)
    assert nada_foi_criado(ambiente)
