"""T-44 · US-02: objetivos, ações, metas, registros do realizado e painel de acompanhamento."""

import pytest

PROGRAMA = {
    "nome": "Convivência e fortalecimento de vínculos",
    "identificador": "SCFV",
    "publico": "Crianças e adolescentes de 6 a 15 anos",
    "responsavel": "Ana Martins",
    "vigencia_inicio": "2026-02-02",
    "vigencia_fim": "2026-12-18",
}

ACAO = {
    "descricao": "Oficinas semanais de convivência",
    "periodo_inicio": "2026-03-02",
    "periodo_fim": "2026-11-30",
    "resultado_esperado": "120 oficinas realizadas no ano",
    "periodicidade": "mensal",
}


@pytest.fixture
def programa(cliente, cabecalhos, banco):
    resposta = cliente.post("/gestao/programas", json=PROGRAMA, headers=cabecalhos)
    assert resposta.status_code == 201
    return f"/gestao/programas/{resposta.json()['id']}"


@pytest.fixture
def objetivo_id(cliente, cabecalhos, programa):
    resposta = cliente.post(
        f"{programa}/objetivos",
        json={"descricao": "Ampliar a participação nas atividades coletivas"},
        headers=cabecalhos,
    )
    assert resposta.status_code == 201
    return resposta.json()["id"]


@pytest.fixture
def acao_id(cliente, cabecalhos, programa, objetivo_id):
    resposta = cliente.post(
        f"{programa}/acoes", json={**ACAO, "objetivo_id": objetivo_id}, headers=cabecalhos
    )
    assert resposta.status_code == 201
    return resposta.json()["id"]


def criar_meta(cliente, cabecalhos, programa, acao_id, descricao="Oficinas realizadas", planejado=120):
    resposta = cliente.post(
        f"{programa}/metas",
        json={"acao_id": acao_id, "descricao": descricao, "valor_planejado": planejado, "unidade": "oficinas"},
        headers=cabecalhos,
    )
    assert resposta.status_code == 201
    return resposta.json()["id"]


def registrar(cliente, cabecalhos, programa, meta_id, valor, data="2026-04-30"):
    return cliente.post(
        f"{programa}/metas/{meta_id}/registros",
        json={"data": data, "valor_realizado": valor},
        headers=cabecalhos,
    )


# ---- Objetivos ---------------------------------------------------------------------


def test_cadastra_e_lista_objetivos(cliente, cabecalhos, programa, objetivo_id):
    resposta = cliente.get(f"{programa}/objetivos", headers=cabecalhos)

    assert resposta.json() == [
        {"id": objetivo_id, "descricao": "Ampliar a participação nas atividades coletivas"}
    ]


def test_objetivo_sem_descricao_400(cliente, cabecalhos, programa):
    resposta = cliente.post(f"{programa}/objetivos", json={"descricao": " "}, headers=cabecalhos)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Objetivo sem descrição."


# ---- Ações -------------------------------------------------------------------------


def test_cadastra_e_lista_acoes(cliente, cabecalhos, programa, objetivo_id, acao_id):
    resposta = cliente.get(f"{programa}/acoes", headers=cabecalhos)

    assert resposta.json() == [{"id": acao_id, "objetivo_id": objetivo_id, **ACAO}]


@pytest.mark.parametrize(
    "ausentes, mensagem",
    [
        ({"periodo_inicio": None}, "Ação sem período (início e fim)."),
        ({"periodo_fim": None}, "Ação sem período (início e fim)."),
        ({"resultado_esperado": "  "}, "Ação sem resultado esperado."),
        ({"periodicidade": None}, "Ação sem periodicidade."),
        (
            {"periodo_inicio": None, "periodo_fim": None, "resultado_esperado": None, "periodicidade": ""},
            "Ação sem período (início e fim), resultado esperado e periodicidade.",
        ),
    ],
)
def test_acao_sem_periodo_resultado_ou_periodicidade_400(
    cliente, cabecalhos, programa, objetivo_id, ausentes, mensagem
):
    resposta = cliente.post(
        f"{programa}/acoes", json={**ACAO, "objetivo_id": objetivo_id, **ausentes}, headers=cabecalhos
    )

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == mensagem
    assert cliente.get(f"{programa}/acoes", headers=cabecalhos).json() == []


def test_acao_com_campos_omitidos_no_corpo_400(cliente, cabecalhos, programa, objetivo_id):
    resposta = cliente.post(
        f"{programa}/acoes",
        json={"objetivo_id": objetivo_id, "descricao": "Oficinas"},
        headers=cabecalhos,
    )

    assert resposta.status_code == 400
    assert "período (início e fim)" in resposta.json()["detail"]


@pytest.mark.parametrize(
    "campos, mensagem",
    [
        (
            {"periodicidade": "diária"},
            "Periodicidade inválida. Use uma destas: semanal, quinzenal, mensal, bimestral, "
            "trimestral, semestral, anual.",
        ),
        (
            {"periodo_inicio": "2026-11-30", "periodo_fim": "2026-03-02"},
            "O fim do período da ação não pode ser anterior ao início.",
        ),
        (
            {"periodo_inicio": "2026-01-15"},
            "O período da ação deve estar dentro da vigência do programa (02/02/2026 a 18/12/2026).",
        ),
        (
            {"periodo_fim": "2027-01-31"},
            "O período da ação deve estar dentro da vigência do programa (02/02/2026 a 18/12/2026).",
        ),
        ({"objetivo_id": "outro"}, "Objetivo não encontrado neste programa."),
    ],
)
def test_acao_invalida_400(cliente, cabecalhos, programa, objetivo_id, campos, mensagem):
    resposta = cliente.post(
        f"{programa}/acoes", json={**ACAO, "objetivo_id": objetivo_id, **campos}, headers=cabecalhos
    )

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == mensagem


def test_periodicidade_aceita_maiusculas(cliente, cabecalhos, programa, objetivo_id):
    resposta = cliente.post(
        f"{programa}/acoes",
        json={**ACAO, "objetivo_id": objetivo_id, "periodicidade": "Trimestral"},
        headers=cabecalhos,
    )

    assert resposta.status_code == 201
    assert resposta.json()["periodicidade"] == "trimestral"


def test_objetivo_de_outro_programa_nao_serve(cliente, cabecalhos, programa, objetivo_id):
    outro = cliente.post(
        "/gestao/programas", json={**PROGRAMA, "identificador": "OUTRO"}, headers=cabecalhos
    ).json()["id"]

    resposta = cliente.post(
        f"/gestao/programas/{outro}/acoes",
        json={**ACAO, "objetivo_id": objetivo_id},
        headers=cabecalhos,
    )

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Objetivo não encontrado neste programa."


# ---- Metas e registros -------------------------------------------------------------


def test_cadastra_meta_e_registros_do_realizado(cliente, cabecalhos, programa, acao_id):
    meta_id = criar_meta(cliente, cabecalhos, programa, acao_id)
    registrar(cliente, cabecalhos, programa, meta_id, 10, "2026-03-31")
    registrar(cliente, cabecalhos, programa, meta_id, 12.5, "2026-04-30")

    metas = cliente.get(f"{programa}/metas", headers=cabecalhos).json()
    registros = cliente.get(f"{programa}/metas/{meta_id}/registros", headers=cabecalhos).json()

    assert metas == [
        {
            "id": meta_id,
            "acao_id": acao_id,
            "descricao": "Oficinas realizadas",
            "valor_planejado": 120.0,
            "unidade": "oficinas",
        }
    ]
    assert [(r["data"], r["valor_realizado"]) for r in registros] == [
        ("2026-03-31", 10.0),
        ("2026-04-30", 12.5),
    ]


@pytest.mark.parametrize(
    "corpo, mensagem",
    [
        ({}, "Meta sem ação, descrição e valor planejado."),
        ({"descricao": "Oficinas", "valor_planejado": 0}, "O valor planejado da meta deve ser maior que zero."),
        ({"acao_id": "outra", "descricao": "Oficinas", "valor_planejado": 10}, "Ação não encontrada neste programa."),
    ],
)
def test_meta_invalida_400(cliente, cabecalhos, programa, acao_id, corpo, mensagem):
    corpo = {"acao_id": acao_id, **corpo} if corpo else corpo

    resposta = cliente.post(f"{programa}/metas", json=corpo, headers=cabecalhos)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == mensagem


@pytest.mark.parametrize(
    "corpo, mensagem",
    [
        ({}, "Registro sem data e valor realizado."),
        ({"data": "2026-04-30", "valor_realizado": -1}, "O valor realizado deve ser maior que zero."),
    ],
)
def test_registro_invalido_400(cliente, cabecalhos, programa, acao_id, corpo, mensagem):
    meta_id = criar_meta(cliente, cabecalhos, programa, acao_id)

    resposta = cliente.post(f"{programa}/metas/{meta_id}/registros", json=corpo, headers=cabecalhos)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == mensagem


def test_registro_em_meta_inexistente_404(cliente, cabecalhos, programa):
    resposta = registrar(cliente, cabecalhos, programa, "nao-existe", 5)

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Meta não encontrada neste programa."


# ---- Painel ------------------------------------------------------------------------


def test_painel_retorna_planejado_realizado_e_percentual(cliente, cabecalhos, programa, objetivo_id, acao_id):
    oficinas = criar_meta(cliente, cabecalhos, programa, acao_id, "Oficinas realizadas", 120)
    familias = criar_meta(cliente, cabecalhos, programa, acao_id, "Famílias atendidas", 40)
    sem_registro = criar_meta(cliente, cabecalhos, programa, acao_id, "Visitas domiciliares", 30)
    for valor in (40, 30, 22):
        assert registrar(cliente, cabecalhos, programa, oficinas, valor).status_code == 201
    registrar(cliente, cabecalhos, programa, familias, 46)

    resposta = cliente.get(f"{programa}/painel", headers=cabecalhos)

    assert resposta.status_code == 200
    painel = resposta.json()
    assert painel["programa_id"] == programa.rsplit("/", 1)[1]
    por_meta = {m["meta_id"]: m for m in painel["metas"]}
    assert {k: por_meta[oficinas][k] for k in ("planejado", "realizado", "percentual")} == {
        "planejado": 120.0,
        "realizado": 92.0,
        "percentual": 76.7,
    }
    # Meta superada passa de 100%; meta sem registro começa em zero.
    assert (por_meta[familias]["realizado"], por_meta[familias]["percentual"]) == (46.0, 115.0)
    assert (por_meta[sem_registro]["realizado"], por_meta[sem_registro]["percentual"]) == (0.0, 0.0)
    assert por_meta[oficinas]["acao_id"] == acao_id
    assert por_meta[oficinas]["objetivo_id"] == objetivo_id
    assert por_meta[oficinas]["unidade"] == "oficinas"


def test_painel_so_conta_metas_do_proprio_programa(cliente, cabecalhos, programa, acao_id):
    criar_meta(cliente, cabecalhos, programa, acao_id)
    outro = cliente.post(
        "/gestao/programas", json={**PROGRAMA, "identificador": "OUTRO"}, headers=cabecalhos
    ).json()["id"]

    resposta = cliente.get(f"/gestao/programas/{outro}/painel", headers=cabecalhos)

    assert resposta.json() == {"programa_id": outro, "metas": []}


def test_painel_de_programa_inexistente_404(cliente, cabecalhos, banco):
    resposta = cliente.get("/gestao/programas/nao-existe/painel", headers=cabecalhos)

    assert resposta.status_code == 404


def test_painel_sem_autenticacao_401(cliente):
    assert cliente.get("/gestao/programas/p-1/painel").status_code == 401
