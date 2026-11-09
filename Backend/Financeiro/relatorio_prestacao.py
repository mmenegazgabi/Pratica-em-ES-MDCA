"""Relatório de prestação de contas em PDF e XLSX (T-24 · US-06).

Serviço reutilizável: ``montar_relatorio`` junta os dados de um projeto num
período e ``gerar_pdf`` / ``gerar_xlsx`` desenham esses mesmos dados em cada
formato. O endpoint (T-25) e a tela (T-26) só chamam estas funções.

O que entra no relatório (mesmas regras do dashboard, T-29):

- orçado: soma do ``valor_total`` dos orçamentos do projeto cuja vigência
  cruza o período;
- realizado: soma dos lançamentos **aprovados** com ``data_despesa`` no
  período (pendentes, rejeitados e lançamentos sem data ficam de fora);
- saldo: orçado - realizado;
- a lista desses lançamentos aprovados, cada um com o link do comprovante.

Paridade entre formatos: os dois arquivos são montados a partir das mesmas
funções (``linhas_do_cabecalho``, ``linhas_do_resumo``, ``linhas_dos_lancamentos``),
então não há como um formato mostrar um dado que o outro não mostra. O texto
digitado pelas pessoas é limpo uma vez, em ``montar_relatorio``, antes de ir
para os dois formatos (ver ``_texto``).

Os valores são somados em centavos (Decimal) para não acumular erro de float.
"""

import io
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote
from xml.sax.saxutils import escape

if __package__:
    from .alerta_saldo import _em_centavos
    from .dashboard import _conta_no_realizado, _cruza_periodo
    from .moeda import formatar_reais
    from .orcamento import Orcamento
    from .projetos import Projeto
else:
    from alerta_saldo import _em_centavos
    from dashboard import _conta_no_realizado, _cruza_periodo
    from moeda import formatar_reais
    from orcamento import Orcamento
    from projetos import Projeto


# Dados do MDCA como aparecem nos formulários da própria instituição (ficha de
# ingresso de educadores). Podem ser trocados sem mexer no código pelas
# variáveis de ambiente MDCA_INSTITUICAO_NOME e MDCA_INSTITUICAO_CNPJ.
NOME_INSTITUICAO_PADRAO = "Movimento pelos Direitos da Criança e do Adolescente"
CNPJ_INSTITUICAO_PADRAO = "93.459.345/0001-99"

# Horário de Brasília (sem horário de verão desde 2019). Fuso fixo para não
# depender da base de fusos do sistema, que falta no Python do Windows.
FUSO_BRASILIA = timezone(timedelta(hours=-3), "BRT")

TITULO = "Prestação de contas"
TITULO_RESUMO = "Resumo"
TITULO_LANCAMENTOS = "Lançamentos aprovados no período"
COLUNAS_LANCAMENTOS = ("Data", "Categoria", "Descrição", "Valor", "Comprovante")
SEM_LANCAMENTOS = "Nenhum lançamento aprovado no período."
SEM_COMPROVANTE = "Sem comprovante"
ROTULO_TOTAL = "Total"

CONTENT_TYPE_PDF = "application/pdf"
CONTENT_TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class RelatorioInvalido(ValueError):
    """Dados insuficientes ou inválidos para montar o relatório."""


# --- Instituição ---------------------------------------------------------------


def _digitos_cnpj(base: Sequence[int]) -> Tuple[int, int]:
    def digito(numeros, pesos):
        resto = sum(n * p for n, p in zip(numeros, pesos)) % 11
        return 0 if resto < 2 else 11 - resto

    primeiro = digito(base, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    segundo = digito(list(base) + [primeiro], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return primeiro, segundo


def formatar_cnpj(cnpj: str) -> str:
    """Confere os dígitos verificadores e devolve no formato 00.000.000/0000-00."""
    numeros = re.sub(r"\D", "", cnpj or "")
    if len(numeros) != 14 or len(set(numeros)) == 1:
        raise RelatorioInvalido("CNPJ da instituição inválido.")
    digitos = [int(c) for c in numeros]
    if _digitos_cnpj(digitos[:12]) != tuple(digitos[12:]):
        raise RelatorioInvalido("CNPJ da instituição inválido.")
    n = numeros
    return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"


@dataclass(frozen=True)
class Instituicao:
    nome: str
    cnpj: str

    def __post_init__(self) -> None:
        nome = _texto(self.nome)
        if not nome:
            raise RelatorioInvalido("Nome da instituição é obrigatório.")
        object.__setattr__(self, "nome", nome)
        object.__setattr__(self, "cnpj", formatar_cnpj(self.cnpj))


def instituicao_configurada() -> Instituicao:
    """Instituição do cabeçalho: variáveis de ambiente ou os dados do MDCA."""
    return Instituicao(
        nome=os.getenv("MDCA_INSTITUICAO_NOME") or NOME_INSTITUICAO_PADRAO,
        cnpj=os.getenv("MDCA_INSTITUICAO_CNPJ") or CNPJ_INSTITUICAO_PADRAO,
    )


# --- Dados do relatório --------------------------------------------------------


def _texto(valor: Optional[str]) -> str:
    """Texto pronto para os dois formatos.

    - junta quebras de linha e espaços repetidos (cada dado cabe numa célula);
    - troca por "?" o que as fontes padrão do PDF não desenham (ex.: emoji).
      Letras com acento, travessão, aspas curvas e reticências continuam.

    Aplicado antes dos dois formatos, para o XLSX mostrar o mesmo texto do PDF.
    """
    limpo = " ".join(str(valor or "").split())
    return limpo.encode("cp1252", errors="replace").decode("cp1252")


@dataclass(frozen=True)
class LancamentoDoRelatorio:
    id: str
    data_despesa: date
    categoria: str
    descricao: str
    valor: Decimal
    comprovante_url: Optional[str]


@dataclass(frozen=True)
class RelatorioPrestacao:
    instituicao: Instituicao
    projeto_id: str
    projeto_nome: str
    data_inicio: date
    data_fim: date
    orcado: Decimal
    realizado: Decimal
    saldo: Decimal
    lancamentos: Tuple[LancamentoDoRelatorio, ...]
    gerado_em: datetime

    @property
    def periodo(self) -> str:
        return f"{formatar_data(self.data_inicio)} a {formatar_data(self.data_fim)}"


def _url_do_comprovante(url_base: str, chave: Optional[str]) -> Optional[str]:
    if not chave:
        return None
    return f"{url_base}/{quote(chave, safe='/')}"


def montar_relatorio(
    projeto: Projeto,
    orcamentos: Iterable[Orcamento],
    data_inicio: date,
    data_fim: date,
    *,
    url_base: str,
    instituicao: Optional[Instituicao] = None,
    gerado_em: Optional[datetime] = None,
) -> RelatorioPrestacao:
    """Junta orçado, realizado, saldo e lançamentos aprovados do projeto no período.

    ``orcamentos`` pode trazer orçamentos de outros projetos: só os do
    ``projeto`` entram. ``url_base`` é o endereço público da API; o link do
    comprovante é a rota autenticada ``GET /comprovantes/...`` (T-11).
    """
    if data_inicio is None or data_fim is None:
        raise RelatorioInvalido("Informe o início e o fim do período.")
    if data_fim < data_inicio:
        raise RelatorioInvalido("O fim do período não pode ser antes do início.")
    url_base = (url_base or "").strip().rstrip("/")
    if not re.match(r"^https?://[^/\s]+", url_base):
        raise RelatorioInvalido("url_base deve ser o endereço http(s) da API.")

    orcado = Decimal(0)
    aprovados = []
    for orcamento in orcamentos:
        if orcamento.projeto_id != projeto.id:
            continue
        if _cruza_periodo(orcamento, data_inicio, data_fim):
            orcado += _em_centavos(orcamento.valor_total)
        # Cópia sob a trava do orçamento: aprovações mudam a lista ao mesmo tempo.
        with orcamento._lock:
            lancamentos = list(orcamento.lancamentos)
        aprovados.extend(
            l for l in lancamentos if _conta_no_realizado(l, data_inicio, data_fim)
        )

    aprovados.sort(key=lambda l: (l.data_despesa, l.criado_em, l.id))
    itens = tuple(
        LancamentoDoRelatorio(
            id=l.id,
            data_despesa=l.data_despesa,
            categoria=_texto(l.categoria),
            descricao=_texto(l.descricao),
            valor=_em_centavos(l.valor),
            comprovante_url=_url_do_comprovante(url_base, l.comprovante_chave),
        )
        for l in aprovados
    )
    realizado = sum((i.valor for i in itens), Decimal(0))

    return RelatorioPrestacao(
        instituicao=instituicao or instituicao_configurada(),
        projeto_id=projeto.id,
        projeto_nome=_texto(projeto.nome),
        data_inicio=data_inicio,
        data_fim=data_fim,
        orcado=orcado,
        realizado=realizado,
        saldo=orcado - realizado,
        lancamentos=itens,
        gerado_em=gerado_em or datetime.now(timezone.utc),
    )


# --- Conteúdo comum aos dois formatos -----------------------------------------


def formatar_data(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


def formatar_momento(momento: datetime) -> str:
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(FUSO_BRASILIA).strftime("%d/%m/%Y %H:%M") + " (horário de Brasília)"


def formatar_valor(valor: Decimal) -> str:
    return formatar_reais(valor)


def linhas_do_cabecalho(rel: RelatorioPrestacao) -> List[Tuple[str, str]]:
    return [
        ("Instituição", rel.instituicao.nome),
        ("CNPJ", rel.instituicao.cnpj),
        ("Projeto", rel.projeto_nome),
        ("Período de referência", rel.periodo),
        ("Gerado em", formatar_momento(rel.gerado_em)),
    ]


def linhas_do_resumo(rel: RelatorioPrestacao) -> List[Tuple[str, Decimal]]:
    return [("Orçado", rel.orcado), ("Realizado", rel.realizado), ("Saldo", rel.saldo)]


def linhas_dos_lancamentos(rel: RelatorioPrestacao) -> List[Tuple[date, str, str, Decimal, Optional[str]]]:
    return [
        (l.data_despesa, l.categoria, l.descricao, l.valor, l.comprovante_url)
        for l in rel.lancamentos
    ]


def nome_do_arquivo(rel: RelatorioPrestacao, extensao: str) -> str:
    """Ex.: prestacao-contas_semear_2026-01-01_2026-06-30.pdf"""
    base = re.sub(r"[^a-z0-9]+", "-", rel.projeto_nome.lower().encode("ascii", "ignore").decode()).strip("-")
    return f"prestacao-contas_{base or 'projeto'}_{rel.data_inicio.isoformat()}_{rel.data_fim.isoformat()}.{extensao}"


# --- PDF -----------------------------------------------------------------------


def gerar_pdf(rel: RelatorioPrestacao) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    verde = colors.HexColor("#3f8a3a")
    cinza = colors.HexColor("#71717a")
    borda = colors.HexColor("#d4d4d8")
    fundo = colors.HexColor("#f4f4f5")

    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=11.5, splitLongWords=1)
    negrito = ParagraphStyle("negrito", parent=base, fontName="Helvetica-Bold")
    direita = ParagraphStyle("direita", parent=base, alignment=TA_RIGHT)
    direita_negrito = ParagraphStyle("direita_negrito", parent=direita, fontName="Helvetica-Bold")
    titulo = ParagraphStyle("titulo", parent=base, fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=verde, spaceAfter=6)
    secao = ParagraphStyle("secao", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=10, spaceAfter=4)

    def p(texto: str, estilo=base) -> Paragraph:
        return Paragraph(escape(texto), estilo)

    def link(url: Optional[str]) -> Paragraph:
        if not url:
            return p(SEM_COMPROVANTE, ParagraphStyle("sem", parent=base, textColor=cinza))
        href = escape(url, {'"': "&quot;"})
        return Paragraph(f'<link href="{href}" color="#1d4ed8">{escape(url)}</link>', base)

    largura = landscape(A4)[0] - 30 * mm
    elementos = [p(TITULO, titulo)]

    cabecalho = Table(
        [[p(rotulo, negrito), p(valor)] for rotulo, valor in linhas_do_cabecalho(rel)],
        colWidths=[45 * mm, largura - 45 * mm],
        hAlign="LEFT",
    )
    cabecalho.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, -1), (-1, -1), 0.8, verde),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    elementos += [cabecalho, p(TITULO_RESUMO, secao)]

    resumo = Table(
        [[p(rotulo, negrito), p(formatar_valor(valor), direita)] for rotulo, valor in linhas_do_resumo(rel)],
        colWidths=[45 * mm, 45 * mm],
        hAlign="LEFT",
    )
    resumo.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, borda),
        ("BACKGROUND", (0, 0), (0, -1), fundo),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos += [resumo, p(TITULO_LANCAMENTOS, secao)]

    larguras = [22 * mm, 38 * mm, 82 * mm, 28 * mm]
    larguras.append(largura - sum(larguras))
    linhas = [[p(c, direita_negrito if c == "Valor" else negrito) for c in COLUNAS_LANCAMENTOS]]
    for dia, categoria, descricao, valor, url in linhas_dos_lancamentos(rel):
        linhas.append([p(formatar_data(dia)), p(categoria), p(descricao), p(formatar_valor(valor), direita), link(url)])
    if rel.lancamentos:
        linhas.append([p(ROTULO_TOTAL, negrito), p(""), p(""), p(formatar_valor(rel.realizado), direita_negrito), p("")])
    else:
        linhas.append([p(SEM_LANCAMENTOS), "", "", "", ""])

    tabela = Table(linhas, colWidths=larguras, repeatRows=1, hAlign="LEFT")
    estilo = [
        ("GRID", (0, 0), (-1, -1), 0.5, borda),
        ("BACKGROUND", (0, 0), (-1, 0), fundo),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, -1), (-1, -1), fundo),
    ]
    if not rel.lancamentos:
        estilo.append(("SPAN", (0, -1), (-1, -1)))
    tabela.setStyle(TableStyle(estilo))
    elementos += [tabela, Spacer(1, 4 * mm)]

    rodape = f"{rel.instituicao.nome} · CNPJ {rel.instituicao.cnpj} · {TITULO} · {rel.projeto_nome} · {rel.periodo}"

    def desenhar_rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(cinza)
        canvas.drawString(15 * mm, 8 * mm, rodape[:180])
        canvas.drawRightString(landscape(A4)[0] - 15 * mm, 8 * mm, f"Página {doc.page}")
        canvas.restoreState()

    saida = io.BytesIO()
    doc = SimpleDocTemplate(
        saida,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"{TITULO} — {rel.projeto_nome} — {rel.periodo}",
        author=rel.instituicao.nome,
        subject=f"{TITULO} · CNPJ {rel.instituicao.cnpj}",
        creator="MDCA · Módulo Financeiro",
    )
    doc.build(elementos, onFirstPage=desenhar_rodape, onLaterPages=desenhar_rodape)
    return saida.getvalue()


# --- XLSX ----------------------------------------------------------------------

FORMATO_REAIS = '"R$" #,##0.00;"R$" -#,##0.00'
FORMATO_DATA = "DD/MM/YYYY"


def _escrever_texto(celula, texto: str) -> None:
    """Grava sempre como texto: "=..." digitado por alguém não vira fórmula."""
    celula.value = texto
    celula.data_type = "s"


def gerar_xlsx(rel: RelatorioPrestacao) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    negrito = Font(bold=True)
    fundo = PatternFill("solid", fgColor="F4F4F5")
    fina = Side(style="thin", color="D4D4D8")
    grade = Border(left=fina, right=fina, top=fina, bottom=fina)
    link = Font(color="1D4ED8", underline="single")

    wb = Workbook()
    ws = wb.active
    ws.title = TITULO
    wb.properties.title = f"{TITULO} — {rel.projeto_nome} — {rel.periodo}"
    wb.properties.creator = rel.instituicao.nome
    wb.properties.subject = f"{TITULO} · CNPJ {rel.instituicao.cnpj}"

    linha = 1
    _escrever_texto(ws.cell(linha, 1), TITULO)
    ws.cell(linha, 1).font = Font(bold=True, size=14, color="3F8A3A")
    linha += 1
    for rotulo, valor in linhas_do_cabecalho(rel):
        _escrever_texto(ws.cell(linha, 1), rotulo)
        ws.cell(linha, 1).font = negrito
        _escrever_texto(ws.cell(linha, 2), valor)
        linha += 1

    linha += 1
    _escrever_texto(ws.cell(linha, 1), TITULO_RESUMO)
    ws.cell(linha, 1).font = Font(bold=True, size=12)
    linha += 1
    for rotulo, valor in linhas_do_resumo(rel):
        _escrever_texto(ws.cell(linha, 1), rotulo)
        ws.cell(linha, 1).font = negrito
        ws.cell(linha, 1).fill = fundo
        celula = ws.cell(linha, 2, float(valor))
        celula.number_format = FORMATO_REAIS
        for c in (ws.cell(linha, 1), celula):
            c.border = grade
        linha += 1

    linha += 1
    _escrever_texto(ws.cell(linha, 1), TITULO_LANCAMENTOS)
    ws.cell(linha, 1).font = Font(bold=True, size=12)
    linha += 1
    linha_colunas = linha
    for coluna, nome in enumerate(COLUNAS_LANCAMENTOS, start=1):
        celula = ws.cell(linha, coluna)
        _escrever_texto(celula, nome)
        celula.font = negrito
        celula.fill = fundo
        celula.border = grade
    linha += 1

    for dia, categoria, descricao, valor, url in linhas_dos_lancamentos(rel):
        ws.cell(linha, 1, dia).number_format = FORMATO_DATA
        _escrever_texto(ws.cell(linha, 2), categoria)
        _escrever_texto(ws.cell(linha, 3), descricao)
        ws.cell(linha, 4, float(valor)).number_format = FORMATO_REAIS
        comprovante = ws.cell(linha, 5)
        if url:
            _escrever_texto(comprovante, url)
            comprovante.hyperlink = url
            comprovante.font = link
        else:
            _escrever_texto(comprovante, SEM_COMPROVANTE)
        for coluna in range(1, 6):
            ws.cell(linha, coluna).border = grade
            ws.cell(linha, coluna).alignment = Alignment(vertical="top", wrap_text=coluna in (2, 3))
        linha += 1

    if rel.lancamentos:
        _escrever_texto(ws.cell(linha, 1), ROTULO_TOTAL)
        ws.cell(linha, 1).font = negrito
        total = ws.cell(linha, 4, float(rel.realizado))
        total.number_format = FORMATO_REAIS
        total.font = negrito
        for coluna in range(1, 6):
            ws.cell(linha, coluna).fill = fundo
            ws.cell(linha, coluna).border = grade
    else:
        _escrever_texto(ws.cell(linha, 1), SEM_LANCAMENTOS)

    for coluna, largura in zip("ABCDE", (24, 26, 50, 16, 90)):
        ws.column_dimensions[coluna].width = largura
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = f"{linha_colunas}:{linha_colunas}"

    saida = io.BytesIO()
    wb.save(saida)
    return saida.getvalue()
