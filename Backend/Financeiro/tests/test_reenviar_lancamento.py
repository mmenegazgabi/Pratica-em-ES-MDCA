"""Reenvio de despesa rejeitada depois de corrigida."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.main import app
from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
from Financeiro.routers.comprovantes import obter_armazenamento
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

client = TestClient(app)


def auth(usuario="marcos", papel="educador"):
    return {
        "Authorization": f"Bearer {TOKEN}",
        "X-Papel-Usuario": papel,
        "X-Usuario-Id": usuario,
    }


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    _orcamentos.clear()
    armazenamento = ArmazenamentoEmMemoria()
    app.dependency_overrides[obter_armazenamento] = lambda: armazenamento
    yield armazenamento
    app.dependency_overrides.clear()
    _orcamentos.clear()


def criar(status=StatusLancamento.REJEITADO, motivo="Nota ilegível"):
    lancamento = Lancamento(
        valor=50,
        status=status,
        descricao="Lanche",
        categoria="materiais",
        data_despesa=date(2026, 10, 10),
        comprovante_chave="comprovantes/antigo.jpg",
        motivo_rejeicao=motivo if status == StatusLancamento.REJEITADO else None,
        autor_id="marcos",
    )
    _orcamentos.append(
        Orcamento(
            id="orcamento-1",
            projeto_id="projeto-1",
            valor_total=1000,
            data_inicio=date(2026, 1, 1),
            data_fim=date(2026, 12, 31),
            categorias_despesa=["materiais", "transporte"],
            lancamentos=[lancamento],
        )
    )
    return lancamento


def reenviar(lancamento, usuario="marcos", foto=None, **overrides):
    dados = {
        "valor": "42.50",
        "descricao": "Lanche corrigido",
        "categoria": "transporte",
        "data_despesa": "2026-10-11",
    }
    dados.update(overrides)
    arquivos = {"comprovante": ("nova.png", foto, "image/png")} if foto else None
    return client.patch(
        f"/lancamentos/{lancamento.id}/reenviar",
        data=dados,
        files=arquivos,
        headers=auth(usuario),
    )


def test_reenviar_rejeitada_volta_para_pendente_e_guarda_motivo_anterior():
    lancamento = criar()
    anterior = lancamento.criado_em
    resposta = reenviar(lancamento)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "pendente"
    assert corpo["motivo_rejeicao"] is None
    assert corpo["motivos_rejeicao_anteriores"] == ["Nota ilegível"]
    assert corpo["valor"] == 42.5
    assert corpo["descricao"] == "Lanche corrigido"
    assert corpo["categoria"] == "transporte"
    assert corpo["data_despesa"] == "2026-10-11"
    assert lancamento.status == StatusLancamento.PENDENTE
    assert lancamento.criado_em > anterior


def test_reenviar_sem_foto_mantem_comprovante():
    lancamento = criar()
    assert reenviar(lancamento).status_code == 200
    assert lancamento.comprovante_chave == "comprovantes/antigo.jpg"


def test_reenviar_com_foto_troca_comprovante():
    lancamento = criar()
    resposta = reenviar(lancamento, foto=PNG)
    assert resposta.status_code == 200
    assert lancamento.comprovante_chave != "comprovantes/antigo.jpg"
    assert resposta.json()["comprovante_url"] == f"/{lancamento.comprovante_chave}"


@pytest.mark.parametrize(
    "status", [StatusLancamento.PENDENTE, StatusLancamento.APROVADO]
)
def test_reenviar_pendente_ou_aprovada_retorna_409_sem_mudar(status, ambiente):
    lancamento = criar(status)
    resposta = reenviar(lancamento, foto=PNG)
    assert resposta.status_code == 409
    assert resposta.json()["detail"] == "Só despesas rejeitadas podem ser reenviadas"
    assert lancamento.status == status
    assert lancamento.valor == 50
    assert lancamento.motivos_rejeicao_anteriores == []
    assert lancamento.comprovante_chave == "comprovantes/antigo.jpg"


def test_reenviar_de_outro_autor_retorna_404():
    lancamento = criar()
    resposta = reenviar(lancamento, usuario="outra")
    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Lançamento não encontrado"
    assert lancamento.status == StatusLancamento.REJEITADO


def test_reenviar_com_valor_invalido_retorna_400_e_continua_rejeitada():
    lancamento = criar()
    resposta = reenviar(lancamento, valor="0", foto=PNG)
    assert resposta.status_code == 400
    assert lancamento.status == StatusLancamento.REJEITADO
    assert lancamento.motivo_rejeicao == "Nota ilegível"
    assert lancamento.valor == 50
    assert lancamento.comprovante_chave == "comprovantes/antigo.jpg"


def test_rejeitar_de_novo_depois_do_reenvio_acumula_motivos():
    lancamento = criar()
    assert reenviar(lancamento).status_code == 200
    rejeicao = client.patch(
        f"/lancamentos/{lancamento.id}/rejeitar",
        json={"motivo": "Valor diferente da nota"},
        headers=auth(papel="coordenacao"),
    )
    assert rejeicao.status_code == 200
    assert reenviar(lancamento).status_code == 200
    assert lancamento.motivos_rejeicao_anteriores == [
        "Nota ilegível",
        "Valor diferente da nota",
    ]
