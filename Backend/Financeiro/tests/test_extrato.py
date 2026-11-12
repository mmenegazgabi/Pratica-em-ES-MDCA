"""US-05 — extrato bancário: POST/GET /extrato e conciliação com item do extrato.

Todos os testes rodam duas vezes: com os dados em memória e no PostgreSQL de teste
(``TEST_DATABASE_URL``, fixture ``banco_financeiro``; sem ela, a rodada do banco é
pulada). Os lançamentos são criados pela API, do jeito que as telas fazem.
"""

import itertools
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.extrato import caixa_do_extrato
from Financeiro.main import app
from Financeiro.notificacoes import caixa_de_notificacoes
from Financeiro.persistencia import AUDITORIA_EM_MEMORIA
from Financeiro.projetos import _projetos
from Financeiro.rascunhos import caixa_de_rascunhos
from Financeiro.routers.comprovantes import obter_armazenamento
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

client = TestClient(app)


def cabecalhos(papel="voluntario_financeiro", token=TOKEN, usuario="vera"):
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if papel is not None:
        headers["X-Papel-Usuario"] = papel
    if usuario is not None:
        headers["X-Usuario-Id"] = usuario
    return headers


def esvaziar_memoria() -> None:
    """O equivalente a reiniciar a API: some tudo o que estava só no processo."""
    _projetos.clear()
    _orcamentos.clear()
    caixa_de_notificacoes.limpar()
    caixa_de_rascunhos.limpar()
    caixa_do_extrato.limpar()
    AUDITORIA_EM_MEMORIA.clear()


@pytest.fixture(autouse=True, params=["memoria", "banco"])
def armazenamento(request, monkeypatch):
    """Devolve o motor do banco de teste na rodada do banco e None na da memória."""
    motor = None
    if request.param == "banco":
        motor = request.getfixturevalue("banco_financeiro")
    else:
        esvaziar_memoria()
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    app.dependency_overrides[obter_armazenamento] = lambda: ArmazenamentoEmMemoria()
    yield motor
    app.dependency_overrides.pop(obter_armazenamento, None)
    esvaziar_memoria()


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
    lancamento_id = aprovado()
    conciliar(lancamento_id, itens[0]["id"])

    em_aberto = listar(em_aberto="true").json()
    conciliados = listar(em_aberto="false").json()
    todos = listar().json()

    assert [i["id"] for i in em_aberto] == [itens[1]["id"]]
    assert [i["id"] for i in conciliados] == [itens[0]["id"]]
    assert conciliados[0]["conciliado_com"] == lancamento_id
    assert len(todos) == 2


# --- Conciliação com item do extrato -----------------------------------------


_projetos_criados = itertools.count(1)


def criar_orcamento():
    coordenacao = cabecalhos("coordenacao", usuario="luana")
    nome = f"Leitura {next(_projetos_criados)}"
    projeto = client.post("/projetos", json={"nome": nome}, headers=coordenacao)
    assert projeto.status_code == 201, projeto.text
    resposta = client.post(
        "/orcamentos",
        json={
            "projeto_id": projeto.json()["id"],
            "valor_total": 1000,
            "data_inicio": "2026-01-01",
            "data_fim": "2026-12-31",
            "categorias_despesa": ["materiais"],
        },
        headers=coordenacao,
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def lancar(orcamento_id, valor="200.00", aprovar=True):
    resposta = client.post(
        "/lancamentos",
        data={
            "orcamento_id": orcamento_id,
            "valor": valor,
            "descricao": "Tinta",
            "categoria": "materiais",
            "data_despesa": "2026-05-15",
        },
        files={"comprovante": ("nota.jpg", JPEG, "image/jpeg")},
        headers=cabecalhos("educador", usuario="marcos"),
    )
    assert resposta.status_code == 201, resposta.text
    lancamento_id = resposta.json()["id"]
    if aprovar:
        aprovado = client.patch(
            f"/lancamentos/{lancamento_id}/aprovar", headers=cabecalhos("coordenacao", usuario="luana")
        )
        assert aprovado.status_code == 200, aprovado.text
    return lancamento_id


def aprovado():
    return lancar(criar_orcamento())


def conciliar(lancamento_id, referencia):
    return client.patch(
        f"/lancamentos/{lancamento_id}/conciliar",
        json={"referencia_extrato": referencia},
        headers=cabecalhos(),
    )


def lancamento(lancamento_id):
    return client.get(f"/lancamentos/{lancamento_id}", headers=cabecalhos("coordenacao")).json()


def item_do_extrato(item_id):
    return next(i for i in listar().json() if i["id"] == item_id)


def trilha(**params):
    resposta = client.get("/auditoria", params=params, headers=cabecalhos("coordenacao", usuario="luana"))
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["itens"]


def test_conciliar_com_id_do_item_marca_o_item():
    item = importar(CSV_PONTO_E_VIRGULA).json()["itens"][0]
    lancamento_id = aprovado()

    resposta = conciliar(lancamento_id, item["id"])

    assert resposta.status_code == 200
    assert resposta.json()["referencia_extrato"] == item["id"]
    assert item_do_extrato(item["id"])["conciliado_com"] == lancamento_id


def test_item_ja_conciliado_com_outro_lancamento_e_recusado():
    item = importar(CSV_PONTO_E_VIRGULA).json()["itens"][0]
    orcamento_id = criar_orcamento()
    um, outro = lancar(orcamento_id), lancar(orcamento_id)
    conciliar(um, item["id"])

    resposta = conciliar(outro, item["id"])

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Item do extrato já conciliado com outro lançamento."
    assert lancamento(outro)["conciliado"] is False
    assert item_do_extrato(item["id"])["conciliado_com"] == um


def test_repetir_a_conciliacao_do_mesmo_par_e_idempotente():
    item = importar(CSV_PONTO_E_VIRGULA).json()["itens"][0]
    lancamento_id = aprovado()
    conciliar(lancamento_id, item["id"])

    resposta = conciliar(lancamento_id, item["id"])

    assert resposta.status_code == 200
    assert item_do_extrato(item["id"])["conciliado_com"] == lancamento_id
    assert [e["codigo"] for e in trilha(acao="conciliar_lancamento")] == ["conciliar_lancamento"]


def test_lancamento_ja_conciliado_nao_prende_outro_item():
    um, outro = importar(CSV_PONTO_E_VIRGULA).json()["itens"]
    lancamento_id = aprovado()
    conciliar(lancamento_id, um["id"])

    resposta = conciliar(lancamento_id, outro["id"])

    assert resposta.status_code == 409
    assert item_do_extrato(outro["id"])["conciliado_com"] is None


def test_referencia_livre_continua_aceita_e_nao_mexe_no_extrato():
    importar(CSV_PONTO_E_VIRGULA)
    lancamento_id = aprovado()

    resposta = conciliar(lancamento_id, "EXT-2026-10-001")

    assert resposta.status_code == 200
    assert all(i["conciliado_com"] is None for i in listar().json())
    [evento] = trilha(acao="conciliar_lancamento")
    assert "item_extrato_id" not in evento["detalhes"]


def test_lancamento_nao_aprovado_nao_prende_o_item():
    item = importar(CSV_PONTO_E_VIRGULA).json()["itens"][0]
    pendente = lancar(criar_orcamento(), aprovar=False)

    resposta = conciliar(pendente, item["id"])

    assert resposta.status_code == 409
    assert item_do_extrato(item["id"])["conciliado_com"] is None


def test_lancamento_inexistente_nao_prende_o_item():
    item = importar(CSV_PONTO_E_VIRGULA).json()["itens"][0]

    resposta = conciliar("nao-existe", item["id"])

    assert resposta.status_code == 404
    assert item_do_extrato(item["id"])["conciliado_com"] is None


# --- Auditoria (T-34) ----------------------------------------------------------


def test_importacao_vai_para_a_trilha_e_reimportar_nao():
    importar(CSV_PONTO_E_VIRGULA)
    importar(CSV_PONTO_E_VIRGULA)
    importar("data;descricao;valor\n2026-10-05;PIX recebido doação;1500,00\n2026-10-07;Novo;1,00\n")

    eventos = trilha(acao="importar_extrato")

    assert [(e["acao"], e["alvo"], e["quem"]) for e in eventos] == [
        ("Importou extrato bancário", "1 item novo · 1 repetido", "vera"),
        ("Importou extrato bancário", "2 itens novos", "vera"),
    ]
    assert eventos[0]["detalhes"] == {"importados": 1, "ignorados_repetidos": 1}
    assert eventos[0]["alvo_tipo"] == "extrato"


def test_importacao_invalida_ou_negada_nao_grava_na_trilha_de_importacao():
    importar("data;descricao;valor\n2026-10-05;A;x\n")
    importar(CSV_PONTO_E_VIRGULA, "educador")

    assert trilha(acao="importar_extrato") == []


def test_conciliacao_com_item_registra_o_item_na_trilha():
    item = importar(CSV_PONTO_E_VIRGULA).json()["itens"][0]
    lancamento_id = aprovado()
    conciliar(lancamento_id, item["id"])

    [evento] = trilha(acao="conciliar_lancamento")

    assert evento["alvo_id"] == lancamento_id
    assert evento["detalhes"]["item_extrato_id"] == item["id"]
    assert evento["detalhes"]["referencia_extrato"] == item["id"]


# --- Só no banco ----------------------------------------------------------------


def _so_no_banco(motor):
    if motor is None:
        pytest.skip("só no PostgreSQL")


def test_extrato_e_ligacao_ficam_gravados_e_sobrevivem_a_reinicio(armazenamento):
    _so_no_banco(armazenamento)
    itens = importar(CSV_PONTO_E_VIRGULA).json()["itens"]
    lancamento_id = aprovado()
    conciliar(lancamento_id, itens[1]["id"])
    antes = listar().json()

    esvaziar_memoria()

    assert listar().json() == antes
    with armazenamento.connect() as conexao:
        linhas = conexao.execute(
            sa.text("SELECT id, valor, conciliado_com FROM extrato_itens ORDER BY data")
        ).all()
    assert [(l.id, str(l.valor), l.conciliado_com) for l in linhas] == [
        (itens[0]["id"], "1500.00", None),
        (itens[1]["id"], "-250.50", lancamento_id),
    ]


def test_importacoes_ao_mesmo_tempo_nao_duplicam(armazenamento):
    _so_no_banco(armazenamento)
    texto = "data;descricao;valor\n2026-10-05;PIX;10,00\n2026-10-05;PIX;10,00\n"

    with ThreadPoolExecutor(max_workers=4) as executor:
        respostas = list(executor.map(lambda _: importar(texto), range(4)))

    assert sorted(r.json()["importados"] for r in respostas) == [0, 0, 0, 2]
    assert len(listar().json()) == 2


def test_dois_lancamentos_ao_mesmo_tempo_no_mesmo_item_so_um_liga(armazenamento):
    _so_no_banco(armazenamento)
    item = importar(CSV_PONTO_E_VIRGULA).json()["itens"][0]
    um, outro = aprovado(), aprovado()  # orçamentos diferentes: não esperam um pelo outro

    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(lambda l: conciliar(l, item["id"]), [um, outro]))

    assert sorted(r.status_code for r in respostas) == [200, 400]
    vencedor = um if respostas[0].status_code == 200 else outro
    perdedor = outro if vencedor == um else um
    assert item_do_extrato(item["id"])["conciliado_com"] == vencedor
    assert lancamento(perdedor)["conciliado"] is False


def test_falha_ao_ligar_desfaz_a_conciliacao(armazenamento, monkeypatch):
    """A ligação vai na mesma transação: se ela falha, o lançamento não fica conciliado."""
    _so_no_banco(armazenamento)
    from Financeiro.extrato import ItemJaConciliado
    from Financeiro.persistencia import RepositorioBanco

    def falhar(self, item_id, lancamento_id):
        raise ItemJaConciliado()

    monkeypatch.setattr(RepositorioBanco, "vincular_item_extrato", falhar)
    item = importar(CSV_PONTO_E_VIRGULA).json()["itens"][0]
    lancamento_id = aprovado()

    assert conciliar(lancamento_id, item["id"]).status_code == 400
    assert lancamento(lancamento_id)["conciliado"] is False
    assert item_do_extrato(item["id"])["conciliado_com"] is None
    assert trilha(acao="conciliar_lancamento") == []
