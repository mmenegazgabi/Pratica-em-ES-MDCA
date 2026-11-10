"""Critérios de aceitação da exportação da US-06 (T-27): os arquivos batem com a origem.

Os testes do serviço (T-24) e da rota (T-25) ficam em ``test_relatorio_prestacao.py`` e
``test_relatorio_endpoint.py``. Aqui cada critério é verificado como um percurso
completo: os dados são gravados onde a API os guarda (projetos e orçamentos com os
lançamentos), o arquivo é baixado por ``GET /relatorios/prestacao-contas`` e o
conteúdo é lido de volta do PDF (pypdf) e do XLSX (openpyxl):

1. Os totais do PDF (orçado, realizado e saldo) são os calculados aqui direto dos
   dados gravados, sem passar pelo serviço do relatório.
2. A planilha abre sem erro e tem as mesmas colunas e as mesmas linhas do PDF.
3. Período sem lançamentos aprovados gera os dois arquivos sem erro, com a tabela vazia.
"""

import io
import re
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pypdf import PdfReader

from Financeiro.comprovantes import TIPOS_ACEITOS, gerar_chave
from Financeiro.main import app
from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
from Financeiro.projetos import _projetos, registrar_projeto
from Financeiro.relatorio_prestacao import (
    CNPJ_INSTITUICAO_PADRAO,
    NOME_INSTITUICAO_PADRAO,
    COLUNAS_LANCAMENTOS,
    ROTULO_TOTAL,
    SEM_LANCAMENTOS,
    TITULO,
    TITULO_LANCAMENTOS,
    TITULO_RESUMO,
    formatar_data,
    formatar_valor,
)
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"
ROTA = "/relatorios/prestacao-contas"
INICIO = date(2026, 1, 1)
FIM = date(2026, 6, 30)
CENTAVO = Decimal("0.01")
# Relógio fixo: lançamentos da mesma data desempatam por criado_em, sem depender da resolução do relógio.
CRIADO_EM = datetime(2026, 1, 1, tzinfo=timezone.utc)

# Início do rodapé que o PDF desenha em cada página.
RODAPE = f"{NOME_INSTITUICAO_PADRAO} · CNPJ {CNPJ_INSTITUICAO_PADRAO} · {TITULO} · "

client = TestClient(app)


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    monkeypatch.delenv("FINANCEIRO_URL_PUBLICA", raising=False)
    monkeypatch.delenv("MDCA_INSTITUICAO_NOME", raising=False)
    monkeypatch.delenv("MDCA_INSTITUICAO_CNPJ", raising=False)
    _orcamentos.clear()
    _projetos.clear()
    yield
    _orcamentos.clear()
    _projetos.clear()


def lancamento(valor, dia, categoria="Alimentação", descricao="Despesa", status=StatusLancamento.APROVADO, comprovante=True, ordem=0):
    return Lancamento(
        valor=valor,
        status=status,
        data_despesa=dia,
        categoria=categoria,
        descricao=descricao,
        comprovante_chave=gerar_chave(TIPOS_ACEITOS["jpg"]) if comprovante else None,
        criado_em=CRIADO_EM + timedelta(seconds=ordem),
    )


@pytest.fixture
def semear():
    """Projeto com valores quebrados em centavos e lançamentos que não podem entrar."""
    projeto = registrar_projeto("Semear Contraturno")
    outro = registrar_projeto("Horta Comunitária")
    _orcamentos.extend([
        Orcamento(
            id="o-2026",
            projeto_id=projeto.id,
            valor_total=15000.55,
            data_inicio=date(2026, 1, 1),
            data_fim=date(2026, 12, 31),
            categorias_despesa=["Alimentação", "Transporte", "Material"],
            lancamentos=[
                lancamento(1200, date(2026, 4, 2), "Transporte", "Fretamento"),
                lancamento(486.9, date(2026, 3, 12), "Alimentação", "Lanche da oficina"),
                lancamento(0.1, date(2026, 2, 1), "Material", "=SOMA(A1:A9) clipes", ordem=1),
                lancamento(0.2, date(2026, 2, 1), "Material", "Elásticos", comprovante=False, ordem=2),
                lancamento(33.33, date(2026, 6, 30), "Material", "Último dia do período"),
                lancamento(300, date(2026, 5, 5), descricao="Pendente", status=StatusLancamento.PENDENTE),
                lancamento(150, date(2026, 5, 6), descricao="Rejeitado", status=StatusLancamento.REJEITADO),
                lancamento(77.77, date(2026, 7, 1), "Transporte", "Depois do período"),
                lancamento(10, None, descricao="Sem data"),
            ],
        ),
        # Vigência cruza o início do período: entra no orçado.
        Orcamento(
            id="o-2025",
            projeto_id=projeto.id,
            valor_total=2000.45,
            data_inicio=date(2025, 7, 1),
            data_fim=date(2026, 1, 31),
            categorias_despesa=["Alimentação"],
            lancamentos=[
                lancamento(250.1, date(2026, 1, 1), descricao="Primeiro dia do período"),
                lancamento(90, date(2025, 12, 31), descricao="Antes do período"),
            ],
        ),
        # Vigência fora do período: não entra no orçado.
        Orcamento(
            id="o-2027",
            projeto_id=projeto.id,
            valor_total=9999,
            data_inicio=date(2027, 1, 1),
            data_fim=date(2027, 12, 31),
            categorias_despesa=["Alimentação"],
        ),
        Orcamento(
            id="o-horta",
            projeto_id=outro.id,
            valor_total=5000,
            data_inicio=date(2026, 1, 1),
            data_fim=date(2026, 12, 31),
            categorias_despesa=["Alimentação"],
            lancamentos=[lancamento(999, date(2026, 2, 2), descricao="Outro projeto")],
        ),
    ])
    return projeto


def baixar(projeto_id, formato, inicio=INICIO, fim=FIM):
    resposta = client.get(
        ROTA,
        params={"projeto_id": projeto_id, "data_inicio": inicio.isoformat(), "data_fim": fim.isoformat(), "formato": formato},
        headers={"Authorization": f"Bearer {TOKEN}", "X-Papel-Usuario": "coordenacao"},
    )
    assert resposta.status_code == 200, resposta.text
    return resposta.content


# --- Valores direto da origem -----------------------------------------------------


def centavos(valor) -> Decimal:
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def totais_da_origem(projeto_id, inicio, fim):
    """Orçado, realizado e saldo somados a partir do que está gravado, sem o serviço do relatório."""
    do_projeto = [o for o in _orcamentos if o.projeto_id == projeto_id]
    orcado = sum(
        (centavos(o.valor_total) for o in do_projeto if o.data_inicio <= fim and o.data_fim >= inicio),
        Decimal(0),
    )
    realizado = sum((centavos(l.valor) for l in aprovados_da_origem(projeto_id, inicio, fim)), Decimal(0))
    return orcado, realizado, orcado - realizado


def aprovados_da_origem(projeto_id, inicio, fim):
    return [
        l
        for o in _orcamentos
        if o.projeto_id == projeto_id
        for l in o.lancamentos
        if l.status == StatusLancamento.APROVADO and l.data_despesa is not None and inicio <= l.data_despesa <= fim
    ]


# --- Leitura do PDF ----------------------------------------------------------------


def reais(texto: str) -> Decimal:
    """"R$ 1.234,56" -> Decimal("1234.56")."""
    numero = texto.replace("R$", "").strip().replace(".", "").replace(",", ".")
    return Decimal(numero)


def linhas_pdf(conteudo: bytes):
    """Linhas de texto de todas as páginas, sem o rodapé e o número de página."""
    linhas = []
    for pagina in PdfReader(io.BytesIO(conteudo)).pages:
        for linha in pagina.extract_text().splitlines():
            linha = linha.strip()
            if linha and not linha.startswith(RODAPE) and not re.fullmatch(r"Página \d+", linha):
                linhas.append(linha)
    return linhas


def resumo_pdf(linhas):
    """{"Orçado": Decimal, ...} lido da seção de resumo do PDF."""
    secao = linhas[linhas.index(TITULO_RESUMO) + 1 : linhas.index(TITULO_LANCAMENTOS)]
    return {rotulo: reais(valor) for rotulo, valor in zip(secao[::2], secao[1::2])}


def tabela_pdf(linhas):
    """Cabeçalho e linhas da tabela de lançamentos do PDF, célula a célula.

    O cabeçalho da tabela se repete no topo de cada página e sai do resultado. Um
    link longo pode quebrar em mais de uma linha: os pedaços são juntados.
    """
    corpo = linhas[linhas.index(TITULO_LANCAMENTOS) + 1 :]
    n = len(COLUNAS_LANCAMENTOS)
    cabecalho = corpo[:n]
    resto = corpo[n:]
    while True:
        try:
            i = next(i for i in range(len(resto)) if resto[i : i + n] == cabecalho)
        except StopIteration:
            break
        resto = resto[:i] + resto[i + n :]

    linhas_da_tabela = []
    i = 0
    while i < len(resto) and re.fullmatch(r"\d{2}/\d{2}/\d{4}", resto[i]):
        dia, categoria, descricao, valor = resto[i : i + 4]
        i += 4
        comprovante = []
        while i < len(resto) and not re.fullmatch(r"\d{2}/\d{2}/\d{4}", resto[i]) and resto[i] != ROTULO_TOTAL:
            comprovante.append(resto[i])
            i += 1
        linhas_da_tabela.append((dia, categoria, descricao, valor, "".join(comprovante)))
    return cabecalho, linhas_da_tabela, resto[i:]


# --- Leitura do XLSX ---------------------------------------------------------------


def abrir_xlsx(conteudo: bytes):
    """Abre a planilha como um programa de planilhas abriria: zip íntegro e pasta legível."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
        assert pacote.testzip() is None
        assert {"[Content_Types].xml", "xl/workbook.xml"} <= set(pacote.namelist())
    return load_workbook(io.BytesIO(conteudo))


def celula_como_no_pdf(valor) -> str:
    if isinstance(valor, datetime):
        return formatar_data(valor.date())
    if isinstance(valor, (int, float)):
        return formatar_valor(centavos(valor))
    return "" if valor is None else str(valor)


def tabela_xlsx(ws):
    """Cabeçalho, linhas da tabela de lançamentos e o que vem depois, com o texto que o PDF mostra."""
    linhas = [tuple(c.value for c in linha[: len(COLUNAS_LANCAMENTOS)]) for linha in ws.iter_rows()]
    inicio = next(i for i, linha in enumerate(linhas) if linha == COLUNAS_LANCAMENTOS)
    dados, depois = [], []
    for linha in linhas[inicio + 1 :]:
        if isinstance(linha[0], datetime) and not depois:
            dados.append(tuple(celula_como_no_pdf(v) for v in linha))
        else:
            depois.append(tuple(celula_como_no_pdf(v) for v in linha if v is not None))
    return linhas[inicio], dados, depois


def resumo_xlsx(ws):
    linhas = [(linha[0].value, linha[1].value) for linha in ws.iter_rows(max_col=2)]
    inicio = linhas.index((TITULO_RESUMO, None)) + 1
    return {rotulo: centavos(valor) for rotulo, valor in linhas[inicio : inicio + 3]}


# --- Critério 1: totais do PDF batem com a origem --------------------------------


def test_totais_do_pdf_batem_com_os_valores_gravados(semear):
    orcado, realizado, saldo = totais_da_origem(semear.id, INICIO, FIM)
    linhas = linhas_pdf(baixar(semear.id, "pdf"))

    # Conferência à mão, para o próprio teste não estar errado do mesmo jeito que o serviço.
    assert (orcado, realizado, saldo) == (Decimal("17001.00"), Decimal("1970.63"), Decimal("15030.37"))
    assert resumo_pdf(linhas) == {"Orçado": orcado, "Realizado": realizado, "Saldo": saldo}


def test_total_da_tabela_do_pdf_e_a_soma_das_linhas_e_o_realizado(semear):
    _, realizado, _ = totais_da_origem(semear.id, INICIO, FIM)
    _, linhas, depois = tabela_pdf(linhas_pdf(baixar(semear.id, "pdf")))

    assert sum(reais(valor) for _, _, _, valor, _ in linhas) == realizado
    assert depois == [ROTULO_TOTAL, formatar_valor(realizado)]


def test_pdf_lista_exatamente_os_lancamentos_aprovados_gravados_no_periodo(semear):
    origem = sorted(aprovados_da_origem(semear.id, INICIO, FIM), key=lambda l: (l.data_despesa, l.criado_em))
    _, linhas, _ = tabela_pdf(linhas_pdf(baixar(semear.id, "pdf")))

    assert [(dia, categoria, descricao, valor) for dia, categoria, descricao, valor, _ in linhas] == [
        (formatar_data(l.data_despesa), l.categoria, l.descricao, formatar_valor(centavos(l.valor))) for l in origem
    ]
    assert [link for *_, link in linhas] == [
        f"http://testserver/{l.comprovante_chave}" if l.comprovante_chave else "Sem comprovante" for l in origem
    ]


def test_totais_da_planilha_batem_com_os_valores_gravados(semear):
    orcado, realizado, saldo = totais_da_origem(semear.id, INICIO, FIM)
    ws = abrir_xlsx(baixar(semear.id, "xlsx")).active

    assert resumo_xlsx(ws) == {"Orçado": orcado, "Realizado": realizado, "Saldo": saldo}


@pytest.mark.parametrize("inicio, fim, esperado", [
    (date(2026, 1, 1), date(2026, 1, 1), ("17001.00", "250.10")),  # um dia só, na borda do período
    (date(2026, 2, 1), date(2026, 3, 31), ("15000.55", "487.20")),  # só o orçamento de 2026 cruza
    (date(2025, 12, 1), date(2026, 12, 31), ("17001.00", "2138.40")),  # pega o lançamento de antes e o de depois
])
def test_totais_batem_com_a_origem_em_outros_periodos(semear, inicio, fim, esperado):
    orcado, realizado, saldo = totais_da_origem(semear.id, inicio, fim)
    assert (orcado, realizado) == tuple(Decimal(v) for v in esperado)
    pdf = resumo_pdf(linhas_pdf(baixar(semear.id, "pdf", inicio, fim)))
    xlsx = resumo_xlsx(abrir_xlsx(baixar(semear.id, "xlsx", inicio, fim)).active)

    assert pdf == xlsx == {"Orçado": orcado, "Realizado": realizado, "Saldo": saldo}


def test_mudanca_na_origem_aparece_no_proximo_arquivo(semear):
    """O arquivo é gerado na hora: uma aprovação nova muda os totais exportados."""
    antes = resumo_pdf(linhas_pdf(baixar(semear.id, "pdf")))
    pendente = next(l for l in _orcamentos[0].lancamentos if l.status == StatusLancamento.PENDENTE)
    _orcamentos[0].aprovar_lancamento(pendente.id)
    depois = resumo_pdf(linhas_pdf(baixar(semear.id, "pdf")))

    assert depois["Realizado"] == antes["Realizado"] + Decimal("300.00")
    assert depois["Saldo"] == antes["Saldo"] - Decimal("300.00")
    assert depois == dict(zip(("Orçado", "Realizado", "Saldo"), totais_da_origem(semear.id, INICIO, FIM)))


# --- Critério 2: planilha abre e tem as mesmas colunas e linhas do PDF ------------


def test_planilha_abre_corretamente(semear):
    wb = abrir_xlsx(baixar(semear.id, "xlsx"))
    ws = wb.active

    assert wb.sheetnames == [TITULO]
    assert ws.cell(1, 1).value == TITULO
    assert ws.max_column == len(COLUNAS_LANCAMENTOS)
    assert not any(c.data_type == "f" for linha in ws.iter_rows() for c in linha)
    formula = next(c for linha in ws.iter_rows() for c in linha if c.value == "=SOMA(A1:A9) clipes")
    assert formula.data_type == "s"


def test_planilha_tem_as_mesmas_colunas_e_linhas_do_pdf(semear):
    cab_pdf, linhas_do_pdf, depois_pdf = tabela_pdf(linhas_pdf(baixar(semear.id, "pdf")))
    cab_xlsx, linhas_do_xlsx, depois_xlsx = tabela_xlsx(abrir_xlsx(baixar(semear.id, "xlsx")).active)

    assert tuple(cab_pdf) == cab_xlsx == COLUNAS_LANCAMENTOS
    assert len(linhas_do_xlsx) == len(linhas_do_pdf) == len(aprovados_da_origem(semear.id, INICIO, FIM)) == 6
    assert linhas_do_xlsx == linhas_do_pdf
    assert depois_pdf == [ROTULO_TOTAL, depois_xlsx[0][1]]
    assert depois_xlsx == [(ROTULO_TOTAL, formatar_valor(sum(reais(l[3]) for l in linhas_do_pdf)))]


def test_planilha_e_pdf_tem_o_mesmo_resumo(semear):
    pdf = resumo_pdf(linhas_pdf(baixar(semear.id, "pdf")))
    xlsx = resumo_xlsx(abrir_xlsx(baixar(semear.id, "xlsx")).active)

    assert list(pdf) == list(xlsx) == ["Orçado", "Realizado", "Saldo"]
    assert pdf == xlsx


def test_mesmas_linhas_quando_o_pdf_tem_varias_paginas():
    projeto = registrar_projeto("Passe Livre")
    _orcamentos.append(Orcamento(
        id="o-passe",
        projeto_id=projeto.id,
        valor_total=50000,
        data_inicio=INICIO,
        data_fim=FIM,
        categorias_despesa=["Transporte"],
        lancamentos=[lancamento(10 + i * 1.11, date(2026, 1 + i % 6, 1 + i % 28), "Transporte", f"Passagem {i:03d}") for i in range(80)],
    ))
    pdf = baixar(projeto.id, "pdf")
    cab_pdf, linhas_do_pdf, _ = tabela_pdf(linhas_pdf(pdf))
    cab_xlsx, linhas_do_xlsx, _ = tabela_xlsx(abrir_xlsx(baixar(projeto.id, "xlsx")).active)

    assert len(PdfReader(io.BytesIO(pdf)).pages) > 1
    assert tuple(cab_pdf) == cab_xlsx
    assert len(linhas_do_pdf) == len(linhas_do_xlsx) == 80
    assert linhas_do_xlsx == linhas_do_pdf


# --- Critério 3: período sem lançamentos → relatório vazio, sem erro -------------


@pytest.mark.parametrize("inicio, fim", [
    (date(2026, 5, 1), date(2026, 5, 31)),  # só pendente e rejeitado no período
    (date(2026, 7, 2), date(2026, 12, 31)),  # orçamento vigente, nenhum lançamento
])
def test_periodo_sem_lancamentos_gera_pdf_e_planilha_vazios(semear, inicio, fim):
    orcado, realizado, saldo = totais_da_origem(semear.id, inicio, fim)
    linhas = linhas_pdf(baixar(semear.id, "pdf", inicio, fim))
    ws = abrir_xlsx(baixar(semear.id, "xlsx", inicio, fim)).active
    cab_pdf, linhas_do_pdf, depois_pdf = tabela_pdf(linhas)
    cab_xlsx, linhas_do_xlsx, depois_xlsx = tabela_xlsx(ws)

    assert realizado == 0 and saldo == orcado > 0
    assert resumo_pdf(linhas) == resumo_xlsx(ws) == {"Orçado": orcado, "Realizado": Decimal(0), "Saldo": orcado}
    assert tuple(cab_pdf) == cab_xlsx == COLUNAS_LANCAMENTOS
    assert linhas_do_pdf == linhas_do_xlsx == []
    assert depois_pdf == [SEM_LANCAMENTOS]
    assert depois_xlsx == [(SEM_LANCAMENTOS,)]


@pytest.mark.parametrize("formato", ["pdf", "xlsx"])
def test_projeto_sem_orcamento_nem_lancamentos_gera_arquivo_zerado(formato):
    projeto = registrar_projeto("Projeto novo")
    conteudo = baixar(projeto.id, formato)

    if formato == "pdf":
        linhas = linhas_pdf(conteudo)
        assert resumo_pdf(linhas) == {"Orçado": 0, "Realizado": 0, "Saldo": 0}
        assert tabela_pdf(linhas)[1:] == ([], [SEM_LANCAMENTOS])
    else:
        ws = abrir_xlsx(conteudo).active
        assert resumo_xlsx(ws) == {"Orçado": 0, "Realizado": 0, "Saldo": 0}
        assert tabela_xlsx(ws)[1:] == ([], [(SEM_LANCAMENTOS,)])
