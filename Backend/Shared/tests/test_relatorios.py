"""Componente de relatórios da plataforma (ARQ-06 · T-75): PDF e XLSX com os mesmos dados.

Não usa banco.
"""

from Shared.relatorios import Documento, Secao, conteudo, gerar_pdf, gerar_xlsx, ler_pdf, ler_xlsx, limpar, nome_do_arquivo

DOC = Documento(
    titulo="Relatório técnico — Semear — 01/09/2026 a 30/09/2026",
    cabecalho=[("Programa", "Semear (SEMEAR)"), ("Finalidade", "Circulação externa")],
    secoes=[
        Secao("Indicadores", ["Indicador", "Valor"], [["Encontros realizados", "4"], ["Frequência", "66,7%"]], nota="Mesmo cálculo da tela."),
        Secao("Evidências", ["Data", "Turma", "Tipo"], [], vazio="Nenhuma evidência liberada."),
        Secao("Atividades", ["Data", "Turma", "Conteúdo"], [["02/09/2026", "Oficina", "=HYPERLINK(\"x\")"]]),
    ],
    rodape="Documento sem dados pessoais.",
    colunas_numericas=("Valor",),
)


def palavras(texto):
    return set(texto.replace("\n", " ").split())


def test_xlsx_tem_exatamente_o_conteudo_do_documento():
    assert ler_xlsx(gerar_xlsx(DOC)) == conteudo(DOC)


def test_pdf_tem_todo_o_conteudo_do_documento():
    texto = palavras(ler_pdf(gerar_pdf(DOC)))

    for linha in conteudo(DOC):
        for celula in linha:
            assert palavras(celula) <= texto, celula


def test_texto_que_parece_formula_fica_como_texto_no_xlsx():
    from io import BytesIO

    from openpyxl import load_workbook

    ws = load_workbook(BytesIO(gerar_xlsx(DOC))).active
    celula = next(c for linha in ws.iter_rows() for c in linha if c.value == '=HYPERLINK("x")')
    assert celula.data_type == "s"


def test_caracteres_de_controle_saem_dos_dois_formatos():
    doc = Documento(titulo="Relatório\x00 teste\x1b", cabecalho=[], secoes=[])

    assert limpar("a\x07b ") == "ab"
    assert conteudo(doc) == [["Relatório teste"]]
    assert ler_xlsx(gerar_xlsx(doc)) == [["Relatório teste"]]


def test_nome_do_arquivo_sem_acentos_nem_simbolos():
    assert nome_do_arquivo(DOC, "pdf") == "relatorio-tecnico-semear-01-09-2026-a-30-09-2026.pdf"
    assert nome_do_arquivo(Documento(titulo="???", cabecalho=[], secoes=[]), "xlsx") == "relatorio.xlsx"
