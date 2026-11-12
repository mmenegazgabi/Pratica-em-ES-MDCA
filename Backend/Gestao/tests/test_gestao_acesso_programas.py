"""T-87 · US-02: acesso por programa nas rotas de programas e plano de ação.

A coordenação é um papel só, dado na conta, e vale para todos os programas; ela não
existe como vínculo de programa.

- consultar o programa, o plano e o painel: equipe ativa do programa, direção, coordenação e
  administração;
- alterar o programa, convênios, vagas e plano de ação (inclusive o realizado): coordenação e
  administração;
- cadastrar um programa novo: coordenação e administração (US-02);
- a lista de programas mostra só os que a pessoa pode consultar.

Toda negação vai para ``log_auditoria`` antes do 403.
"""

import pytest
import sqlalchemy as sa

PROGRAMA_NOVO = {
    "nome": "Aprendiz",
    "identificador": "APRENDIZ",
    "publico": "Jovens de 14 a 24 anos",
    "responsavel": "Ana Martins",
    "vigencia_inicio": "2026-01-12",
    "vigencia_fim": "2027-01-11",
}
ACAO = {
    "descricao": "Encontros",
    "periodo_inicio": "2026-03-01",
    "periodo_fim": "2026-11-30",
    "resultado_esperado": "Famílias participando",
    "periodicidade": "mensal",
}


@pytest.fixture
def plataforma(banco):
    """p-1 (Semear, com objetivo, ação e meta) e p-2 (Oficina).

    - admin: administração        - dora: direção
    - coordenadora e ana: coordenação (na conta, todos os programas)
    - jessica: educadora em p-1   - bruno: educador em p-2
    - rafael: saiu de p-1 ontem   - inativo: coordenação na conta, conta desativada
    """
    with banco.begin() as c:
        c.execute(
            sa.text(
                "INSERT INTO projetos (id, nome, identificador, publico, responsavel, vigencia_inicio, vigencia_fim) VALUES "
                "('p-1', 'Semear', 'SEMEAR', 'Crianças', 'Ana Martins', '2026-01-01', '2026-12-31'), "
                "('p-2', 'Oficina', 'OFICINA', 'Jovens', 'Bruno Lima', '2026-01-01', '2026-12-31')"
            )
        )
        c.execute(
            sa.text("INSERT INTO usuarios (id, nome, ativo) VALUES (:id, :nome, :ativo)"),
            [
                {"id": u, "nome": u.title(), "ativo": u != "inativo"}
                for u in ["admin", "dora", "coordenadora", "ana", "jessica", "bruno", "rafael", "inativo", "sem-vinculo"]
            ],
        )
        c.execute(
            sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES "
            "('admin', 'administracao'), ('dora', 'direcao'), ('coordenadora', 'coordenacao'), "
            "('ana', 'coordenacao'), ('inativo', 'coordenacao')")
        )
        c.execute(
            sa.text(
                "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada, data_saida) VALUES "
                "('v2', 'jessica', 'p-1', 'educador', '2025-01-01', NULL), "
                "('v3', 'bruno', 'p-2', 'educador', '2025-01-01', NULL), "
                "('v4', 'rafael', 'p-1', 'psicologo', '2025-01-01', CURRENT_DATE - 1)"
            )
        )
        c.execute(sa.text("INSERT INTO objetivos (id, programa_id, descricao) VALUES ('o-1', 'p-1', 'Vínculos')"))
        c.execute(
            sa.text(
                "INSERT INTO acoes (id, objetivo_id, descricao, periodo_inicio, periodo_fim, resultado_esperado, periodicidade) "
                "VALUES ('a-1', 'o-1', 'Encontros', '2026-03-01', '2026-11-30', 'Famílias', 'mensal')"
            )
        )
        c.execute(sa.text("INSERT INTO metas (id, acao_id, descricao, valor_planejado) VALUES ('m-1', 'a-1', 'Famílias', 40)"))
    return banco


def como(cabecalhos, usuario):
    return {**cabecalhos, "X-Usuario-Id": usuario}


def negacoes(banco):
    with banco.connect() as c:
        return [
            tuple(r)
            for r in c.execute(
                sa.text("SELECT usuario_id, alvo_id, detalhes->>'operacao' FROM log_auditoria WHERE acao = 'acesso_negado' ORDER BY id")
            )
        ]


P1 = "/gestao/programas/p-1"
CONSULTAS = [
    P1,
    f"{P1}/convenios",
    f"{P1}/vagas",
    f"{P1}/objetivos",
    f"{P1}/acoes",
    f"{P1}/metas",
    f"{P1}/metas/m-1/registros",
    f"{P1}/painel",
]
ALTERACOES = [
    ("patch", P1, {"descricao": "Nova descrição"}),
    ("post", f"{P1}/convenios", {"nome": "Convênio municipal"}),
    ("post", f"{P1}/vagas", {"descricao": "Turma da manhã", "quantidade": 20}),
    ("post", f"{P1}/objetivos", {"descricao": "Outro objetivo"}),
    ("post", f"{P1}/acoes", {**ACAO, "objetivo_id": "o-1"}),
    ("post", f"{P1}/metas", {"acao_id": "a-1", "descricao": "Encontros", "valor_planejado": 10}),
    ("post", f"{P1}/metas/m-1/registros", {"data": "2026-04-30", "valor_realizado": 5}),
]


# --- Consultar ---------------------------------------------------------------------


@pytest.mark.parametrize("rota", CONSULTAS)
@pytest.mark.parametrize("usuario", ["ana", "jessica", "dora", "coordenadora", "admin"])
def test_equipe_direcao_coordenacao_e_administracao_consultam_o_programa(cliente, cabecalhos, plataforma, usuario, rota):
    assert cliente.get(rota, headers=como(cabecalhos, usuario)).status_code == 200


@pytest.mark.parametrize("rota", [P1, f"{P1}/painel"])
@pytest.mark.parametrize("usuario", ["bruno", "rafael", "inativo", "sem-vinculo"])
def test_sem_vinculo_ativo_nao_consulta_e_a_tentativa_fica_na_auditoria(cliente, cabecalhos, plataforma, usuario, rota):
    resposta = cliente.get(rota, headers=como(cabecalhos, usuario))

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Seu perfil não tem acesso a este programa."
    assert negacoes(plataforma) == [(usuario, "p-1", "consultar")]


def test_sem_identificacao_do_usuario_400(cliente, cabecalhos, plataforma):
    resposta = cliente.get(P1, headers=cabecalhos)

    assert resposta.status_code == 400


def test_programa_inexistente_continua_404(cliente, cabecalhos, plataforma):
    assert cliente.get("/gestao/programas/nao-existe", headers=como(cabecalhos, "admin")).status_code == 404


# --- Alterar -----------------------------------------------------------------------


@pytest.mark.parametrize("metodo, rota, corpo", ALTERACOES)
@pytest.mark.parametrize("usuario", ["jessica", "dora"])
def test_perfil_que_so_consulta_nao_altera_e_a_tentativa_fica_na_auditoria(
    cliente, cabecalhos, plataforma, usuario, metodo, rota, corpo
):
    resposta = getattr(cliente, metodo)(rota, json=corpo, headers=como(cabecalhos, usuario))

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Seu perfil não pode alterar este programa."
    assert negacoes(plataforma) == [(usuario, "p-1", "gerenciar")]


@pytest.mark.parametrize("metodo, rota, corpo", ALTERACOES)
def test_profissional_de_outro_programa_nao_altera(cliente, cabecalhos, plataforma, metodo, rota, corpo):
    resposta = getattr(cliente, metodo)(rota, json=corpo, headers=como(cabecalhos, "bruno"))

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Seu perfil não tem acesso a este programa."


@pytest.mark.parametrize("metodo, rota, corpo", ALTERACOES)
@pytest.mark.parametrize("usuario", ["ana", "coordenadora", "admin"])
def test_coordenacao_e_administracao_alteram_como_antes(
    cliente, cabecalhos, plataforma, usuario, metodo, rota, corpo
):
    resposta = getattr(cliente, metodo)(rota, json=corpo, headers=como(cabecalhos, usuario))

    assert resposta.status_code in (200, 201), resposta.text
    assert negacoes(plataforma) == []


# --- Cadastrar programa novo -------------------------------------------------------


@pytest.mark.parametrize("usuario", ["coordenadora", "ana", "admin"])
def test_coordenacao_e_administracao_cadastram_programa_novo(cliente, cabecalhos, plataforma, usuario):
    resposta = cliente.post("/gestao/programas", json=PROGRAMA_NOVO, headers=como(cabecalhos, usuario))

    assert resposta.status_code == 201


def test_coordenacao_gerencia_o_programa_que_cadastrou(cliente, cabecalhos, plataforma):
    novo = cliente.post("/gestao/programas", json=PROGRAMA_NOVO, headers=como(cabecalhos, "coordenadora")).json()

    objetivo = cliente.post(
        f"/gestao/programas/{novo['id']}/objetivos", json={"descricao": "Formar"}, headers=como(cabecalhos, "coordenadora")
    )

    assert objetivo.status_code == 201


@pytest.mark.parametrize("usuario", ["dora", "jessica", "sem-vinculo"])
def test_equipe_e_direcao_nao_cadastram_programa_novo(cliente, cabecalhos, plataforma, usuario):
    resposta = cliente.post("/gestao/programas", json=PROGRAMA_NOVO, headers=como(cabecalhos, usuario))

    assert resposta.status_code == 403
    assert resposta.json()["detail"] == "Só a coordenação cadastra programas novos."
    assert negacoes(plataforma) == [(usuario, None, "cadastrar")]
    with plataforma.connect() as c:
        assert c.execute(sa.text("SELECT count(*) FROM projetos WHERE identificador = 'APRENDIZ'")).scalar() == 0


# --- Lista de programas ------------------------------------------------------------


@pytest.mark.parametrize(
    "usuario, esperados",
    [
        ("admin", ["Oficina", "Semear"]),
        ("dora", ["Oficina", "Semear"]),
        ("coordenadora", ["Oficina", "Semear"]),
        ("ana", ["Oficina", "Semear"]),
        ("jessica", ["Semear"]),
        ("bruno", ["Oficina"]),
        ("rafael", []),
        ("inativo", []),
        ("sem-vinculo", []),
    ],
)
def test_lista_so_os_programas_que_a_pessoa_pode_consultar(cliente, cabecalhos, plataforma, usuario, esperados):
    resposta = cliente.get("/gestao/programas", headers=como(cabecalhos, usuario))

    assert resposta.status_code == 200
    assert [p["nome"] for p in resposta.json()] == esperados


# --- Coordenação: visão geral (sem perfil de administração na plataforma final) ----------


def test_coordenacao_ve_pessoas_usuarios_e_valores_financeiros(cliente, cabecalhos, plataforma):
    coordenadora = como(cabecalhos, "coordenadora")

    assert cliente.get("/gestao/pessoas", headers=coordenadora).status_code == 200
    assert cliente.get("/gestao/usuarios", headers=coordenadora).status_code == 200
    visao = cliente.get("/gestao/programas/p-2/visao-integrada", headers=coordenadora)
    assert visao.status_code == 200
    assert visao.json()["financeira"] is not None
    assert negacoes(plataforma) == []


# --- Um tipo só de coordenação (T-87) -------------------------------------------------
# ``coordenacao`` vem da conta (tabela de papéis compartilhada com o Financeiro, que já a
# trata como "vê todos os programas") e não existe como vínculo.


def test_coordenacao_aparece_como_papel_da_conta_e_sem_vinculo(cliente, cabecalhos, plataforma):
    usuarios = {u["id"]: u for u in cliente.get("/gestao/usuarios", headers=como(cabecalhos, "admin")).json()}

    assert usuarios["ana"]["papeis"] == [{"id": "coordenacao", "nome": "Coordenação"}]
    assert usuarios["ana"]["vinculos"] == []


def test_a_tabela_de_papeis_compartilhada_com_o_financeiro_nao_muda(plataforma):
    with plataforma.connect() as c:
        assert c.execute(sa.text("SELECT nome FROM papeis WHERE id = 'coordenacao'")).scalar_one() == "Coordenação"
        assert c.execute(sa.text("SELECT count(*) FROM papeis WHERE id LIKE 'coordenacao%'")).scalar_one() == 1


@pytest.mark.parametrize(
    "rota",
    ["/gestao/programas/p-2/turmas", "/gestao/programas/p-2/agenda", "/gestao/alertas?programa_id=p-2", "/gestao/pessoas?programa_id=p-2"],
    ids=["turmas", "agenda", "alertas", "pessoas"],
)
@pytest.mark.parametrize("usuario", ["coordenadora", "ana"])
def test_coordenacao_alcanca_as_rotas_de_todos_os_programas(cliente, cabecalhos, plataforma, usuario, rota):
    # Sem vínculo com p-2: o papel na conta vale para todos os programas.
    assert cliente.get(rota, headers=como(cabecalhos, usuario)).status_code == 200


def test_educador_so_alcanca_as_turmas_do_proprio_programa(cliente, cabecalhos, plataforma):
    assert cliente.get("/gestao/programas/p-2/turmas", headers=como(cabecalhos, "jessica")).status_code == 403
    assert cliente.get("/gestao/programas/p-2/turmas", headers=como(cabecalhos, "bruno")).status_code == 200
