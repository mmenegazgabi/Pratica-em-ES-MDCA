"""US-05 — extrato bancário: POST/GET /extrato e conciliação com item do extrato."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from Financeiro.extrato import caixa_do_extrato
from Financeiro.main import app
from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"

client = TestClient(app)


def cabecalhos(papel="voluntario_financeiro", token=TOKEN):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if papel is not None:
        headers["X-Papel-Usuario"] = papel
    return headers


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    _orcamentos.clear()
    caixa_do_extrato.limpar()
    yield
    _orcamentos.clear()
    caixa_do_extrato.limpar()


def importar(csv_texto, papel="voluntario_financeiro", nome="extrato.csv"):
    conteudo = csv_texto if isinstance(csv_texto, bytes) else csv_texto.encode("utf-8")
    return client.post(
        "/extrato",
        files={"arquivo": (nome, conteudo, "text/csv")},
        headers=cabecalhos(papel),
    )


def listar(papel="voluntario_financeiro", **params):
    return client.get("/extrato", params=params, headers=cabecalhos(papel))


CSV_PONTO_E_VIRGULA = (
    "data;descricao;valor\n"
    "2026-10-05;PIX recebido doação;1500,00\n"
    "06/10/2026;Compra material escolar;-250,50\n"
)


# --- Importação --------------------------------------------------------------


def test_importa_csv_com_ponto_e_virgula():
    resposta = importar(CSV_PONTO_E_VIRGULA)

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["importados"] == 2
    assert corpo["ignorados_repetidos"] == 0
    primeiro, segundo = corpo["itens"]
    assert primeiro["data"] == "2026-10-05"
    assert primeiro["descricao"] == "PIX recebido doação"
    assert primeiro["valor"] == 1500.0
    assert primeiro["conciliado_com"] is None
    assert primeiro["id"] and primeiro["importado_em"]
    assert segundo["data"] == "2026-10-06"
    assert segundo["valor"] == -250.5


def test_importa_csv_com_virgula_e_historico_no_lugar_de_descricao():
    resposta = importar("Data,Histórico,Valor\n2026-10-05,Tarifa,-12.90\n")

    assert resposta.status_code == 201
    assert resposta.json()["itens"][0]["descricao"] == "Tarifa"
    assert resposta.json()["itens"][0]["valor"] == -12.9


def test_aceita_historico_sem_acento_bom_utf8_e_linhas_em_branco():
    texto = "﻿data;historico;valor\n\n2026-10-05;Tarifa;-1,00\n;;\n"

    resposta = importar(texto)

    assert resposta.status_code == 201
    assert resposta.json()["importados"] == 1


def test_aceita_arquivo_latin1():
    resposta = importar("data;descrição;valor\n2026-10-05;Doação;10,00\n".encode("latin-1"))

    assert resposta.status_code == 201
    assert resposta.json()["itens"][0]["descricao"] == "Doação"


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("R$ 1.234,56", 1234.56),
        ("1.234,56", 1234.56),
        ("1,234.56", 1234.56),
        ("1234.56", 1234.56),
        ("1234,5", 1234.5),
        ("-R$ 50,00", -50.0),
        ("R$ -50,00", -50.0),
        ("  -  50 ", -50.0),
        ("1.234", 1234.0),
        ("1.234.567,89", 1234567.89),
        ("0,99", 0.99),
    ],
)
def test_formatos_de_valor(texto, esperado):
    resposta = importar(f'data;descricao;valor\n2026-10-05;X;"{texto}"\n')

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["itens"][0]["valor"] == esperado


@pytest.mark.parametrize("data", ["2026-10-05", "05/10/2026", "5/10/2026"])
def test_formatos_de_data(data):
    resposta = importar(f"data;descricao;valor\n{data};X;1,00\n")

    assert resposta.status_code == 201
    assert resposta.json()["itens"][0]["data"] == "2026-10-05"


def test_reimportar_o_mesmo_arquivo_nao_duplica_e_iguais_do_mesmo_arquivo_entram():
    texto = "data;descricao;valor\n2026-10-05;PIX;10,00\n05/10/2026;PIX;10,00\n2026-10-06;PIX;10,00\n"

    primeira = importar(texto).json()
    segunda = importar(texto).json()

    assert (primeira["importados"], primeira["ignorados_repetidos"]) == (3, 0)
    assert (segunda["importados"], segunda["ignorados_repetidos"]) == (0, 3)
    assert segunda["itens"] == []
    assert len(listar().json()) == 3


def test_multiconjunto_entra_so_o_que_passa_do_ja_guardado():
    importar("data;descricao;valor\n2026-10-05;PIX;10,00\n")

    resposta = importar("data;descricao;valor\n2026-10-05;PIX;10,00\n2026-10-05;PIX;10,00\n").json()

    assert (resposta["importados"], resposta["ignorados_repetidos"]) == (1, 1)
    assert len(listar().json()) == 2


def test_csv_malformado_retorna_400_e_nao_500():
    nao_fechada = b'data;descricao;valor\n2026-10-05;"' + b"x" * 200000 + b";1,00\n"
    assert importar(nao_fechada).status_code == 400
    resposta = importar(b'data;descricao;valor\n2026-10-05;"abc;1,00\n')
    assert resposta.status_code in (400, 201)
    campo_enorme = b"data;descricao;valor\n2026-10-05;" + b'"' + b"x" * 140000 + b'";1,00\n'
    resposta = importar(campo_enorme)
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Linha 2: linha mal formada."


def test_valor_gigante_retorna_400():
    resposta = importar("data;descricao;valor\n2026-10-05;A;" + "9" * 400 + "\n")

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Linha 2: valor inválido."
    assert importar("data;descricao;valor\n2026-10-05;A;1000000000000,00\n").status_code == 400


def test_cp1252_reticencias_e_quebras_de_linha_mistas():
    corpo = "data;descricao;valor\r2026-10-05;Pix…;1,00\r\n2026-10-06;Outro;2,00\n".encode("cp1252")

    resposta = importar(corpo)

    assert resposta.status_code == 201
    assert [i["descricao"] for i in resposta.json()["itens"]] == ["Pix…", "Outro"]


@pytest.mark.parametrize("texto, esperado", [("0.500", 0.5), ("12.5", 12.5), ("1.234.567", 1234567.0)])
def test_ponto_so_decimal_ou_milhar(texto, esperado):
    resposta = importar(f"data;descricao;valor\n2026-10-05;A;{texto}\n")

    assert resposta.json()["itens"][0]["valor"] == esperado


def test_ponto_mal_posicionado_e_invalido():
    resposta = importar("data;descricao;valor\n2026-10-05;A;1.23.4\n")

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Linha 2: valor inválido."


def test_caracteres_de_controle_saem_da_descricao():
    resposta = importar("data;descricao;valor\n2026-10-05;Pix\x00 \x07da\tAna;1,00\n")

    assert resposta.json()["itens"][0]["descricao"] == "Pix da Ana"


def test_mesma_data_e_descricao_com_valor_diferente_e_outro_item():
    resposta = importar("data;descricao;valor\n2026-10-05;PIX;10,00\n2026-10-05;PIX;11,00\n")

    assert resposta.json()["importados"] == 2


@pytest.mark.parametrize(
    "texto, mensagem",
    [
        ("data;descricao;valor\n2026-10-05;A;1,00\n2026-10-06;B;abc\n", "Linha 3: valor inválido."),
        ("data;descricao;valor\n31/02/2026;A;1,00\n", "Linha 2: data inválida."),
        ("data;descricao;valor\n2026-10-05;A;1,00\nontem;B;1,00\n", "Linha 3: data inválida."),
        ("data;descricao;valor\n2026-10-05;;1,00\n", "Linha 2: descrição obrigatória."),
        ("data;descricao;valor\n2026-10-05;A\n", "Linha 2: colunas faltando."),
        ("\n\ndata;descricao;valor\n2026-10-05;A;x\n", "Linha 4: valor inválido."),
        ("data;descricao;valor\n2026-10-05;A;1,2,3\n", "Linha 2: valor inválido."),
    ],
)
def test_erro_de_linha_diz_o_numero_e_nao_importa_nada(texto, mensagem):
    resposta = importar(texto)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == mensagem
    assert listar().json() == []


def test_erro_depois_de_linhas_validas_nao_importa_as_anteriores():
    importar("data;descricao;valor\n2026-10-05;A;1,00\n2026-10-06;B;x\n")

    assert listar().json() == []


def test_cabecalho_sem_coluna_obrigatoria():
    resposta = importar("data;valor\n2026-10-05;1,00\n")

    assert resposta.status_code == 400
    assert resposta.json()["detail"].startswith("Cabeçalho inválido")


@pytest.mark.parametrize("texto", ["", "   \n\n", "data;descricao;valor\n"])
def test_arquivo_vazio_ou_sem_linhas(texto):
    assert importar(texto).status_code == 400


def test_sem_arquivo_retorna_400():
    resposta = client.post("/extrato", headers=cabecalhos())

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Envie o arquivo CSV do extrato."


def test_arquivo_acima_de_1_mb_retorna_400():
    linha = "2026-10-05;" + "x" * 90 + ";1,00\n"
    texto = "data;descricao;valor\n" + linha * (1024 * 1024 // len(linha) + 5)

    resposta = importar(texto)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Arquivo acima de 1 MB."
    assert listar().json() == []


# --- Papéis e autenticação ---------------------------------------------------


@pytest.mark.parametrize("papel", ["voluntario_financeiro", "coordenacao"])
def test_importar_permitido(papel):
    assert importar(CSV_PONTO_E_VIRGULA, papel).status_code == 201


@pytest.mark.parametrize("papel", ["direcao", "educador"])
def test_importar_negado_para_outros_papeis(papel):
    resposta = importar(CSV_PONTO_E_VIRGULA, papel)

    assert resposta.status_code == 403
    assert listar().json() == []


@pytest.mark.parametrize("papel", ["voluntario_financeiro", "coordenacao", "direcao"])
def test_listar_permitido(papel):
    assert listar(papel).status_code == 200


def test_listar_negado_para_educador():
    assert listar("educador").status_code == 403


def test_sem_token_retorna_401():
    assert client.get("/extrato", headers=cabecalhos(token=None)).status_code == 401
    resposta = client.post(
        "/extrato",
        files={"arquivo": ("e.csv", b"data;descricao;valor\n", "text/csv")},
        headers=cabecalhos(token=None),
    )
    assert resposta.status_code == 401


# --- Listagem ----------------------------------------------------------------


def test_lista_mais_antigos_primeiro():
    importar("data;descricao;valor\n2026-10-09;C;3,00\n2026-10-01;A;1,00\n2026-10-05;B;2,00\n")

    descricoes = [i["descricao"] for i in listar().json()]

    assert descricoes == ["A", "B", "C"]


def test_lista_vazia():
    assert listar().json() == []


def test_filtro_em_aberto():
    itens = importar(CSV_PONTO_E_VIRGULA).json()["itens"]
    lancamento = aprovado()
    criar_orcamento(lancamento)
    conciliar(lancamento.id, itens[0]["id"])

    em_aberto = listar(em_aberto="true").json()
    conciliados = listar(em_aberto="false").json()
    todos = listar().json()

    assert [i["id"] for i in em_aberto] == [itens[1]["id"]]
    assert [i["id"] for i in conciliados] == [itens[0]["id"]]
    assert conciliados[0]["conciliado_com"] == lancamento.id
    assert len(todos) == 2


# --- Conciliação com item do extrato -----------------------------------------


def criar_orcamento(*lancamentos):
    orcamento = Orcamento(
        id="orcamento-1",
        projeto_id="projeto-1",
        valor_total=1000,
        data_inicio=date(2026, 1, 1),
        data_fim=date(2026, 12, 31),
        categorias_despesa=["materiais"],
        lancamentos=list(lancamentos),
    )
    _orcamentos.append(orcamento)
    return orcamento


def aprovado(valor=200):
    return Lancamento(valor=valor, status=StatusLancamento.APROVADO)


def conciliar(lancamento_id, referencia):
    return client.patch(
        f"/lancamentos/{lancamento_id}/conciliar",
        json={"referencia_extrato": referencia},
        headers=cabecalhos(),
    )


def item_do_extrato(item_id):
    return next(i for i in listar().json() if i["id"] == item_id)


def test_conciliar_com_id_do_item_marca_o_item():
    item = importar(CSV_PONTO_E_VIRGULA).json()["itens"][0]
    lancamento = aprovado()
    criar_orcamento(lancamento)

    resposta = conciliar(lancamento.id, item["id"])

    assert resposta.status_code == 200
    assert resposta.json()["referencia_extrato"] == item["id"]
    assert item_do_extrato(item["id"])["conciliado_com"] == lancamento.id


def test_item_ja_conciliado_com_outro_lancamento_e_recusado():
    item = importar(CSV_PONTO_E_VIRGULA).json()["itens"][0]
    um, outro = aprovado(), aprovado()
    criar_orcamento(um, outro)
    conciliar(um.id, item["id"])

    resposta = conciliar(outro.id, item["id"])

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Item do extrato já conciliado com outro lançamento."
    assert outro.conciliado is False
    assert item_do_extrato(item["id"])["conciliado_com"] == um.id


def test_repetir_a_conciliacao_do_mesmo_par_e_idempotente():
    item = importar(CSV_PONTO_E_VIRGULA).json()["itens"][0]
    lancamento = aprovado()
    criar_orcamento(lancamento)
    conciliar(lancamento.id, item["id"])

    resposta = conciliar(lancamento.id, item["id"])

    assert resposta.status_code == 200
    assert item_do_extrato(item["id"])["conciliado_com"] == lancamento.id


def test_referencia_livre_continua_aceita_e_nao_mexe_no_extrato():
    importar(CSV_PONTO_E_VIRGULA)
    lancamento = aprovado()
    criar_orcamento(lancamento)

    resposta = conciliar(lancamento.id, "EXT-2026-10-001")

    assert resposta.status_code == 200
    assert all(i["conciliado_com"] is None for i in listar().json())


def test_lancamento_nao_aprovado_nao_prende_o_item():
    item = importar(CSV_PONTO_E_VIRGULA).json()["itens"][0]
    pendente = Lancamento(valor=10, status=StatusLancamento.PENDENTE)
    criar_orcamento(pendente)

    resposta = conciliar(pendente.id, item["id"])

    assert resposta.status_code == 409
    assert item_do_extrato(item["id"])["conciliado_com"] is None


def test_lancamento_inexistente_nao_prende_o_item():
    item = importar(CSV_PONTO_E_VIRGULA).json()["itens"][0]
    criar_orcamento(aprovado())

    resposta = conciliar("nao-existe", item["id"])

    assert resposta.status_code == 404
    assert item_do_extrato(item["id"])["conciliado_com"] is None
