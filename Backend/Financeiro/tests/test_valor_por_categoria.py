"""US-01 — Valor orçado por categoria no orçamento.

POST /orcamentos e PATCH /orcamentos/{id} recebem o valor de cada categoria;
GET /orcamentos e GET /orcamentos/{id} devolvem, por categoria, o valor
orçado, o realizado (só aprovados), o percentual e o nível de alerta.
"""

import pytest
from fastapi.testclient import TestClient

from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.main import app
from Financeiro.notificacoes import caixa_de_notificacoes
from Financeiro.orcamento import OrcamentoInvalido, validar_categorias
from Financeiro.routers.comprovantes import obter_armazenamento
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

client = TestClient(app)


def como(papel, usuario=None):
    headers = {"Authorization": f"Bearer {TOKEN}", "X-Papel-Usuario": papel}
    if usuario:
        headers["X-Usuario-Id"] = usuario
    return headers


COORDENACAO = como("coordenacao")


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    _orcamentos.clear()
    caixa_de_notificacoes.limpar()
    app.dependency_overrides[obter_armazenamento] = lambda: ArmazenamentoEmMemoria()
    yield
    app.dependency_overrides.clear()
    _orcamentos.clear()
    caixa_de_notificacoes.limpar()


def payload(valor_total=10000, **campos):
    corpo = {
        "projeto_id": "oficina-de-arte",
        "valor_total": valor_total,
        "data_inicio": "2026-01-01",
        "data_fim": "2026-12-31",
    }
    if "categorias_despesa" not in campos and "categorias" not in campos:
        campos["categorias"] = [
            {"nome": "materiais", "valor_orcado": 4000},
            {"nome": "alimentacao", "valor_orcado": 3000},
        ]
    corpo.update(campos)
    return corpo


def criar(**campos):
    resposta = client.post("/orcamentos", json=payload(**campos))
    assert resposta.status_code == 201, resposta.json()
    return resposta.json()["id"]


def editar(orcamento_id, corpo, headers=COORDENACAO):
    return client.patch(f"/orcamentos/{orcamento_id}", json=corpo, headers=headers)


def detalhe(orcamento_id):
    return client.get(f"/orcamentos/{orcamento_id}").json()


def categorias(orcamento_id):
    return {c["nome"]: c for c in detalhe(orcamento_id)["categorias"]}


def gastar(orcamento_id, valor, categoria="materiais", aprovar=True):
    lancamento_id = client.post(
        "/lancamentos",
        data={
            "orcamento_id": orcamento_id,
            "valor": str(valor),
            "descricao": "Compra",
            "categoria": categoria,
            "data_despesa": "2026-10-10",
        },
        files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
        headers=como("educador", "educadora-ana"),
    ).json()["id"]
    if aprovar:
        assert client.patch(
            f"/lancamentos/{lancamento_id}/aprovar", headers=COORDENACAO
        ).status_code == 200
    return lancamento_id


# --- Critério 1: salva o valor de cada categoria -----------------------------


@pytest.mark.parametrize(
    "valores",
    [(4000, 3000), (6000, 4000), (0, 0), (10000, 0)],
    ids=["soma-abaixo-do-total", "soma-igual-ao-total", "zeradas", "uma-com-tudo"],
)
def test_criar_com_valores_validos_salva_cada_categoria(valores):
    orcamento_id = criar(
        categorias=[
            {"nome": "materiais", "valor_orcado": valores[0]},
            {"nome": "alimentacao", "valor_orcado": valores[1]},
        ]
    )

    por_nome = categorias(orcamento_id)
    assert por_nome["materiais"]["valor_orcado"] == valores[0]
    assert por_nome["alimentacao"]["valor_orcado"] == valores[1]


def test_editar_com_valores_validos_salva_cada_categoria():
    orcamento_id = criar()

    resposta = editar(
        orcamento_id,
        {
            "categorias": [
                {"nome": "materiais", "valor_orcado": 5000},
                {"nome": "alimentacao", "valor_orcado": 2500},
                {"nome": "transporte", "valor_orcado": 1500},
            ]
        },
    )

    assert resposta.status_code == 200
    assert [(c["nome"], c["valor_orcado"]) for c in resposta.json()["categorias"]] == [
        ("materiais", 5000),
        ("alimentacao", 2500),
        ("transporte", 1500),
    ]
    assert detalhe(orcamento_id)["categorias_despesa"] == [
        "materiais",
        "alimentacao",
        "transporte",
    ]


def test_soma_compara_em_centavos():
    # 0,10 + 0,20 em float dá 0,30000000000000004, que não pode contar como
    # acima de 0,30.
    validar_categorias(0.3, ["a", "b"], {"a": 0.1, "b": 0.2})


# --- Critério 2: soma acima do total → 400 ----------------------------------


def test_criar_com_soma_acima_do_total_retorna_400():
    resposta = client.post(
        "/orcamentos",
        json=payload(
            valor_total=10000,
            categorias=[
                {"nome": "materiais", "valor_orcado": 6000},
                {"nome": "alimentacao", "valor_orcado": 4000.01},
            ],
        ),
    )

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == (
        "A soma das categorias (R$ 10.000,01) passa do valor total do "
        "orçamento (R$ 10.000,00)."
    )
    assert _orcamentos == []


def test_editar_categorias_com_soma_acima_do_total_retorna_400_e_nada_muda():
    orcamento_id = criar()

    resposta = editar(
        orcamento_id,
        {"categorias": [{"nome": "materiais", "valor_orcado": 10001}]},
    )

    assert resposta.status_code == 400
    assert "passa do valor total" in resposta.json()["detail"]
    assert categorias(orcamento_id)["materiais"]["valor_orcado"] == 4000
    assert detalhe(orcamento_id)["categorias_despesa"] == ["materiais", "alimentacao"]


def test_reduzir_total_abaixo_da_soma_das_categorias_retorna_400():
    orcamento_id = criar()  # categorias somam 7000

    resposta = editar(orcamento_id, {"valor_total": 6999})

    assert resposta.status_code == 400
    assert "passa do valor total" in resposta.json()["detail"]
    assert detalhe(orcamento_id)["valor_total"] == 10000


# --- Critério 3: não reduz categoria abaixo do que já foi gasto --------------


def test_reduzir_categoria_abaixo_do_gasto_retorna_400():
    orcamento_id = criar()
    gastar(orcamento_id, 3840)

    resposta = editar(
        orcamento_id,
        {
            "categorias": [
                {"nome": "materiais", "valor_orcado": 3000},
                {"nome": "alimentacao", "valor_orcado": 3000},
            ]
        },
    )

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == (
        "O valor orçado da categoria materiais (R$ 3.000,00) é menor do que "
        "já foi gasto nela (R$ 3.840,00)."
    )
    assert categorias(orcamento_id)["materiais"]["valor_orcado"] == 4000


def test_reduzir_categoria_ate_exatamente_o_gasto_e_permitido():
    orcamento_id = criar()
    gastar(orcamento_id, 3840)

    resposta = editar(
        orcamento_id,
        {
            "categorias": [
                {"nome": "materiais", "valor_orcado": 3840},
                {"nome": "alimentacao", "valor_orcado": 3000},
            ]
        },
    )

    assert resposta.status_code == 200
    assert categorias(orcamento_id)["materiais"]["nivel_alerta"] == "estourado"


def test_gasto_pendente_nao_conta_para_o_limite():
    orcamento_id = criar()
    gastar(orcamento_id, 3840, aprovar=False)

    resposta = editar(
        orcamento_id,
        {"categorias": [{"nome": "materiais", "valor_orcado": 100},
                        {"nome": "alimentacao", "valor_orcado": 0}]},
    )

    assert resposta.status_code == 200


def test_reduzir_total_abaixo_do_gasto_retorna_400():
    orcamento_id = criar(categorias_despesa=["materiais"])
    gastar(orcamento_id, 3000)

    resposta = editar(orcamento_id, {"valor_total": 2999})

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == (
        "O valor total (R$ 2.999,00) é menor do que já foi gasto no "
        "orçamento (R$ 3.000,00)."
    )


# --- Critério 4: GET traz o detalhamento de cada categoria ------------------


def test_get_por_id_traz_cada_categoria_com_realizado_percentual_e_alerta():
    orcamento_id = criar()
    gastar(orcamento_id, 3840)            # materiais: 96% → atencao
    gastar(orcamento_id, 500, aprovar=False)  # pendente não conta
    gastar(orcamento_id, 300, categoria="alimentacao")  # 10% → normal

    assert detalhe(orcamento_id)["categorias"] == [
        {
            "nome": "materiais",
            "valor_orcado": 4000,
            "realizado": 3840,
            "percentual_consumido": 96,
            "nivel_alerta": "atencao",
        },
        {
            "nome": "alimentacao",
            "valor_orcado": 3000,
            "realizado": 300,
            "percentual_consumido": 10,
            "nivel_alerta": "normal",
        },
    ]


@pytest.mark.parametrize(
    "gasto, nivel",
    [(799.99, "normal"), (800, "atencao"), (999.99, "atencao"), (1000, "estourado")],
)
def test_limiares_de_alerta_da_categoria_sao_80_e_100(gasto, nivel):
    orcamento_id = criar(categorias=[{"nome": "materiais", "valor_orcado": 1000}])
    gastar(orcamento_id, gasto)

    assert categorias(orcamento_id)["materiais"]["nivel_alerta"] == nivel


def test_categoria_estourada_quando_aprovacao_passa_do_limite():
    # O limite da categoria não bloqueia a aprovação; ele vira alerta.
    orcamento_id = criar(categorias=[{"nome": "materiais", "valor_orcado": 1000}])
    gastar(orcamento_id, 1200)

    materiais = categorias(orcamento_id)["materiais"]
    assert materiais["percentual_consumido"] == 120
    assert materiais["nivel_alerta"] == "estourado"


def test_categoria_com_valor_zero_e_gasto_fica_estourada():
    orcamento_id = criar(categorias=[{"nome": "materiais", "valor_orcado": 0}])
    gastar(orcamento_id, 10)

    materiais = categorias(orcamento_id)["materiais"]
    assert materiais["percentual_consumido"] is None
    assert materiais["nivel_alerta"] == "estourado"


def test_get_lista_tambem_traz_as_categorias():
    orcamento_id = criar()
    gastar(orcamento_id, 400)

    [item] = client.get("/orcamentos").json()
    [paginado] = client.get("/orcamentos/projeto/oficina-de-arte").json()["itens"]

    for corpo in (item, paginado):
        assert corpo["id"] == orcamento_id
        assert corpo["categorias"][0]["realizado"] == 400
        assert corpo["categorias"][0]["percentual_consumido"] == 10


def test_orcamento_so_com_nomes_tem_categorias_sem_limite():
    orcamento_id = criar(categorias_despesa=["materiais", "transporte"])
    gastar(orcamento_id, 250)

    assert detalhe(orcamento_id)["categorias"] == [
        {
            "nome": "materiais",
            "valor_orcado": None,
            "realizado": 250,
            "percentual_consumido": None,
            "nivel_alerta": None,
        },
        {
            "nome": "transporte",
            "valor_orcado": None,
            "realizado": 0,
            "percentual_consumido": None,
            "nivel_alerta": None,
        },
    ]


# --- Critério 5: categorias_despesa continua na resposta ---------------------


def test_categorias_despesa_continua_com_os_nomes_na_ordem():
    orcamento_id = criar()

    assert detalhe(orcamento_id)["categorias_despesa"] == ["materiais", "alimentacao"]
    [vigente] = client.get("/orcamentos", params={"vigentes_em": "2026-10-10"}).json()
    assert vigente["categorias_despesa"] == ["materiais", "alimentacao"]


def test_formulario_do_celular_lanca_em_categoria_do_novo_formato():
    orcamento_id = criar()

    gastar(orcamento_id, 50, categoria="alimentacao", aprovar=False)

    assert _orcamentos[0].lancamentos[0].categoria == "alimentacao"


# --- Validações de entrada ---------------------------------------------------


@pytest.mark.parametrize(
    "lista, mensagem",
    [
        ([{"nome": "materiais", "valor_orcado": -1}],
         "O valor orçado da categoria materiais deve ser maior ou igual a zero."),
        ([{"nome": "materiais", "valor_orcado": 1}, {"nome": "Materiais ", "valor_orcado": 1}],
         "Categoria repetida: Materiais."),
        ([{"nome": "   ", "valor_orcado": 1}], "Nome de categoria não pode ser vazio."),
    ],
    ids=["negativo", "repetida", "nome-vazio"],
)
def test_categorias_invalidas_retornam_400_no_post_e_no_patch(lista, mensagem):
    resposta = client.post("/orcamentos", json=payload(categorias=lista))
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == mensagem

    orcamento_id = criar()
    resposta = editar(orcamento_id, {"categorias": lista})
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == mensagem


@pytest.mark.parametrize(
    "campos",
    [
        {"categorias": []},
        {"categorias_despesa": []},
        {"categorias": None, "categorias_despesa": None},
        {"categorias": [{"nome": "a", "valor_orcado": 1}], "categorias_despesa": ["a"]},
        {"categorias": [{"nome": "materiais"}]},
    ],
    ids=["lista-vazia", "nomes-vazio", "nenhum", "os-dois", "sem-valor"],
)
def test_formato_de_categorias_invalido_no_post_retorna_422(campos):
    assert client.post("/orcamentos", json=payload(**campos)).status_code == 422


def test_patch_sem_nada_para_editar_retorna_422():
    orcamento_id = criar()
    assert editar(orcamento_id, {}).status_code == 422


def test_post_com_nomes_segue_funcionando_como_antes():
    resposta = client.post(
        "/orcamentos", json=payload(categorias_despesa=["materiais", "transporte"])
    )
    assert resposta.status_code == 201


# --- PATCH: demais regras ----------------------------------------------------


def test_editar_valor_total_atualiza_o_saldo():
    orcamento_id = criar()
    gastar(orcamento_id, 1000)

    resposta = editar(orcamento_id, {"valor_total": 12000})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["valor_total"] == 12000
    assert corpo["saldo"] == 11000
    assert corpo["categorias"][0]["valor_orcado"] == 4000  # categorias mantidas


def test_nao_remove_categoria_com_lancamento():
    orcamento_id = criar()
    gastar(orcamento_id, 100, categoria="alimentacao", aprovar=False)

    resposta = editar(
        orcamento_id, {"categorias": [{"nome": "materiais", "valor_orcado": 4000}]}
    )

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == (
        "Não é possível remover categoria com lançamentos: alimentacao."
    )


def test_remove_categoria_sem_lancamento_ou_so_com_rejeitados():
    orcamento_id = criar()
    rejeitado = gastar(orcamento_id, 100, categoria="alimentacao", aprovar=False)
    client.patch(
        f"/lancamentos/{rejeitado}/rejeitar", json={"motivo": "Duplicado."}, headers=COORDENACAO
    )

    resposta = editar(
        orcamento_id, {"categorias": [{"nome": "materiais", "valor_orcado": 4000}]}
    )

    assert resposta.status_code == 200
    assert resposta.json()["categorias_despesa"] == ["materiais"]


def test_orcamento_inexistente_retorna_404():
    assert editar("nao-existe", {"valor_total": 1}).status_code == 404


@pytest.mark.parametrize("papel", ["educador", "voluntario_financeiro", ""])
def test_so_coordenacao_e_direcao_editam(papel):
    orcamento_id = criar()
    assert editar(orcamento_id, {"valor_total": 1}, headers=como(papel)).status_code == 403
    assert editar(orcamento_id, {"valor_total": 20000}, headers=como("direcao")).status_code == 200


def test_editar_sem_token_retorna_401():
    orcamento_id = criar()
    assert editar(orcamento_id, {"valor_total": 1}, headers={}).status_code == 401


def test_dominio_rejeita_soma_acima_do_total():
    with pytest.raises(OrcamentoInvalido):
        validar_categorias(100, ["a", "b"], {"a": 60, "b": 40.01})
