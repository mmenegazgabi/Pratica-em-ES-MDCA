"""T-24 · US-06 — Serviço de relatório de prestação de contas (PDF e XLSX).

Os testes abrem os arquivos gerados de verdade: o PDF com pypdf (texto e links)
e o XLSX com openpyxl (células e hiperlinks). Cada bloco é um critério do card.
"""

import io
import re
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from Financeiro.comprovantes import TIPOS_ACEITOS, gerar_chave
from Financeiro.dashboard import resumo_por_projeto
from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
from Financeiro.projetos import Projeto
from Financeiro.relatorio_prestacao import (
    CNPJ_INSTITUICAO_PADRAO,
    COLUNAS_LANCAMENTOS,
    NOME_INSTITUICAO_PADRAO,
    ROTULO_TOTAL,
    SEM_COMPROVANTE,
    SEM_LANCAMENTOS,
    TITULO,
    TITULO_LANCAMENTOS,
    TITULO_RESUMO,
    Instituicao,
    RelatorioInvalido,
    formatar_cnpj,
    formatar_data,
    formatar_valor,
    gerar_pdf,
    gerar_xlsx,
    instituicao_configurada,
    linhas_do_cabecalho,
    linhas_do_resumo,
    linhas_dos_lancamentos,
    montar_relatorio,
    nome_do_arquivo,
)

API = "https://api.mdca.teste"
INICIO = date(2026, 1, 1)
FIM = date(2026, 6, 30)
GERADO_EM = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
MDCA = Instituicao(nome=NOME_INSTITUICAO_PADRAO, cnpj=CNPJ_INSTITUICAO_PADRAO)


# --- Dados de exemplo ------------------------------------------------------------


def lancamento(valor, dia, categoria="Alimentação", descricao="Despesa", status=StatusLancamento.APROVADO, comprovante=True):
    return Lancamento(
        valor=valor,
        status=status,
        data_despesa=dia,
        categoria=categoria,
        descricao=descricao,
        comprovante_chave=gerar_chave(TIPOS_ACEITOS["jpg"]) if comprovante else None,
    )


@pytest.fixture
def semear():
    return Projeto(nome="Semear Contraturno")


@pytest.fixture
def orcamentos(semear):
    outro = Projeto(nome="Horta")
    no_periodo = Orcamento(
        id="o-2026",
        projeto_id=semear.id,
        valor_total=15000,
        data_inicio=date(2026, 1, 1),
        data_fim=date(2026, 12, 31),
        categorias_despesa=["Alimentação", "Transporte"],
        lancamentos=[
            lancamento(1200, date(2026, 4, 2), "Transporte", "Fretamento para saída pedagógica"),
            lancamento(486.9, date(2026, 3, 12), "Alimentação", "Lanche da oficina"),
            lancamento(300, date(2026, 5, 5), descricao="Pendente não entra", status=StatusLancamento.PENDENTE),
            lancamento(150, date(2026, 5, 6), descricao="Rejeitado não entra", status=StatusLancamento.REJEITADO),
            lancamento(77.77, date(2026, 8, 1), "Transporte", "Fora do período não entra"),
            lancamento(10, None, descricao="Sem data não entra"),
        ],
    )
    # Vigência cruza o período: entra no orçado.
    anterior = Orcamento(
        id="o-2025",
        projeto_id=semear.id,
        valor_total=2000,
        data_inicio=date(2025, 7, 1),
        data_fim=date(2026, 1, 31),
        categorias_despesa=["Alimentação"],
        lancamentos=[lancamento(250.1, date(2026, 1, 15), descricao="Ceia de encerramento")],
    )
    # Vigência fora do período: não entra no orçado.
    futuro = Orcamento(
        id="o-2027",
        projeto_id=semear.id,
        valor_total=9999,
        data_inicio=date(2027, 1, 1),
        data_fim=date(2027, 12, 31),
        categorias_despesa=["Alimentação"],
    )
    de_outro_projeto = Orcamento(
        id="o-horta",
        projeto_id=outro.id,
        valor_total=5000,
        data_inicio=date(2026, 1, 1),
        data_fim=date(2026, 12, 31),
        categorias_despesa=["Alimentação"],
        lancamentos=[lancamento(999, date(2026, 2, 2), descricao="Outro projeto não entra")],
    )
    return [no_periodo, anterior, futuro, de_outro_projeto]


def relatorio(projeto, orcamentos, inicio=INICIO, fim=FIM, **extra):
    extra.setdefault("instituicao", MDCA)
    extra.setdefault("gerado_em", GERADO_EM)
    return montar_relatorio(projeto, orcamentos, inicio, fim, url_base=API, **extra)


# --- Leitura dos arquivos gerados -----------------------------------------------


def _sem_espacos(texto):
    return re.sub(r"\s+", "", texto)


def texto_pdf(conteudo: bytes, rel) -> str:
    """Texto do corpo do PDF, sem rodapé, número de página e cabeçalho repetido da tabela."""
    leitor = PdfReader(io.BytesIO(conteudo))
    texto = _sem_espacos("".join(pagina.extract_text() for pagina in leitor.pages))
    rodape = _sem_espacos(f"{rel.instituicao.nome} · CNPJ {rel.instituicao.cnpj} · {TITULO} · {rel.projeto_nome} · {rel.periodo}")
    texto = texto.replace(rodape, "")
    texto = re.sub(r"Página\d+", "", texto)
    colunas = _sem_espacos("".join(COLUNAS_LANCAMENTOS))
    primeira = texto.find(colunas) + len(colunas)
    return texto[:primeira] + texto[primeira:].replace(colunas, "")


def links_pdf(conteudo: bytes) -> set:
    links = set()
    for pagina in PdfReader(io.BytesIO(conteudo)).pages:
        for anotacao in pagina.get("/Annots") or []:
            acao = anotacao.get_object().get("/A") or {}
            if acao.get("/URI"):
                links.add(str(acao["/URI"]))
    return links


def celulas_xlsx(conteudo: bytes):
    return load_workbook(io.BytesIO(conteudo)).active


def texto_xlsx(conteudo: bytes) -> str:
    """Todas as células, na ordem, formatadas como o PDF formata (R$, dd/mm/aaaa)."""
    partes = []
    for linha in celulas_xlsx(conteudo).iter_rows():
        for celula in linha:
            valor = celula.value
            if valor is None:
                continue
            if isinstance(valor, datetime):
                partes.append(formatar_data(valor.date()))
            elif isinstance(valor, (int, float)):
                partes.append(formatar_valor(Decimal(str(valor)).quantize(Decimal("0.01"))))
            else:
                partes.append(str(valor))
    return _sem_espacos("".join(partes))


def links_xlsx(conteudo: bytes) -> set:
    return {c.hyperlink.target for linha in celulas_xlsx(conteudo).iter_rows() for c in linha if c.hyperlink}


def conteudo_esperado(rel) -> str:
    """O que os dois formatos têm que mostrar, montado só a partir dos dados do relatório."""
    partes = [TITULO]
    for rotulo, valor in linhas_do_cabecalho(rel):
        partes += [rotulo, valor]
    partes.append(TITULO_RESUMO)
    for rotulo, valor in linhas_do_resumo(rel):
        partes += [rotulo, formatar_valor(valor)]
    partes += [TITULO_LANCAMENTOS, *COLUNAS_LANCAMENTOS]
    for dia, categoria, descricao, valor, url in linhas_dos_lancamentos(rel):
        partes += [formatar_data(dia), categoria, descricao, formatar_valor(valor), url or SEM_COMPROVANTE]
    partes += [ROTULO_TOTAL, formatar_valor(rel.realizado)] if rel.lancamentos else [SEM_LANCAMENTOS]
    return _sem_espacos("".join(partes))


# --- Critério 1: orçado, realizado, saldo e lançamentos aprovados com links ----


def test_resumo_traz_orcado_realizado_e_saldo_do_periodo(semear, orcamentos):
    rel = relatorio(semear, orcamentos)

    assert rel.orcado == Decimal("17000.00")  # 15000 + 2000 (o de 2027 não cruza o período)
    assert rel.realizado == Decimal("1937.00")  # 1200 + 486,90 + 250,10
    assert rel.saldo == Decimal("15063.00")


def test_so_lancamentos_aprovados_do_projeto_no_periodo_em_ordem_de_data(semear, orcamentos):
    rel = relatorio(semear, orcamentos)

    assert [l.descricao for l in rel.lancamentos] == [
        "Ceia de encerramento",
        "Lanche da oficina",
        "Fretamento para saída pedagógica",
    ]
    assert [l.data_despesa for l in rel.lancamentos] == [date(2026, 1, 15), date(2026, 3, 12), date(2026, 4, 2)]
    assert sum(l.valor for l in rel.lancamentos) == rel.realizado


def test_cada_lancamento_tem_o_link_do_comprovante_na_api(semear, orcamentos):
    rel = relatorio(semear, orcamentos)
    chaves = {l.id: l.comprovante_chave for o in orcamentos for l in o.lancamentos}

    for item in rel.lancamentos:
        assert item.comprovante_url == f"{API}/{chaves[item.id]}"
        assert re.fullmatch(rf"{API}/comprovantes/\d{{4}}/\d{{2}}/[0-9a-f]{{32}}\.jpg", item.comprovante_url)


def test_numeros_iguais_aos_do_dashboard_da_diretoria(semear, orcamentos):
    rel = relatorio(semear, orcamentos)
    [resumo] = resumo_por_projeto([semear], orcamentos, INICIO, FIM)

    assert (float(rel.orcado), float(rel.realizado), float(rel.saldo)) == (resumo.orcado, resumo.realizado, resumo.saldo)


def test_pdf_e_xlsx_mostram_resumo_e_lancamentos_com_links(semear, orcamentos):
    rel = relatorio(semear, orcamentos)
    pdf, xlsx = gerar_pdf(rel), gerar_xlsx(rel)
    esperados = {l.comprovante_url for l in rel.lancamentos}

    for texto in (texto_pdf(pdf, rel), texto_xlsx(xlsx)):
        assert _sem_espacos("OrçadoR$ 17.000,00RealizadoR$ 1.937,00SaldoR$ 15.063,00") in texto
        for item in rel.lancamentos:
            assert _sem_espacos(f"{formatar_data(item.data_despesa)}{item.categoria}{item.descricao}{formatar_valor(item.valor)}{item.comprovante_url}") in texto
        for fora in ("Pendente não entra", "Rejeitado não entra", "Fora do período", "Sem data", "Outro projeto"):
            assert _sem_espacos(fora) not in texto
    assert links_pdf(pdf) == esperados
    assert links_xlsx(xlsx) == esperados


def test_lancamento_aprovado_sem_comprovante_aparece_marcado(semear):
    o = Orcamento(id="o", projeto_id=semear.id, valor_total=100, data_inicio=INICIO, data_fim=FIM,
                  categorias_despesa=["Alimentação"], lancamentos=[lancamento(10, date(2026, 2, 1), comprovante=False)])
    rel = relatorio(semear, [o])
    pdf, xlsx = gerar_pdf(rel), gerar_xlsx(rel)

    assert rel.lancamentos[0].comprovante_url is None
    assert SEM_COMPROVANTE in PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert _sem_espacos(SEM_COMPROVANTE) in texto_xlsx(xlsx)
    assert links_pdf(pdf) == links_xlsx(xlsx) == set()


def test_periodo_sem_lancamentos_aprovados(semear, orcamentos):
    rel = relatorio(semear, orcamentos, date(2026, 6, 1), date(2026, 6, 30))
    pdf, xlsx = gerar_pdf(rel), gerar_xlsx(rel)

    assert rel.lancamentos == ()
    assert rel.realizado == 0
    assert rel.saldo == rel.orcado == Decimal("15000.00")
    assert _sem_espacos(SEM_LANCAMENTOS) in texto_pdf(pdf, rel)
    assert _sem_espacos(SEM_LANCAMENTOS) in texto_xlsx(xlsx)


def test_soma_em_centavos_sem_erro_de_float(semear):
    o = Orcamento(id="o", projeto_id=semear.id, valor_total=0.3, data_inicio=INICIO, data_fim=FIM,
                  categorias_despesa=["Alimentação"],
                  lancamentos=[lancamento(0.1, date(2026, 2, 1)), lancamento(0.2, date(2026, 2, 2))])
    rel = relatorio(semear, [o])

    assert rel.realizado == Decimal("0.30")
    assert rel.saldo == Decimal("0.00")


def test_periodo_invertido_ou_incompleto_e_recusado(semear, orcamentos):
    with pytest.raises(RelatorioInvalido, match="antes do início"):
        relatorio(semear, orcamentos, date(2026, 6, 30), date(2026, 1, 1))
    with pytest.raises(RelatorioInvalido, match="início e o fim"):
        relatorio(semear, orcamentos, None, FIM)


@pytest.mark.parametrize("url_base", ["", "ftp://api", "api.mdca.teste", "javascript:alert(1)"])
def test_url_base_precisa_ser_http(semear, orcamentos, url_base):
    with pytest.raises(RelatorioInvalido, match="url_base"):
        montar_relatorio(semear, orcamentos, INICIO, FIM, url_base=url_base, instituicao=MDCA)


def test_url_base_com_barra_no_fim_nao_duplica_a_barra(semear, orcamentos):
    rel = montar_relatorio(semear, orcamentos, INICIO, FIM, url_base=API + "/", instituicao=MDCA)
    assert all(l.comprovante_url.startswith(f"{API}/comprovantes/") for l in rel.lancamentos)


# --- Critério 2: PDF e XLSX com exatamente os mesmos dados -------------------------


def test_paridade_pdf_e_xlsx_tem_exatamente_o_mesmo_conteudo(semear, orcamentos):
    rel = relatorio(semear, orcamentos)
    pdf, xlsx = gerar_pdf(rel), gerar_xlsx(rel)
    esperado = conteudo_esperado(rel)

    assert texto_xlsx(xlsx) == esperado
    assert texto_pdf(pdf, rel) == esperado
    assert links_pdf(pdf) == links_xlsx(xlsx)


def test_paridade_com_varias_paginas(semear):
    lancamentos = [
        lancamento(10 + i * 1.11, date(2026, 1 + i % 6, 1 + i % 28), "Transporte", f"Passagem escolar número {i:03d} da turma da manhã")
        for i in range(70)
    ]
    o = Orcamento(id="o", projeto_id=semear.id, valor_total=50000, data_inicio=INICIO, data_fim=FIM,
                  categorias_despesa=["Transporte"], lancamentos=lancamentos)
    rel = relatorio(semear, [o])
    pdf, xlsx = gerar_pdf(rel), gerar_xlsx(rel)

    assert len(PdfReader(io.BytesIO(pdf)).pages) > 1
    assert texto_xlsx(xlsx) == texto_pdf(pdf, rel) == conteudo_esperado(rel)
    assert len(links_pdf(pdf)) == len(links_xlsx(xlsx)) == 70


def test_paridade_com_texto_dificil_digitado_pelas_pessoas(semear):
    descricoes = [
        'Cadernos & lápis <kit> "escolar"',
        "Lanche\ncom   quebra de linha",
        "Material 😀 com emoji",
        "=HYPERLINK(\"http://golpe\",\"clique\")",
        "Travessão — aspas “curvas” e reticências…",
    ]
    o = Orcamento(id="o", projeto_id=semear.id, valor_total=1000, data_inicio=INICIO, data_fim=FIM,
                  categorias_despesa=["Alimentação"],
                  lancamentos=[lancamento(1, date(2026, 2, i + 1), descricao=d) for i, d in enumerate(descricoes)])
    rel = relatorio(semear, [o])
    pdf, xlsx = gerar_pdf(rel), gerar_xlsx(rel)

    assert [l.descricao for l in rel.lancamentos] == [
        'Cadernos & lápis <kit> "escolar"',
        "Lanche com quebra de linha",
        "Material ? com emoji",
        "=HYPERLINK(\"http://golpe\",\"clique\")",
        "Travessão — aspas “curvas” e reticências…",
    ]
    assert texto_xlsx(xlsx) == texto_pdf(pdf, rel) == conteudo_esperado(rel)


def test_xlsx_nunca_transforma_texto_em_formula(semear):
    o = Orcamento(id="o", projeto_id=semear.id, valor_total=100, data_inicio=INICIO, data_fim=FIM,
                  categorias_despesa=["=1+1"], lancamentos=[lancamento(5, date(2026, 2, 1), "=1+1", "=SUM(A1:A9)")])
    ws = celulas_xlsx(gerar_xlsx(relatorio(semear, [o])))
    textos = [c for linha in ws.iter_rows() for c in linha if isinstance(c.value, str) and c.value.startswith("=")]

    assert {c.value for c in textos} == {"=1+1", "=SUM(A1:A9)"}
    assert all(c.data_type == "s" for c in textos)


def test_xlsx_guarda_numeros_e_datas_de_verdade(semear, orcamentos):
    """Na planilha os valores são números (dá para somar) e as datas são datas."""
    rel = relatorio(semear, orcamentos)
    ws = celulas_xlsx(gerar_xlsx(rel))
    valores = [c for linha in ws.iter_rows() for c in linha if isinstance(c.value, (int, float))]
    datas = [c for linha in ws.iter_rows() for c in linha if isinstance(c.value, datetime)]

    assert [Decimal(str(c.value)).quantize(Decimal("0.01")) for c in valores] == [
        rel.orcado, rel.realizado, rel.saldo, *(l.valor for l in rel.lancamentos), rel.realizado,
    ]
    assert all("R$" in c.number_format for c in valores)
    assert [c.value.date() for c in datas] == [l.data_despesa for l in rel.lancamentos]


# --- Critério 3: cabeçalho com instituição, CNPJ e período ---------------------------


def test_cabecalho_do_pdf_traz_instituicao_cnpj_e_periodo_antes_do_resumo(semear, orcamentos):
    rel = relatorio(semear, orcamentos)
    texto = texto_pdf(gerar_pdf(rel), rel)
    cabecalho = texto[: texto.index(TITULO_RESUMO)]

    assert _sem_espacos(f"Instituição{NOME_INSTITUICAO_PADRAO}") in cabecalho
    assert _sem_espacos("CNPJ93.459.345/0001-99") in cabecalho
    assert _sem_espacos("Período de referência01/01/2026 a 30/06/2026") in cabecalho
    assert _sem_espacos("ProjetoSemear Contraturno") in cabecalho


def test_cabecalho_do_xlsx_traz_instituicao_cnpj_e_periodo_nas_primeiras_linhas(semear, orcamentos):
    ws = celulas_xlsx(gerar_xlsx(relatorio(semear, orcamentos)))
    topo = {ws.cell(linha, 1).value: ws.cell(linha, 2).value for linha in range(2, 7)}

    assert ws.cell(1, 1).value == TITULO
    assert topo["Instituição"] == NOME_INSTITUICAO_PADRAO
    assert topo["CNPJ"] == "93.459.345/0001-99"
    assert topo["Período de referência"] == "01/01/2026 a 30/06/2026"
    assert topo["Projeto"] == "Semear Contraturno"


def test_cabecalho_repete_no_rodape_de_cada_pagina_do_pdf(semear):
    o = Orcamento(id="o", projeto_id=semear.id, valor_total=50000, data_inicio=INICIO, data_fim=FIM,
                  categorias_despesa=["Transporte"],
                  lancamentos=[lancamento(10, date(2026, 3, 1), "Transporte", f"Item {i}") for i in range(70)])
    paginas = PdfReader(io.BytesIO(gerar_pdf(relatorio(semear, [o])))).pages

    assert len(paginas) > 1
    for pagina in paginas:
        texto = pagina.extract_text()
        assert "CNPJ 93.459.345/0001-99" in texto
        assert "01/01/2026 a 30/06/2026" in texto


def test_metadados_dos_arquivos_identificam_instituicao_e_periodo(semear, orcamentos):
    rel = relatorio(semear, orcamentos)
    meta = PdfReader(io.BytesIO(gerar_pdf(rel))).metadata
    props = load_workbook(io.BytesIO(gerar_xlsx(rel))).properties

    assert meta.author == props.creator == NOME_INSTITUICAO_PADRAO
    assert "01/01/2026 a 30/06/2026" in meta.title
    assert "01/01/2026 a 30/06/2026" in props.title


def test_gerado_em_no_horario_de_brasilia(semear, orcamentos):
    rel = relatorio(semear, orcamentos, gerado_em=datetime(2026, 11, 9, 2, 30, tzinfo=timezone.utc))
    assert dict(linhas_do_cabecalho(rel))["Gerado em"] == "08/11/2026 23:30 (horário de Brasília)"


def test_instituicao_padrao_e_a_do_mdca(monkeypatch):
    monkeypatch.delenv("MDCA_INSTITUICAO_NOME", raising=False)
    monkeypatch.delenv("MDCA_INSTITUICAO_CNPJ", raising=False)
    padrao = instituicao_configurada()

    assert padrao.nome == "Movimento pelos Direitos da Criança e do Adolescente"
    assert padrao.cnpj == "93.459.345/0001-99"


def test_instituicao_pode_vir_das_variaveis_de_ambiente(monkeypatch, semear, orcamentos):
    monkeypatch.setenv("MDCA_INSTITUICAO_NOME", "Instituição Parceira")
    monkeypatch.setenv("MDCA_INSTITUICAO_CNPJ", "11222333000181")
    rel = montar_relatorio(semear, orcamentos, INICIO, FIM, url_base=API)

    assert dict(linhas_do_cabecalho(rel))["Instituição"] == "Instituição Parceira"
    assert dict(linhas_do_cabecalho(rel))["CNPJ"] == "11.222.333/0001-81"


@pytest.mark.parametrize("cnpj", ["93.459.345/0001-98", "11111111111111", "123", "", "93459345000199x9"])
def test_cnpj_invalido_e_recusado(cnpj):
    with pytest.raises(RelatorioInvalido, match="CNPJ"):
        formatar_cnpj(cnpj)


def test_nome_da_instituicao_e_obrigatorio():
    with pytest.raises(RelatorioInvalido, match="Nome da instituição"):
        Instituicao(nome="   ", cnpj=CNPJ_INSTITUICAO_PADRAO)


def test_nome_do_arquivo_tem_projeto_e_periodo(semear, orcamentos):
    rel = relatorio(semear, orcamentos)
    assert nome_do_arquivo(rel, "pdf") == "prestacao-contas_semear-contraturno_2026-01-01_2026-06-30.pdf"
    assert nome_do_arquivo(rel, "xlsx").endswith(".xlsx")
