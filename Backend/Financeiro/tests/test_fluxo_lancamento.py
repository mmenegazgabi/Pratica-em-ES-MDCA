"""T-14 · US-03 — Testes de QA do endpoint de criação de lançamento.

Cada bloco corresponde a um critério de aceitação da T-14. O corpo enviado é
igual ao que o formulário do celular (T-13) monta em `montarFormData`:
valor com ponto e 2 casas, data AAAA-MM-DD e o arquivo em `comprovante`.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.main import app
from Financeiro.orcamento import Orcamento, StatusLancamento
from Financeiro.routers.comprovantes import obter_armazenamento
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"
EDUCADOR = {"Authorization": f"Bearer {TOKEN}", "X-Papel-Usuario": "educador"}
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
CAMPOS_OBRIGATORIOS = ["orcamento_id", "valor", "descricao", "categoria", "data_despesa"]

client = TestClient(app)


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    _orcamentos.clear()
    _orcamentos.append(
        Orcamento(
            id="orc-semear",
            projeto_id="semear-contraturno",
            valor_total=15000,
            data_inicio=date(2026, 1, 1),
            data_fim=date(2026, 12, 31),
            categorias_despesa=["alimentacao", "transporte"],
        )
    )
    armazenamento = ArmazenamentoEmMemoria()
    app.dependency_overrides[obter_armazenamento] = lambda: armazenamento
    yield armazenamento
    app.dependency_overrides.clear()
    _orcamentos.clear()


def corpo_do_formulario(**trocas):
    """Campos exatamente como o formulário da T-13 envia."""
    corpo = {
        "orcamento_id": "orc-semear",
        "valor": "486.90",
        "descricao": "Lanche da oficina",
        "categoria": "alimentacao",
        "data_despesa": "2026-10-12",
    }
    corpo.update(trocas)
    return corpo


def enviar(dados, comprovante=("nota.jpg", JPEG, "image/jpeg")):
    arquivos = {"comprovante": comprovante} if comprovante else None
    return client.post("/lancamentos", data=dados, files=arquivos, headers=EDUCADOR)


def nada_foi_criado(armazenamento):
    return _orcamentos[0].lancamentos == [] and armazenamento.objetos == {}


# --- Critério 1: sem campo obrigatório → bloqueia ----------------------------


@pytest.mark.parametrize("campo", CAMPOS_OBRIGATORIOS)
def test_sem_campo_obrigatorio_bloqueia_e_nao_cria_nada(ambiente, campo):
    dados = corpo_do_formulario()
    del dados[campo]

    resposta = enviar(dados)

    assert resposta.status_code == 422
    assert any(campo in erro["loc"] for erro in resposta.json()["detail"])
    assert nada_foi_criado(ambiente)


@pytest.mark.parametrize(
    "campo, valor_vazio",
    [("descricao", "   "), ("valor", "0"), ("categoria", "")],
)
def test_campo_obrigatorio_vazio_bloqueia_e_nao_cria_nada(ambiente, campo, valor_vazio):
    resposta = enviar(corpo_do_formulario(**{campo: valor_vazio}))

    assert resposta.status_code in (400, 422)
    assert nada_foi_criado(ambiente)


# --- Critério 2: sem comprovante → bloqueia (regra de negócio) ---------------


def test_sem_comprovante_bloqueia_com_mensagem_da_regra(ambiente):
    resposta = enviar(corpo_do_formulario(), comprovante=None)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Comprovante obrigatório."
    assert nada_foi_criado(ambiente)


def test_comprovante_vazio_conta_como_sem_comprovante(ambiente):
    resposta = enviar(corpo_do_formulario(), comprovante=("nota.jpg", b"", "image/jpeg"))

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Comprovante obrigatório."
    assert nada_foi_criado(ambiente)


def test_sem_comprovante_e_sem_outros_campos_aponta_os_campos(ambiente):
    resposta = client.post("/lancamentos", data={}, headers=EDUCADOR)

    assert resposta.status_code == 422
    assert nada_foi_criado(ambiente)


# --- Critério 3: envio válido completo → lançamento pendente -----------------


def test_envio_valido_completo_cria_lancamento_pendente(ambiente):
    resposta = enviar(corpo_do_formulario())

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["status"] == "pendente"
    assert corpo["status_descricao"] == "Pendente de aprovação"
    assert corpo["valor"] == 486.9
    assert corpo["categoria"] == "alimentacao"
    assert corpo["data_despesa"] == "2026-10-12"

    [lancamento] = _orcamentos[0].lancamentos
    assert lancamento.status == StatusLancamento.PENDENTE
    assert ambiente.objetos[corpo["comprovante"]["chave"]].conteudo == JPEG


def test_lancamento_criado_aparece_pendente_na_consulta_e_nao_mexe_no_saldo():
    criado = enviar(corpo_do_formulario()).json()

    consulta = client.get(f"/lancamentos/{criado['id']}", headers=EDUCADOR)
    orcamento = client.get("/orcamentos/orc-semear").json()

    assert consulta.status_code == 200
    assert consulta.json()["status_descricao"] == "Pendente de aprovação"
    assert consulta.json()["motivo_rejeicao"] is None
    assert orcamento["saldo"] == 15000
    assert orcamento["realizado"] == 0


def test_dois_envios_validos_criam_dois_lancamentos_independentes():
    primeiro = enviar(corpo_do_formulario(valor="10.00")).json()
    segundo = enviar(corpo_do_formulario(valor="20.00")).json()

    assert primeiro["id"] != segundo["id"]
    assert primeiro["comprovante"]["chave"] != segundo["comprovante"]["chave"]
    assert len(_orcamentos[0].lancamentos) == 2
