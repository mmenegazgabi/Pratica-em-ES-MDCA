"""T-34 · US-08: auditoria do Financeiro na trilha única (plano de integração, Trabalho 4).

"Pronto quando": aprovar um lançamento gera uma linha com usuário, horário e ação, que
aparece na rota que a tela Auditoria vai usar. Aqui também: cada ação sensível gera um
registro na mesma transação (ação que falha não deixa registro), o acesso negado fica
registrado, e só Coordenação e Direção leem a trilha do Financeiro.

Precisa do PostgreSQL descartável (``TEST_DATABASE_URL``), como os demais testes de banco.
"""

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from datetime import datetime, timezone

from Acesso import sessoes
from Financeiro.main import app

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
CODIGO = "token-de-teste-banco"

client = TestClient(app)


def tela(papel, usuario):
    """Como as telas do Financeiro chamam hoje: código de acesso, papel e usuário."""
    return {"Authorization": f"Bearer {CODIGO}", "X-Papel-Usuario": papel, "X-Usuario-Id": usuario}


COORD = tela("coordenacao", "luana")
EDUCADOR = tela("educador", "marcos")
VOLUNTARIO = tela("voluntario_financeiro", "vera")
DIRECAO = tela("direcao", "jane")


def eventos(motor, **filtro):
    onde = " AND ".join(f"{k} = :{k}" for k in filtro) or "true"
    with motor.connect() as c:
        return [
            dict(l._mapping)
            for l in c.execute(
                sa.text(
                    "SELECT usuario_id, modulo, acao, alvo_tipo, alvo_id, descricao, detalhes, ocorrido_em "
                    f"FROM log_auditoria WHERE modulo = 'financeiro' AND {onde} ORDER BY id"
                ),
                filtro,
            )
        ]


def criar_orcamento(valor_total=1000):
    r = client.post("/orcamentos", headers=COORD, json={
        "projeto_id": "p-1", "valor_total": valor_total, "data_inicio": "2026-01-01", "data_fim": "2026-12-31",
        "categorias": [{"nome": "Materiais", "valor_orcado": 600}]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def lancar(orcamento_id, valor="180.00", headers=EDUCADOR):
    r = client.post("/lancamentos", headers=headers, files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
                    data={"orcamento_id": orcamento_id, "valor": valor, "descricao": "Tinta",
                          "categoria": "Materiais", "data_despesa": "2026-05-15"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --- Pronto quando ------------------------------------------------------------------


def test_aprovar_gera_linha_com_usuario_horario_e_acao_que_aparece_na_auditoria(banco_financeiro):
    lancamento = lancar(criar_orcamento())

    assert client.patch(f"/lancamentos/{lancamento}/aprovar", headers=COORD).status_code == 200

    [linha] = eventos(banco_financeiro, acao="aprovar_lancamento")
    assert (linha["usuario_id"], linha["alvo_tipo"], linha["alvo_id"]) == ("luana", "lancamento", lancamento)
    assert linha["ocorrido_em"] is not None
    assert linha["descricao"] == "Materiais · R$ 180,00 · Semear"
    assert linha["detalhes"]["saldo_orcamento"] == 820.0

    tela_auditoria = client.get("/auditoria", params={"modulo": "financeiro"}, headers=COORD).json()
    primeiro = tela_auditoria["itens"][0]
    assert (primeiro["quem"], primeiro["acao"], primeiro["alvo"], primeiro["codigo"]) == (
        "luana", "Aprovou despesa", "Materiais · R$ 180,00 · Semear", "aprovar_lancamento")
    assert primeiro["quando"]


# --- Cada ação sensível -------------------------------------------------------------


def test_fluxo_completo_registra_cada_acao_na_ordem(banco_financeiro):
    projeto = client.post("/projetos", json={"nome": "Horta comunitária"}, headers=COORD).json()["id"]
    client.patch(f"/projetos/{projeto}/status", json={"status": "encerrado"}, headers=DIRECAO)
    orcamento = criar_orcamento()
    client.patch(f"/orcamentos/{orcamento}", json={"valor_total": 1500}, headers=COORD)
    aprovado = lancar(orcamento)
    client.patch(f"/lancamentos/{aprovado}/aprovar", headers=COORD)
    rejeitado = lancar(orcamento, "64.00")
    client.patch(f"/lancamentos/{rejeitado}/rejeitar", json={"motivo": "Nota ilegível"}, headers=COORD)
    client.patch(f"/lancamentos/{rejeitado}/reenviar", headers=EDUCADOR, data={
        "valor": "64.00", "descricao": "Lanche", "categoria": "Materiais", "data_despesa": "2026-05-16"})
    client.patch(f"/lancamentos/{aprovado}/conciliar", json={"referencia_extrato": "EXT-1024-02"}, headers=VOLUNTARIO)
    client.get("/relatorios/prestacao-contas", headers=DIRECAO, params={
        "projeto_id": "p-1", "data_inicio": "2026-07-01", "data_fim": "2026-09-30", "formato": "xlsx"})

    linhas = eventos(banco_financeiro)
    assert [(l["acao"], l["usuario_id"]) for l in linhas] == [
        ("criar_projeto", "luana"),
        ("encerrar_projeto", "jane"),
        ("criar_orcamento", "luana"),
        ("editar_orcamento", "luana"),
        ("criar_lancamento", "marcos"),
        ("aprovar_lancamento", "luana"),
        ("criar_lancamento", "marcos"),
        ("rejeitar_lancamento", "luana"),
        ("reenviar_lancamento", "marcos"),
        ("conciliar_lancamento", "vera"),
        ("gerar_relatorio", "jane"),
    ]
    por_acao = {l["acao"]: l for l in linhas}
    assert por_acao["criar_projeto"]["descricao"] == "Horta comunitária"
    assert por_acao["editar_orcamento"]["descricao"] == "Semear · valor total R$ 1.500,00"
    assert (por_acao["editar_orcamento"]["detalhes"]["antes"]["valor_total"],
            por_acao["editar_orcamento"]["detalhes"]["depois"]["valor_total"]) == (1000.0, 1500.0)
    assert por_acao["rejeitar_lancamento"]["detalhes"]["motivo"] == "Nota ilegível"
    assert por_acao["conciliar_lancamento"]["descricao"] == "Materiais · R$ 180,00 · Semear · EXT-1024-02"
    assert por_acao["gerar_relatorio"]["descricao"] == "Semear · 01/07/2026 a 30/09/2026 · XLSX"


# --- Mesma transação: ação que falha não deixa registro --------------------------------


def test_acao_que_falha_nao_deixa_registro(banco_financeiro):
    orcamento = criar_orcamento()
    lancamento = lancar(orcamento)
    antes = len(eventos(banco_financeiro))

    client.patch(f"/lancamentos/{lancamento}/rejeitar", json={"motivo": ""}, headers=COORD)  # 400
    client.patch(f"/orcamentos/{orcamento}", json={"valor_total": 10}, headers=COORD)  # 400 (soma das categorias)
    assert client.patch(f"/lancamentos/{lancamento}/aprovar", headers=COORD).status_code == 200
    assert client.patch(f"/lancamentos/{lancamento}/aprovar", headers=COORD).status_code == 409

    novos = [l["acao"] for l in eventos(banco_financeiro)][antes:]
    assert novos == ["aprovar_lancamento"]


def test_conciliar_de_novo_com_a_mesma_referencia_nao_gera_outro_registro(banco_financeiro):
    lancamento = lancar(criar_orcamento())
    client.patch(f"/lancamentos/{lancamento}/aprovar", headers=COORD)
    for _ in range(3):
        r = client.patch(f"/lancamentos/{lancamento}/conciliar", json={"referencia_extrato": "ext-1"}, headers=VOLUNTARIO)
        assert r.status_code == 200

    assert len(eventos(banco_financeiro, acao="conciliar_lancamento")) == 1


def test_registro_some_junto_quando_a_transacao_e_desfeita(banco_financeiro, monkeypatch):
    """Se algo falha depois do registro e antes do commit, nem a ação nem o registro ficam."""
    from Financeiro.persistencia import RepositorioBanco

    lancamento = lancar(criar_orcamento())

    def falha(self):
        raise RuntimeError("queda no meio da requisição")

    monkeypatch.setattr(RepositorioBanco, "confirmar", falha)
    with pytest.raises(RuntimeError):
        client.patch(f"/lancamentos/{lancamento}/aprovar", headers=COORD)
    monkeypatch.undo()

    assert eventos(banco_financeiro, acao="aprovar_lancamento") == []
    with banco_financeiro.connect() as c:
        status = c.execute(sa.text("SELECT status FROM lancamentos WHERE id = :i"), {"i": lancamento}).scalar_one()
    assert status == "pendente"


# --- Acesso negado ----------------------------------------------------------------------


def test_acesso_negado_fica_na_trilha_com_quem_tentou_e_a_rota(banco_financeiro):
    lancamento = lancar(criar_orcamento())

    assert client.patch(f"/lancamentos/{lancamento}/aprovar", headers=VOLUNTARIO).status_code == 403

    [linha] = eventos(banco_financeiro, acao="acesso_negado")
    assert linha["usuario_id"] == "vera"
    assert linha["alvo_id"] == f"PATCH /lancamentos/{lancamento}/aprovar"
    assert linha["detalhes"]["papeis"] == ["voluntario_financeiro"]


def test_acesso_negado_pelo_login_registra_o_usuario_da_sessao(banco_financeiro):
    with banco_financeiro.begin() as c:
        c.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-2', 'Oficina')"))
        c.execute(sa.text("INSERT INTO usuarios (id, nome) VALUES ('marcos', 'Marcos Vieira')"))
        c.execute(sa.text("INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) "
                          "VALUES ('v-1', 'marcos', 'p-2', 'educador', '2025-01-01')"))
    with banco_financeiro.begin() as c:
        token, _ = sessoes.criar(c, "marcos", False, datetime.now(timezone.utc))

    resposta = client.get("/orcamentos/projeto/p-1", headers={"Authorization": f"Bearer {token}"})

    assert resposta.status_code == 403
    [linha] = eventos(banco_financeiro, acao="acesso_negado")
    assert (linha["usuario_id"], linha["alvo_id"]) == ("marcos", "GET /orcamentos/projeto/p-1")
    assert linha["detalhes"]["login"] is True
    # Na rota da tela, aparece o nome da conta.
    item = client.get("/auditoria", headers=COORD).json()["itens"][0]
    assert (item["quem"], item["acao"]) == ("Marcos Vieira", "Acesso negado")


# --- Quem lê a trilha ---------------------------------------------------------------------


@pytest.mark.parametrize("headers, status", [(COORD, 200), (DIRECAO, 200), (EDUCADOR, 403), (VOLUNTARIO, 403)])
def test_so_coordenacao_e_direcao_leem_a_auditoria(banco_financeiro, headers, status):
    assert client.get("/auditoria", params={"modulo": "financeiro"}, headers=headers).status_code == status


def test_auditoria_sem_login_responde_401(banco_financeiro):
    assert client.get("/auditoria").status_code == 401


def test_auditoria_do_financeiro_nao_mostra_eventos_da_gestao(banco_financeiro):
    with banco_financeiro.begin() as c:
        c.execute(sa.text("INSERT INTO log_auditoria (usuario_id, modulo, acao) VALUES ('ana', 'gestao', 'consulta_pessoa')"))
    criar_orcamento()

    itens = client.get("/auditoria", headers=COORD).json()["itens"]

    assert [i["codigo"] for i in itens] == ["criar_orcamento"]
    assert client.get("/auditoria", params={"modulo": "gestao"}, headers=COORD).status_code == 422


def test_filtros_e_paginas_da_auditoria(banco_financeiro):
    orcamento = criar_orcamento()
    for valor in ("10.00", "20.00", "30.00"):
        lancar(orcamento, valor)

    so_lancamentos = client.get("/auditoria", params={"acao": "criar_lancamento"}, headers=COORD).json()
    assert so_lancamentos["total"] == 3
    assert [i["alvo"] for i in so_lancamentos["itens"]] == [
        "Materiais · R$ 30,00 · Semear", "Materiais · R$ 20,00 · Semear", "Materiais · R$ 10,00 · Semear"]
    pagina_2 = client.get("/auditoria", params={"tamanho": 2, "pagina": 2}, headers=COORD).json()
    assert (pagina_2["total"], len(pagina_2["itens"])) == (4, 2)
    assert client.get("/auditoria", params={"usuario_id": "luana"}, headers=COORD).json()["total"] == 1
    assert client.get("/auditoria", params={"desde": "2099-01-01"}, headers=COORD).json()["total"] == 0
    assert client.get("/auditoria", params={"desde": "2026-02-01", "ate": "2026-01-01"}, headers=COORD).status_code == 422


def test_trilha_e_so_de_leitura(banco_financeiro):
    criar_orcamento()

    # Nenhuma rota altera ou apaga a trilha...
    assert client.delete("/auditoria", headers=COORD).status_code == 405
    # ...e o banco também recusa (trigger da T-32).
    with banco_financeiro.connect() as c:
        with pytest.raises(sa.exc.DBAPIError):
            c.execute(sa.text("DELETE FROM log_auditoria"))
