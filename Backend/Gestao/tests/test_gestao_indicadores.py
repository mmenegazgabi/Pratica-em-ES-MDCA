"""Indicadores por programa e período (T-72 · US-10), com os critérios da T-74.

1. O valor de cada indicador com registros conhecidos.
2. O mesmo recorte (programa e período) aplicado a todos os indicadores.
3. Período fechado e em aberto.
4. Nenhum dado pessoal na visão agregada.
5. Quem vê quais programas.

Os encontros são de setembro de 2026 (período já fechado), gravados direto no banco
para os números ficarem fixos.
"""

import json
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

INDICADORES = "/gestao/indicadores"
SETEMBRO = {"inicio": "2026-09-01", "fim": "2026-09-30"}
AGOSTO = {"inicio": "2026-08-01", "fim": "2026-08-31"}
NOMES = ["Lara Oliveira", "Davi Oliveira", "Nina Oliveira", "Caio Souza", "Rui Souza"]


@pytest.fixture
def dados(banco):
    """Três programas: p-1 (Semear) e p-2 (Oficina) com encontros; p-3 (Brincar) vazio.

    - ana: coordenação    - dora: direção    - zeca: sem papel nem vínculo
    - jessica: educadora em p-1    - bruno: educador em p-2
    - t-1 (p-1, 14h-16h): Lara e Davi desde agosto; Nina saiu em 01/09; Rui na espera
    - t-2 (p-1, 9h-10h30): Lara desde 10/09
    - t-9 (p-2, 8h-9h): Caio desde 05/09

    Setembro: t-1 em 02/09 (Lara e Davi presentes) e 09/09 (Lara presente, Davi com falta
    justificada); t-2 em 16/09 (Lara falta); t-9 em 03/09 (Caio presente).
    Agosto: t-1 em 26/08 (Lara, Davi e Nina presentes).
    Metas de p-1: "Famílias" 40 (10 em agosto, 10 em setembro, 5 em outubro) e "Encontros" 10.
    """
    with banco.begin() as c:
        c.execute(
            sa.text(
                "INSERT INTO projetos (id, nome, identificador) VALUES "
                "('p-1', 'Semear', 'SEMEAR'), ('p-2', 'Oficina', 'OFICINA'), ('p-3', 'Brincar', 'BRINCAR')"
            )
        )
        c.execute(
            sa.text("INSERT INTO usuarios (id, nome) VALUES (:id, :nome)"),
            [
                {"id": u, "nome": n}
                for u, n in [
                    ("ana", "Ana Martins"), ("dora", "Dora Prates"), ("zeca", "Zeca Lima"),
                    ("jessica", "Jéssica Almeida"), ("bruno", "Bruno Lima"),
                ]
            ],
        )
        c.execute(sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('ana', 'coordenacao'), ('dora', 'direcao')"))
        c.execute(
            sa.text(
                "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) VALUES "
                "('v-1', 'jessica', 'p-1', 'educador', '2026-01-01'), ('v-2', 'bruno', 'p-2', 'educador', '2026-01-01')"
            )
        )
        c.execute(sa.text("INSERT INTO espacos (id, programa_id, nome) VALUES ('e-1', 'p-1', 'Ateliê'), ('e-2', 'p-2', 'Sala')"))
        c.execute(
            sa.text(
                """
                INSERT INTO turmas (id, programa_id, nome, espaco_id, responsavel_id, capacidade, dias_semana, hora_inicio, hora_fim) VALUES
                    ('t-1', 'p-1', 'Oficina de arte', 'e-1', 'jessica', 20, '{1,2,3,4,5,6,7}', '14:00', '16:00'),
                    ('t-2', 'p-1', 'Leitura', 'e-1', 'jessica', 20, '{1,2,3,4,5,6,7}', '09:00', '10:30'),
                    ('t-9', 'p-2', 'Marcenaria', 'e-2', 'bruno', 20, '{1,2,3,4,5,6,7}', '08:00', '09:00')
                """
            )
        )
        c.execute(sa.text("INSERT INTO nucleos_familiares (id, nome) VALUES ('f-1', 'Oliveira'), ('f-2', 'Souza')"))
        c.execute(
            sa.text(
                "INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id) "
                "VALUES (:id, :nome, lower(:nome), '2014-01-01', :familia, :programa)"
            ),
            [
                {"id": "pe-lara", "nome": "Lara Oliveira", "familia": "f-1", "programa": "p-1"},
                {"id": "pe-davi", "nome": "Davi Oliveira", "familia": "f-1", "programa": "p-1"},
                {"id": "pe-nina", "nome": "Nina Oliveira", "familia": "f-1", "programa": "p-1"},
                {"id": "pe-rui", "nome": "Rui Souza", "familia": "f-2", "programa": "p-1"},
                {"id": "pe-caio", "nome": "Caio Souza", "familia": "f-2", "programa": "p-2"},
            ],
        )
        c.execute(
            sa.text(
                """
                INSERT INTO matriculas (id, turma_id, pessoa_id, situacao, data_entrada, data_saida, motivo_saida) VALUES
                    ('m-1', 't-1', 'pe-lara', 'ativa', '2026-08-01', NULL, NULL),
                    ('m-2', 't-1', 'pe-davi', 'ativa', '2026-08-01', NULL, NULL),
                    ('m-3', 't-1', 'pe-nina', 'desligada', '2026-08-01', '2026-09-01', 'Mudou de cidade'),
                    ('m-4', 't-1', 'pe-rui', 'espera', NULL, NULL, NULL),
                    ('m-5', 't-2', 'pe-lara', 'ativa', '2026-09-10', NULL, NULL),
                    ('m-6', 't-9', 'pe-caio', 'ativa', '2026-09-05', NULL, NULL)
                """
            )
        )
        encontros = [
            ("a-1", "p-1", "t-1", "2026-09-02", "jessica"),
            ("a-2", "p-1", "t-1", "2026-09-09", "jessica"),
            ("a-3", "p-1", "t-2", "2026-09-16", "jessica"),
            ("a-9", "p-2", "t-9", "2026-09-03", "bruno"),
            ("a-0", "p-1", "t-1", "2026-08-26", "jessica"),
        ]
        c.execute(
            sa.text(
                "INSERT INTO atividades (id, registro_id, programa_id, turma_id, data, educador_id, conteudo) "
                "VALUES (:id, :id, :programa, :turma, :data, :educador, 'Encontro')"
            ),
            [{"id": i, "programa": p, "turma": t, "data": d, "educador": e} for i, p, t, d, e in encontros],
        )
        chamadas = [
            ("a-1", "pe-lara", True, None), ("a-1", "pe-davi", True, None),
            ("a-2", "pe-lara", True, None), ("a-2", "pe-davi", False, "Consulta médica"),
            ("a-3", "pe-lara", False, None),
            ("a-9", "pe-caio", True, None),
            ("a-0", "pe-lara", True, None), ("a-0", "pe-davi", True, None), ("a-0", "pe-nina", True, None),
        ]
        c.execute(
            sa.text(
                "INSERT INTO chamadas (id, atividade_id, pessoa_id, presente, justificativa) "
                "VALUES (:id, :atividade, :pessoa, :presente, :justificativa)"
            ),
            [
                {"id": f"c-{n}", "atividade": a, "pessoa": p, "presente": pr, "justificativa": j}
                for n, (a, p, pr, j) in enumerate(chamadas)
            ],
        )
        c.execute(sa.text("INSERT INTO objetivos (id, programa_id, descricao) VALUES ('o-1', 'p-1', 'Vínculos')"))
        c.execute(
            sa.text(
                "INSERT INTO acoes (id, objetivo_id, descricao, periodo_inicio, periodo_fim, resultado_esperado, periodicidade) "
                "VALUES ('ac-1', 'o-1', 'Encontros com famílias', '2026-03-01', '2026-11-30', 'Famílias participando', 'mensal')"
            )
        )
        c.execute(
            sa.text(
                "INSERT INTO metas (id, acao_id, descricao, valor_planejado, unidade) VALUES "
                "('me-1', 'ac-1', 'Famílias', 40, 'famílias'), ('me-2', 'ac-1', 'Encontros', 10, 'encontros')"
            )
        )
        c.execute(
            sa.text(
                "INSERT INTO registros_meta (id, meta_id, data, valor_realizado) VALUES "
                "('r-1', 'me-1', '2026-08-10', 10), ('r-2', 'me-1', '2026-09-20', 10), ('r-3', 'me-1', '2026-10-05', 5)"
            )
        )
    return banco


def como(cabecalhos, usuario):
    return {**cabecalhos, "X-Usuario-Id": usuario}


def consultar(cliente, cabecalhos, usuario="dora", **params):
    resposta = cliente.get(INDICADORES, params=params, headers=como(cabecalhos, usuario))
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def por_programa(corpo):
    return {p["programa_id"]: p["numeros"] for p in corpo["programas"]}


# --- 1. Valores com registros conhecidos -----------------------------------------


def test_valores_de_setembro_por_programa_e_no_total(cliente, cabecalhos, dados):
    corpo = consultar(cliente, cabecalhos, **SETEMBRO)

    assert corpo["periodo"] == {"inicio": "2026-09-01", "fim": "2026-09-30", "fechado": True}
    assert [(p["programa_id"], p["nome"], p["identificador"]) for p in corpo["programas"]] == [
        ("p-3", "Brincar", "BRINCAR"),
        ("p-2", "Oficina", "OFICINA"),
        ("p-1", "Semear", "SEMEAR"),
    ]
    numeros = por_programa(corpo)
    # Lara e Davi (Nina saiu em 01/09 e Rui está na espera); 3 encontros; a falta
    # justificada do Davi conta como ausência; 2h + 2h + 1h30.
    assert numeros["p-1"] == {
        "pessoas_acompanhadas": 2,
        "encontros_realizados": 3,
        "presencas": 3,
        "ausencias": 2,
        "frequencia": 60.0,
        "horas_de_atividades": 5.5,
        "metas": 2,
        # Famílias: 20 de 40 até 30/09 (50%); Encontros: 0 de 10 (0%).
        "percentual_medio_das_metas": 25.0,
    }
    assert numeros["p-2"] == {
        "pessoas_acompanhadas": 1,
        "encontros_realizados": 1,
        "presencas": 1,
        "ausencias": 0,
        "frequencia": 100.0,
        "horas_de_atividades": 1.0,
        "metas": 0,
        "percentual_medio_das_metas": None,
    }
    assert numeros["p-3"] == {
        "pessoas_acompanhadas": 0,
        "encontros_realizados": 0,
        "presencas": 0,
        "ausencias": 0,
        "frequencia": None,
        "horas_de_atividades": 0.0,
        "metas": 0,
        "percentual_medio_das_metas": None,
    }
    assert corpo["totais"] == {
        "pessoas_acompanhadas": 3,
        "encontros_realizados": 4,
        "presencas": 4,
        "ausencias": 2,
        "frequencia": 66.7,
        "horas_de_atividades": 6.5,
        "metas": 2,
        "percentual_medio_das_metas": 25.0,
    }


def test_pessoa_em_duas_turmas_do_programa_conta_uma_vez(cliente, cabecalhos, dados):
    # Lara está em t-1 e t-2 em setembro.
    assert por_programa(consultar(cliente, cabecalhos, programa_id="p-1", **SETEMBRO))["p-1"]["pessoas_acompanhadas"] == 2


# --- 2. O mesmo recorte para todos os indicadores --------------------------------


def test_filtro_de_programa_vale_para_todos_os_numeros(cliente, cabecalhos, dados):
    corpo = consultar(cliente, cabecalhos, programa_id="p-2", **SETEMBRO)

    assert [p["programa_id"] for p in corpo["programas"]] == ["p-2"]
    assert corpo["totais"] == corpo["programas"][0]["numeros"]


def test_outro_periodo_muda_todos_os_numeros_juntos(cliente, cabecalhos, dados):
    numeros = por_programa(consultar(cliente, cabecalhos, **AGOSTO))["p-1"]

    # Em agosto Nina ainda estava na turma; um encontro com os três presentes; só os 10
    # de agosto na meta "Famílias" (25%) e 0% em "Encontros".
    assert numeros == {
        "pessoas_acompanhadas": 3,
        "encontros_realizados": 1,
        "presencas": 3,
        "ausencias": 0,
        "frequencia": 100.0,
        "horas_de_atividades": 2.0,
        "metas": 2,
        "percentual_medio_das_metas": 12.5,
    }


def test_so_o_inicio_ou_so_o_fim_completa_o_mes(cliente, cabecalhos, dados):
    assert consultar(cliente, cabecalhos, inicio="2026-09-01")["periodo"]["fim"] == "2026-09-30"
    assert consultar(cliente, cabecalhos, fim="2026-08-31")["periodo"]["inicio"] == "2026-08-01"


# --- 3. Período fechado e em aberto ----------------------------------------------


def test_sem_datas_usa_o_mes_atual_em_aberto(cliente, cabecalhos, dados):
    hoje = date.today()

    periodo = consultar(cliente, cabecalhos)["periodo"]

    assert periodo["inicio"] == hoje.replace(day=1).isoformat()
    assert periodo["fechado"] is False


def test_periodo_fecha_quando_o_fim_ja_passou(cliente, cabecalhos, dados):
    hoje = date.today()
    ontem = hoje - timedelta(days=1)
    inicio = (hoje - timedelta(days=10)).isoformat()

    assert consultar(cliente, cabecalhos, inicio=inicio, fim=hoje.isoformat())["periodo"]["fechado"] is False
    assert consultar(cliente, cabecalhos, inicio=inicio, fim=ontem.isoformat())["periodo"]["fechado"] is True


@pytest.mark.parametrize(
    "params",
    [
        {"inicio": "2026-09-30", "fim": "2026-09-01"},
        {"inicio": "2025-01-01", "fim": "2026-09-30"},
    ],
)
def test_periodo_invalido_recebe_400(cliente, cabecalhos, dados, params):
    resposta = cliente.get(INDICADORES, params=params, headers=como(cabecalhos, "dora"))

    assert resposta.status_code == 400


# --- 4. Sem dados pessoais --------------------------------------------------------


@pytest.mark.parametrize("usuario", ["dora", "ana", "jessica"])
def test_visao_agregada_nao_tem_dados_pessoais(cliente, cabecalhos, dados, usuario):
    texto = json.dumps(consultar(cliente, cabecalhos, usuario, **SETEMBRO), ensure_ascii=False)

    for nome in NOMES:
        assert nome not in texto
        assert nome.split()[0] not in texto
    assert "pe-" not in texto
    assert "2014-01-01" not in texto


# --- 5. Quem vê quais programas ----------------------------------------------------


@pytest.mark.parametrize("usuario", ["dora", "ana"])
def test_direcao_e_coordenacao_veem_todos_os_programas(cliente, cabecalhos, dados, usuario):
    assert set(por_programa(consultar(cliente, cabecalhos, usuario, **SETEMBRO))) == {"p-1", "p-2", "p-3"}


def test_equipe_ve_so_os_programas_em_que_tem_vinculo(cliente, cabecalhos, dados):
    corpo = consultar(cliente, cabecalhos, "jessica", **SETEMBRO)

    assert list(por_programa(corpo)) == ["p-1"]
    assert corpo["totais"]["encontros_realizados"] == 3


def test_quem_nao_tem_vinculo_recebe_recorte_vazio(cliente, cabecalhos, dados):
    corpo = consultar(cliente, cabecalhos, "zeca", **SETEMBRO)

    assert corpo["programas"] == []
    assert corpo["totais"]["encontros_realizados"] == 0
    assert corpo["totais"]["frequencia"] is None


def test_programa_de_outra_equipe_recebe_403_registrado(cliente, cabecalhos, dados):
    resposta = cliente.get(INDICADORES, params={"programa_id": "p-2"}, headers=como(cabecalhos, "jessica"))

    assert resposta.status_code == 403
    with dados.connect() as c:
        negacoes = c.execute(
            sa.text("SELECT usuario_id, alvo_id FROM log_auditoria WHERE acao = 'acesso_negado'")
        ).all()
    assert [tuple(n) for n in negacoes] == [("jessica", "p-2")]


def test_programa_que_nao_existe_recebe_404(cliente, cabecalhos, dados):
    resposta = cliente.get(INDICADORES, params={"programa_id": "p-x"}, headers=como(cabecalhos, "dora"))

    assert resposta.status_code == 404


def test_sem_login_recebe_401(cliente, dados):
    assert cliente.get(INDICADORES).status_code == 401
