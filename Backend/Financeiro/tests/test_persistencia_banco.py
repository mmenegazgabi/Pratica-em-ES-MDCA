import pytest
"""Persistência do Financeiro no PostgreSQL.

Com ``DATABASE_URL`` as rotas do Financeiro gravam e leem das tabelas das migrations
(``projetos``, ``orcamentos``, ``orcamento_categorias``, ``lancamentos``,
``notificacoes``, ``rascunhos_lancamento``). Estes testes passam pela API, do jeito que o
frontend chama, e conferem direto no banco que o dado ficou lá, e que a API devolve o
mesmo dado depois que a memória do processo é esvaziada (o equivalente a reiniciar).

Precisam de um PostgreSQL descartável em ``TEST_DATABASE_URL`` (fixture
``banco_financeiro`` em ``conftest.py``); sem ele, são pulados localmente. No CI rodam nos
jobs do Financeiro e de infraestrutura, que sobem o banco.
"""

from concurrent.futures import ThreadPoolExecutor

import sqlalchemy as sa
from fastapi.testclient import TestClient

from Financeiro.main import app

from Financeiro.notificacoes import caixa_de_notificacoes
from Financeiro.projetos import _projetos
from Financeiro.rascunhos import caixa_de_rascunhos
from Financeiro.routers.orcamentos import _orcamentos

# Mesmo token da fixture banco_financeiro (conftest.py).
TOKEN = "token-de-teste-banco"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

client = TestClient(app)

# As rotas de orçamento passaram a exigir login (T-33): a tela manda o código de
# acesso e o papel em toda chamada.
LEITURA_ORCAMENTO = {"Authorization": f"Bearer {TOKEN}", "X-Papel-Usuario": "coordenacao"}


@pytest.fixture(autouse=True)
def _codigo_de_acesso(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)


def _esvaziar_memoria() -> None:
    """O equivalente a reiniciar a API: some tudo o que estava só no processo."""
    _projetos.clear()
    _orcamentos.clear()
    caixa_de_notificacoes.limpar()
    caixa_de_rascunhos.limpar()


def como(papel, usuario=None):
    headers = {"Authorization": f"Bearer {TOKEN}", "X-Papel-Usuario": papel}
    if usuario:
        headers["X-Usuario-Id"] = usuario
    return headers


COORDENACAO = como("coordenacao", "luana")
EDUCADOR = como("educador", "marcos")
FINANCEIRO = como("voluntario_financeiro", "vera")


def consulta(motor, sql, **parametros):
    with motor.connect() as conexao:
        return conexao.execute(sa.text(sql), parametros).all()


def criar_orcamento(projeto_id="p-1", valor_total=1000, **extra):
    corpo = {
        "projeto_id": projeto_id,
        "valor_total": valor_total,
        "data_inicio": "2026-01-01",
        "data_fim": "2026-12-31",
        "categorias": [{"nome": "materiais", "valor_orcado": 600}, {"nome": "transporte", "valor_orcado": 300}],
        **extra,
    }
    resposta = client.post("/orcamentos", json=corpo, headers=COORDENACAO)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def lancar(orcamento_id, valor="100.00", categoria="materiais", headers=EDUCADOR):
    resposta = client.post(
        "/lancamentos",
        data={
            "orcamento_id": orcamento_id,
            "valor": valor,
            "descricao": "Tinta e papel",
            "categoria": categoria,
            "data_despesa": "2026-05-15",
        },
        files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
        headers=headers,
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


# --- Projetos: o cadastro é o da Gestão ---------------------------------------


def test_programa_da_gestao_aparece_como_projeto_e_nome_repetido_e_recusado(banco_financeiro):
    projetos = client.get("/projetos", headers=COORDENACAO).json()
    assert [(p["id"], p["nome"], p["status"]) for p in projetos] == [("p-1", "Semear", "ativo")]

    assert client.post("/projetos", json={"nome": "semear"}, headers=COORDENACAO).status_code == 409


def test_projeto_criado_no_financeiro_fica_na_tabela_projetos(banco_financeiro):
    criado = client.post("/projetos", json={"nome": "Oficina de Arte"}, headers=COORDENACAO).json()
    encerrado = client.patch(
        f"/projetos/{criado['id']}/status", json={"status": "encerrado"}, headers=COORDENACAO
    )

    assert encerrado.status_code == 200
    assert consulta(banco_financeiro, "SELECT nome, status FROM projetos WHERE id = :id", id=criado["id"]) == [
        ("Oficina de Arte", "encerrado")
    ]


# --- Orçamentos --------------------------------------------------------------


def test_orcamento_e_valores_por_categoria_ficam_gravados(banco_financeiro):
    orcamento_id = criar_orcamento()

    [linha] = consulta(
        banco_financeiro,
        "SELECT projeto_id, valor_total, periodo_inicio, categorias FROM orcamentos WHERE id = :id",
        id=orcamento_id,
    )
    assert (linha.projeto_id, float(linha.valor_total), linha.categorias) == ("p-1", 1000.0, ["materiais", "transporte"])
    categorias = consulta(
        banco_financeiro,
        "SELECT nome, valor_orcado FROM orcamento_categorias WHERE orcamento_id = :id ORDER BY nome",
        id=orcamento_id,
    )
    assert [(c.nome, float(c.valor_orcado)) for c in categorias] == [("materiais", 600.0), ("transporte", 300.0)]

    _esvaziar_memoria()
    detalhe = client.get(f"/orcamentos/{orcamento_id}", headers=LEITURA_ORCAMENTO).json()
    assert (detalhe["projeto_nome"], detalhe["saldo"]) == ("Semear", 1000.0)
    assert [(c["nome"], c["valor_orcado"]) for c in detalhe["categorias"]] == [("materiais", 600.0), ("transporte", 300.0)]


def test_edicao_do_orcamento_fica_gravada(banco_financeiro):
    orcamento_id = criar_orcamento()

    resposta = client.patch(
        f"/orcamentos/{orcamento_id}",
        json={"valor_total": 1500, "categorias": [{"nome": "materiais", "valor_orcado": 900}]},
        headers=COORDENACAO,
    )

    assert resposta.status_code == 200, resposta.text
    detalhe = client.get(f"/orcamentos/{orcamento_id}", headers=LEITURA_ORCAMENTO).json()
    assert (detalhe["valor_total"], detalhe["categorias_despesa"]) == (1500.0, ["materiais"])
    assert consulta(banco_financeiro, "SELECT nome FROM orcamento_categorias") == [("materiais",)]


def test_edicao_invalida_nao_grava_nada(banco_financeiro):
    orcamento_id = criar_orcamento()

    resposta = client.patch(
        f"/orcamentos/{orcamento_id}",
        json={"categorias": [{"nome": "materiais", "valor_orcado": 5000}]},
        headers=COORDENACAO,
    )

    assert resposta.status_code == 400
    assert [float(v) for (v,) in consulta(banco_financeiro, "SELECT valor_orcado FROM orcamento_categorias ORDER BY nome")] == [
        600.0,
        300.0,
    ]


def test_orcamento_para_projeto_inexistente_e_recusado_sem_gravar(banco_financeiro):
    resposta = client.post(
        "/orcamentos",
        json={
            "projeto_id": "nao-existe",
            "valor_total": 10,
            "data_inicio": "2026-01-01",
            "data_fim": "2026-12-31",
            "categorias_despesa": ["x"],
        },
        headers=COORDENACAO,
    )

    assert resposta.status_code == 400
    assert consulta(banco_financeiro, "SELECT id FROM orcamentos") == []


# --- Lançamentos: aprovação, notificação, rejeição, reenvio, conciliação ------


def test_fluxo_completo_fica_no_banco_e_sobrevive_a_reinicio(banco_financeiro):
    orcamento_id = criar_orcamento()
    aprovado = lancar(orcamento_id, valor="250.40")
    rejeitado = lancar(orcamento_id, valor="80", categoria="transporte")

    assert client.patch(f"/lancamentos/{aprovado['id']}/aprovar", headers=COORDENACAO).status_code == 200
    rejeicao = client.patch(
        f"/lancamentos/{rejeitado['id']}/rejeitar", json={"motivo": "Nota ilegível"}, headers=COORDENACAO
    )
    assert rejeicao.status_code == 200
    reenvio = client.patch(
        f"/lancamentos/{rejeitado['id']}/reenviar",
        data={"valor": "80", "descricao": "Passagens", "categoria": "transporte", "data_despesa": "2026-05-20"},
        headers=EDUCADOR,
    )
    assert reenvio.status_code == 200, reenvio.text
    conciliado = client.patch(
        f"/lancamentos/{aprovado['id']}/conciliar", json={"referencia_extrato": "ext-42"}, headers=FINANCEIRO
    )
    assert conciliado.status_code == 200

    # No banco.
    linhas = {
        l.id: l
        for l in consulta(
            banco_financeiro,
            "SELECT id, projeto_id, status, valor, aprovado_em, conciliado, item_extrato_ref, "
            "motivos_rejeicao_anteriores, comprovante_url, autor_id FROM lancamentos",
        )
    }
    a, r = linhas[aprovado["id"]], linhas[rejeitado["id"]]
    assert (a.projeto_id, a.status, float(a.valor), a.conciliado, a.item_extrato_ref) == ("p-1", "aprovado", 250.4, True, "ext-42")
    assert a.aprovado_em is not None and a.autor_id == "marcos"
    assert a.comprovante_url == aprovado["comprovante"]["url"]
    assert (r.status, r.motivos_rejeicao_anteriores) == ("pendente", ["Nota ilegível"])
    tipos = [t for (t,) in consulta(banco_financeiro, "SELECT tipo FROM notificacoes ORDER BY tipo")]
    assert tipos == ["lancamento_aprovado", "lancamento_rejeitado"]

    # Depois de "reiniciar" (memória vazia), a API devolve o mesmo estado.
    _esvaziar_memoria()
    orcamento = client.get(f"/orcamentos/{orcamento_id}", headers=LEITURA_ORCAMENTO).json()
    assert (orcamento["saldo"], orcamento["realizado"]) == (749.6, 250.4)
    fila = client.get("/lancamentos", params={"status": "pendente"}, headers=COORDENACAO).json()
    assert [(l["id"], l["descricao"]) for l in fila] == [(rejeitado["id"], "Passagens")]
    detalhe = client.get(f"/lancamentos/{rejeitado['id']}", headers=EDUCADOR).json()
    assert detalhe["motivos_rejeicao_anteriores"] == ["Nota ilegível"]
    notificacoes = client.get("/notificacoes", headers=EDUCADOR).json()
    assert len(notificacoes) == 2
    lida = client.patch(f"/notificacoes/{notificacoes[0]['id']}/lida", headers=EDUCADOR)
    assert lida.status_code == 200
    assert len(client.get("/notificacoes", params={"nao_lidas": True}, headers=EDUCADOR).json()) == 1


def test_aprovar_duas_vezes_ao_mesmo_tempo_debita_uma_vez(banco_financeiro):
    orcamento_id = criar_orcamento()
    lancamento = lancar(orcamento_id, valor="100")

    with ThreadPoolExecutor(max_workers=4) as executor:
        respostas = list(
            executor.map(
                lambda _: client.patch(f"/lancamentos/{lancamento['id']}/aprovar", headers=COORDENACAO), range(4)
            )
        )

    assert sorted(r.status_code for r in respostas) == [200, 409, 409, 409]
    assert client.get(f"/orcamentos/{orcamento_id}", headers=LEITURA_ORCAMENTO).json()["saldo"] == 900.0
    assert len(consulta(banco_financeiro, "SELECT id FROM notificacoes")) == 1


def test_lancamento_com_dado_invalido_nao_grava(banco_financeiro):
    orcamento_id = criar_orcamento()

    resposta = client.post(
        "/lancamentos",
        data={
            "orcamento_id": orcamento_id,
            "valor": "10",
            "descricao": "x",
            "categoria": "nao-existe",
            "data_despesa": "2026-05-15",
        },
        files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
        headers=EDUCADOR,
    )

    assert resposta.status_code == 400
    assert consulta(banco_financeiro, "SELECT id FROM lancamentos") == []


# --- Rascunhos ----------------------------------------------------------------


def test_rascunho_fica_gravado_e_completar_vira_lancamento(banco_financeiro):
    orcamento_id = criar_orcamento()
    rascunho = client.post(
        "/rascunhos", files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")}, headers=EDUCADOR
    ).json()

    _esvaziar_memoria()
    assert [r["id"] for r in client.get("/rascunhos", headers=EDUCADOR).json()] == [rascunho["id"]]
    assert client.get("/rascunhos", headers=como("educador", "outro")).json() == []

    completado = client.post(
        f"/rascunhos/{rascunho['id']}/completar",
        data={
            "orcamento_id": orcamento_id,
            "valor": "42",
            "descricao": "Lanche",
            "categoria": "materiais",
            "data_despesa": "2026-06-01",
        },
        headers=EDUCADOR,
    )

    assert completado.status_code == 201, completado.text
    assert consulta(banco_financeiro, "SELECT id FROM rascunhos_lancamento") == []
    [linha] = consulta(banco_financeiro, "SELECT status, comprovante_url FROM lancamentos")
    assert (linha.status, linha.comprovante_url) == ("pendente", rascunho["comprovante_url"])


# --- Leituras que juntam tudo: dashboard e relatório ---------------------------


def test_dashboard_e_relatorio_leem_do_banco(banco_financeiro):
    orcamento_id = criar_orcamento()
    lancamento = lancar(orcamento_id, valor="300")
    client.patch(f"/lancamentos/{lancamento['id']}/aprovar", headers=COORDENACAO)
    _esvaziar_memoria()

    resumo = client.get("/dashboard/projetos", headers=como("direcao")).json()
    assert [(r["projeto_id"], r["orcado"], r["realizado"], r["saldo"]) for r in resumo] == [("p-1", 1000.0, 300.0, 700.0)]

    relatorio = client.get(
        "/relatorios/prestacao-contas",
        params={"projeto_id": "p-1", "data_inicio": "2026-01-01", "data_fim": "2026-12-31", "formato": "xlsx"},
        headers=COORDENACAO,
    )
    assert relatorio.status_code == 200


# --- Banco fora do ar -----------------------------------------------------------


def test_sem_banco_acessivel_responde_503(banco_financeiro, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://ninguem@127.0.0.1:1/mdca_test")

    resposta = client.get("/projetos", headers=COORDENACAO)

    assert resposta.status_code == 503


# --- Trava do orçamento entre conexões (SELECT ... FOR UPDATE) -------------------


def test_segunda_alteracao_espera_a_primeira_terminar(banco_financeiro):
    """Duas instâncias da API alterando o mesmo orçamento: a segunda espera a primeira.

    Determinístico, sem depender de as requisições se sobreporem no tempo: a conexão A
    trava o orçamento e aprova; a B tenta travar o mesmo orçamento e só consegue depois
    do commit de A, já vendo o lançamento aprovado (e por isso não aprova de novo).
    """
    import threading

    from Financeiro.persistencia import RepositorioBanco

    orcamento_id = criar_orcamento(valor_total=1000)
    lancamento_id = lancar(orcamento_id, valor="100")["id"]

    with banco_financeiro.connect() as conexao_a, banco_financeiro.connect() as conexao_b:
        a, b = RepositorioBanco(conexao_a), RepositorioBanco(conexao_b)
        orcamento_a = a.buscar_orcamento(orcamento_id, para_alterar=True)
        lancamento = orcamento_a.aprovar_lancamento(lancamento_id)
        a.salvar_lancamento(orcamento_a, lancamento)

        visto_por_b = {}

        def b_tenta_alterar():
            orcamento_b = b.buscar_orcamento(orcamento_id, para_alterar=True)
            visto_por_b["status"] = orcamento_b.lancamentos[0].status.value
            visto_por_b["saldo"] = orcamento_b.saldo
            b.confirmar()

        tarefa = threading.Thread(target=b_tenta_alterar)
        tarefa.start()
        tarefa.join(timeout=1.0)
        assert tarefa.is_alive(), "B não esperou: o orçamento não estava travado"

        a.confirmar()
        tarefa.join(timeout=10)

    assert visto_por_b == {"status": "aprovado", "saldo": 900.0}


def test_leitura_sem_trava_nao_espera(banco_financeiro):
    """Listar e consultar não travam: a tela continua respondendo durante uma aprovação."""
    import threading

    from Financeiro.persistencia import RepositorioBanco

    orcamento_id = criar_orcamento(valor_total=1000)
    lancar(orcamento_id, valor="100")

    with banco_financeiro.connect() as conexao_a, banco_financeiro.connect() as conexao_b:
        RepositorioBanco(conexao_a).buscar_orcamento(orcamento_id, para_alterar=True)
        lido = {}
        tarefa = threading.Thread(
            target=lambda: lido.setdefault("saldo", RepositorioBanco(conexao_b).buscar_orcamento(orcamento_id).saldo)
        )
        tarefa.start()
        tarefa.join(timeout=5)

        assert not tarefa.is_alive()
        assert lido == {"saldo": 1000.0}
        conexao_a.rollback()


def test_lancamento_espera_a_edicao_do_orcamento_e_respeita_a_categoria_nova(banco_financeiro):
    """A coordenação tira uma categoria enquanto o educador envia a despesa nela.

    O lançamento espera a edição terminar e é recusado (400), em vez de ficar gravado
    numa categoria que o orçamento não tem mais.
    """
    import threading

    from Financeiro.persistencia import RepositorioBanco

    orcamento_id = criar_orcamento(valor_total=1000)
    resposta = {}

    with banco_financeiro.connect() as conexao:
        coordenacao = RepositorioBanco(conexao)
        orcamento = coordenacao.buscar_orcamento(orcamento_id, para_alterar=True)
        orcamento.editar(categorias_despesa=["transporte"])
        coordenacao.salvar_orcamento(orcamento)

        tarefa = threading.Thread(target=lambda: resposta.setdefault("r", lancar_sem_conferir(orcamento_id, "materiais")))
        tarefa.start()
        tarefa.join(timeout=1.0)
        assert tarefa.is_alive(), "o lançamento não esperou a edição do orçamento"
        coordenacao.confirmar()
        tarefa.join(timeout=10)

    assert resposta["r"].status_code == 400
    assert "Categoria não pertence ao orçamento" in resposta["r"].json()["detail"]
    assert consulta(banco_financeiro, "SELECT id FROM lancamentos") == []


def lancar_sem_conferir(orcamento_id, categoria):
    return client.post(
        "/lancamentos",
        data={
            "orcamento_id": orcamento_id,
            "valor": "10.00",
            "descricao": "Tinta",
            "categoria": categoria,
            "data_despesa": "2026-05-15",
        },
        files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
        headers=EDUCADOR,
    )
