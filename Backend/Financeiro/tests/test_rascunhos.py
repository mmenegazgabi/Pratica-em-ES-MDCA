"""Rascunhos de despesa: foto agora, dados depois."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.main import app
from Financeiro.orcamento import Orcamento
from Financeiro.rascunhos import caixa_de_rascunhos
from Financeiro.routers.comprovantes import obter_armazenamento
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

client = TestClient(app)


def auth(usuario="marcos", papel="educador"):
    cab = {"Authorization": f"Bearer {TOKEN}", "X-Papel-Usuario": papel}
    if usuario:
        cab["X-Usuario-Id"] = usuario
    return cab


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    _orcamentos.clear()
    caixa_de_rascunhos.limpar()
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
    caixa_de_rascunhos.limpar()


def fotografar(usuario="marcos", conteudo=JPEG):
    arquivos = None if conteudo is None else {"comprovante": ("nota.jpg", conteudo, "image/jpeg")}
    return client.post("/rascunhos", files=arquivos, headers=auth(usuario))


def completar(rascunho_id, usuario="marcos", **overrides):
    dados = {
        "orcamento_id": "orcamento-1",
        "valor": "42.50",
        "descricao": "Lanche",
        "categoria": "materiais",
        "data_despesa": "2026-10-10",
    }
    dados.update(overrides)
    return client.post(f"/rascunhos/{rascunho_id}/completar", data=dados, headers=auth(usuario))


def test_criar_rascunho_salva_foto_e_devolve_201(ambiente):
    resposta = fotografar()

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["content_type"] == "image/jpeg"
    assert corpo["nome_original"] == "nota.jpg"
    assert corpo["tamanho"] == len(JPEG)
    assert corpo["comprovante_url"].startswith("/")
    assert corpo["id"] and corpo["criado_em"]
    assert len(ambiente.objetos) == 1


def test_criar_rascunho_sem_foto_retorna_400(ambiente):
    resposta = fotografar(conteudo=None)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Comprovante obrigatório."
    assert caixa_de_rascunhos.do_autor("marcos") == []


def test_criar_rascunho_sem_usuario_retorna_400():
    assert fotografar(usuario=None).status_code == 400


def test_listar_mostra_so_os_do_autor():
    fotografar("marcos")
    fotografar("ana")

    resposta = client.get("/rascunhos", headers=auth("marcos"))

    assert resposta.status_code == 200
    assert len(resposta.json()) == 1


def test_completar_cria_lancamento_pendente_com_mesma_foto():
    rascunho = fotografar().json()

    resposta = completar(rascunho["id"])

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["status"] == "pendente"
    assert corpo["comprovante"]["chave"] == rascunho["comprovante_url"].lstrip("/")
    lancamento = _orcamentos[0].lancamentos[0]
    assert lancamento.autor_id == "marcos"
    assert lancamento.descricao == "Lanche"


def test_completar_remove_o_rascunho():
    rascunho = fotografar().json()
    completar(rascunho["id"])

    assert client.get("/rascunhos", headers=auth("marcos")).json() == []
    assert completar(rascunho["id"]).status_code == 404


def test_completar_rascunho_de_outro_autor_retorna_404_e_mantem():
    rascunho = fotografar("marcos").json()

    resposta = completar(rascunho["id"], usuario="ana")

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Rascunho não encontrado"
    assert len(client.get("/rascunhos", headers=auth("marcos")).json()) == 1
    assert _orcamentos[0].lancamentos == []


def test_completar_com_categoria_invalida_retorna_400_e_mantem():
    rascunho = fotografar().json()

    resposta = completar(rascunho["id"], categoria="inexistente")

    assert resposta.status_code == 400
    assert len(client.get("/rascunhos", headers=auth("marcos")).json()) == 1
    assert _orcamentos[0].lancamentos == []


def test_rascunho_nao_aparece_em_listar_lancamentos_nem_no_saldo():
    fotografar()

    resposta = client.get("/lancamentos", headers=auth("marcos"))

    assert resposta.status_code == 200
    assert resposta.json() == []
    assert _orcamentos[0].saldo == 1000


def test_post_lancamentos_continua_igual():
    resposta = client.post(
        "/lancamentos",
        data={
            "orcamento_id": "orcamento-1",
            "valor": "10",
            "descricao": "Direto",
            "categoria": "materiais",
            "data_despesa": "2026-10-10",
        },
        files={"comprovante": ("n.jpg", JPEG, "image/jpeg")},
        headers=auth(),
    )

    assert resposta.status_code == 201
    assert resposta.json()["status"] == "pendente"
