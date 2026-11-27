"""Componente de relatórios da plataforma em PDF e XLSX (ARQ-06 · T-75).

Um relatório é um ``Documento``: título, linhas de cabeçalho (rótulo e valor) e seções,
cada uma com uma tabela (colunas e linhas de texto) e uma nota opcional. ``gerar_pdf`` e
``gerar_xlsx`` desenham **o mesmo documento** em cada formato, então um formato não tem
como mostrar um dado que o outro não mostra (paridade).

Quem monta o documento decide o conteúdo, inclusive o que fica de fora por privacidade:
este componente só desenha texto. O visual segue o relatório de prestação de contas do
Financeiro (``Financeiro/relatorio_prestacao.py``), que pode passar a usar este
componente depois.

Cuidados no XLSX: toda célula é gravada como texto, para "=..." digitado por alguém não
virar fórmula.
"""

import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

VERDE = "3F8A3A"
CINZA = "71717A"
BORDA = "D4D4D8"
FUNDO = "F4F4F5"
_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def limpar(texto) -> str:
    """Texto seguro para os dois formatos: sem caracteres de controle e sem ``None``."""
    if texto is None:
        return ""
    return _CONTROLE.sub("", str(texto)).strip()


@dataclass(frozen=True)
class Secao:
    titulo: str
    colunas: Sequence[str]
    linhas: Sequence[Sequence[str]]
    # Texto curto abaixo da tabela (ex.: o que foi omitido e por quê).
    nota: Optional[str] = None
    # Texto mostrado no lugar da tabela quando ela não tem linhas.
    vazio: str = "Nada a mostrar neste período."


@dataclass(frozen=True)
class Documento:
    titulo: str
    cabecalho: Sequence[Tuple[str, str]]
    secoes: Sequence[Secao]
    rodape: str = ""
    autor: str = "MDCA"
    assunto: str = ""
    # Colunas que alinham à direita (números), pelo título da coluna.
    colunas_numericas: Sequence[str] = field(default_factory=tuple)


def _limpo(doc: Documento) -> Documento:
    """O mesmo documento com todo texto limpo: é dele que os dois formatos saem."""
    return Documento(
        titulo=limpar(doc.titulo),
        cabecalho=[(limpar(r), limpar(v)) for r, v in doc.cabecalho],
        secoes=[
            Secao(
                titulo=limpar(s.titulo),
                colunas=[limpar(c) for c in s.colunas],
                linhas=[[limpar(v) for v in linha] for linha in s.linhas],
                nota=limpar(s.nota) or None,
                vazio=limpar(s.vazio),
            )
            for s in doc.secoes
        ],
        rodape=limpar(doc.rodape),
        autor=limpar(doc.autor),
        assunto=limpar(doc.assunto),
        colunas_numericas=tuple(doc.colunas_numericas),
    )


def conteudo(doc: Documento) -> List[List[str]]:
    """Todas as células do documento, na ordem em que aparecem (base dos testes de paridade)."""
    doc = _limpo(doc)
    celulas = [[doc.titulo]]
    celulas += [[r, v] for r, v in doc.cabecalho]
    for s in doc.secoes:
        celulas.append([s.titulo])
        if s.linhas:
            celulas.append(list(s.colunas))
            celulas += [list(linha) for linha in s.linhas]
        else:
            celulas.append([s.vazio])
        if s.nota:
            celulas.append([s.nota])
    if doc.rodape:
        celulas.append([doc.rodape])
    return celulas


def nome_do_arquivo(doc: Documento, extensao: str) -> str:
    """Nome do arquivo a partir do título, só com letras sem acento, números e hífens."""
    base = unicodedata.normalize("NFKD", limpar(doc.titulo)).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-").lower() or "relatorio"
    return f"{base[:80]}.{extensao}"


def gerar_pdf(doc: Documento) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    doc = _limpo(doc)
    verde, cinza, borda, fundo = (colors.HexColor(f"#{c}") for c in (VERDE, CINZA, BORDA, FUNDO))
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=11.5, splitLongWords=1)
    negrito = ParagraphStyle("negrito", parent=base, fontName="Helvetica-Bold")
    direita = ParagraphStyle("direita", parent=base, alignment=TA_RIGHT)
    direita_negrito = ParagraphStyle("direita_negrito", parent=direita, fontName="Helvetica-Bold")
    discreto = ParagraphStyle("discreto", parent=base, textColor=cinza)
    titulo = ParagraphStyle("titulo", parent=base, fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=verde, spaceAfter=6)
    subtitulo = ParagraphStyle("subtitulo", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=10, spaceAfter=4)

    def p(texto: str, estilo=base) -> Paragraph:
        return Paragraph(escape(texto), estilo)

    largura = landscape(A4)[0] - 30 * mm
    elementos = [p(doc.titulo, titulo)]
    if doc.cabecalho:
        cabecalho = Table([[p(r, negrito), p(v)] for r, v in doc.cabecalho], colWidths=[50 * mm, largura - 50 * mm], hAlign="LEFT")
        cabecalho.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, -1), (-1, -1), 0.8, verde),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]))
        elementos.append(cabecalho)

    for s in doc.secoes:
        elementos.append(p(s.titulo, subtitulo))
        if not s.linhas:
            elementos.append(p(s.vazio, discreto))
        else:
            numericas = {i for i, c in enumerate(s.colunas) if c in doc.colunas_numericas}
            cabeca = [p(c, direita_negrito if i in numericas else negrito) for i, c in enumerate(s.colunas)]
            corpo = [[p(v, direita if i in numericas else base) for i, v in enumerate(linha)] for linha in s.linhas]
            tabela = Table([cabeca] + corpo, colWidths=[largura / len(s.colunas)] * len(s.colunas), repeatRows=1, hAlign="LEFT")
            tabela.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), fundo),
                ("GRID", (0, 0), (-1, -1), 0.4, borda),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
            ]))
            elementos.append(tabela)
        if s.nota:
            elementos += [Spacer(1, 3), p(s.nota, discreto)]

    if doc.rodape:
        elementos += [Spacer(1, 10), p(doc.rodape, discreto)]

    saida = io.BytesIO()
    pdf = SimpleDocTemplate(
        saida,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=doc.titulo,
        author=doc.autor,
        subject=doc.assunto,
    )
    pdf.build(elementos)
    return saida.getvalue()


def _texto(celula, texto: str) -> None:
    celula.value = texto
    celula.data_type = "s"


def gerar_xlsx(doc: Documento) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    doc = _limpo(doc)
    negrito = Font(bold=True)
    fundo = PatternFill("solid", fgColor=FUNDO)
    fina = Side(style="thin", color=BORDA)
    grade = Border(left=fina, right=fina, top=fina, bottom=fina)
    discreto = Font(color=CINZA, italic=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Relatório"
    wb.properties.title = doc.titulo
    wb.properties.creator = doc.autor
    wb.properties.subject = doc.assunto

    linha = 1
    _texto(ws.cell(linha, 1), doc.titulo)
    ws.cell(linha, 1).font = Font(bold=True, size=14, color=VERDE)
    for rotulo, valor in doc.cabecalho:
        linha += 1
        _texto(ws.cell(linha, 1), rotulo)
        ws.cell(linha, 1).font = negrito
        _texto(ws.cell(linha, 2), valor)

    for s in doc.secoes:
        linha += 2
        _texto(ws.cell(linha, 1), s.titulo)
        ws.cell(linha, 1).font = Font(bold=True, size=12)
        linha += 1
        if not s.linhas:
            _texto(ws.cell(linha, 1), s.vazio)
            ws.cell(linha, 1).font = discreto
        else:
            numericas = {i for i, c in enumerate(s.colunas) if c in doc.colunas_numericas}
            for coluna, titulo in enumerate(s.colunas, start=1):
                celula = ws.cell(linha, coluna)
                _texto(celula, titulo)
                celula.font, celula.fill, celula.border = negrito, fundo, grade
            for valores in s.linhas:
                linha += 1
                for coluna, valor in enumerate(valores, start=1):
                    celula = ws.cell(linha, coluna)
                    _texto(celula, valor)
                    celula.border = grade
                    celula.alignment = Alignment(wrap_text=True, vertical="top", horizontal="right" if coluna - 1 in numericas else "left")
        if s.nota:
            linha += 1
            _texto(ws.cell(linha, 1), s.nota)
            ws.cell(linha, 1).font = discreto

    if doc.rodape:
        linha += 2
        _texto(ws.cell(linha, 1), doc.rodape)
        ws.cell(linha, 1).font = discreto

    for coluna in "ABCDEFGH":
        ws.column_dimensions[coluna].width = 26
    saida = io.BytesIO()
    wb.save(saida)
    return saida.getvalue()


def ler_xlsx(dados: bytes) -> List[List[str]]:
    """Células não vazias do XLSX, linha a linha (para conferir paridade nos testes)."""
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(dados)).active
    return [[str(v) for v in linha if v not in (None, "")] for linha in ws.iter_rows(values_only=True) if any(v not in (None, "") for v in linha)]


def ler_pdf(dados: bytes) -> str:
    """Texto do PDF (para conferir paridade e ausência de dados nos testes)."""
    from pypdf import PdfReader

    return "\n".join(pagina.extract_text() or "" for pagina in PdfReader(io.BytesIO(dados)).pages)
