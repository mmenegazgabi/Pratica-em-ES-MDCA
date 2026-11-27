"""Relatório técnico de um programa num período (T-75 · US-11).

Junta, para um programa e um período, as seções escolhidas e desenha o resultado com o
componente de relatórios da plataforma (``Shared/relatorios.py``, ARQ-06), em PDF ou XLSX.

**Seções** (quem emite escolhe quais entram):

- ``plano``: objetivos, ações, resultado esperado e metas (planejado, realizado no período,
  acumulado até o fim e percentual). Mesmo cálculo da Visão integrada.
- ``pessoas``: pessoas acompanhadas no período (matrícula na turma durante o período).
- ``atividades``: encontros do período com presenças e ausências.
- ``indicadores``: os números da US-10 (``Gestao/indicadores.py``), no mesmo recorte.
- ``evidencias``: as evidências escolhidas (sem escolha, todas as do período).
- ``financeiro``: orçado, realizado e saldo do programa no Financeiro. Só para quem vê
  valores financeiros.

**Finalidade e minimização de dados:**

- ``interna`` (consulta interna): traz o nome de cada pessoa acompanhada, a frequência de
  cada uma e o conteúdo de cada encontro.
- ``externa`` (circulação externa: financiadores, conselho, divulgação): nenhum dado
  pessoal. Pessoas só em número por turma; encontros sem o conteúdo digitado (pode citar
  nomes); evidências sem descrição nem nome de arquivo, e só as **liberadas**: todas as
  pessoas presentes no encontro têm autorização de uso de imagem vigente (US-03). As
  outras ficam de fora e aparecem nas pendências.

**Pendências antes da versão final:** chamadas sem registro, encontros sem evidência
(quando a seção de evidências entra), autorizações de imagem vencidas (na circulação
externa) e evidências não liberadas. Elas aparecem na prévia; a emissão não é bloqueada,
mas quem emite as vê antes.

As funções só leem; quem registra a emissão na trilha é a rota.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Set

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from Gestao import indicadores
from Gestao.autorizacoes import VIGENTE, autorizacoes_por_pessoa, situacao_de_imagem
from Gestao.erros import DadosInvalidos
from Gestao.programas import buscar_programa
from Gestao.visao_integrada import execucao_financeira, execucao_fisica
from Shared.relatorios import Documento, Secao

INTERNA = "interna"
EXTERNA = "externa"
FINALIDADES = {INTERNA: "Consulta interna", EXTERNA: "Circulação externa"}

PLANO, PESSOAS, ATIVIDADES, INDICADORES, EVIDENCIAS, FINANCEIRO = (
    "plano", "pessoas", "atividades", "indicadores", "evidencias", "financeiro",
)
SECOES = {
    PLANO: "Objetivos, ações e resultados",
    PESSOAS: "Pessoas atendidas",
    ATIVIDADES: "Atividades e frequência",
    INDICADORES: "Indicadores",
    EVIDENCIAS: "Evidências",
    FINANCEIRO: "Execução física e financeira",
}
TITULO = "Relatório técnico"
NUMERICAS = (
    "Planejado", "Realizado no período", "Realizado acumulado", "%", "Pessoas", "Presenças",
    "Ausências", "Frequência", "Valor", "Encontros",
)

SEM_SECAO = "Escolha ao menos uma seção do relatório."
FINALIDADE_INVALIDA = "Finalidade inválida: use interna ou externa."
SECAO_INVALIDA = "Seção desconhecida: {}."


@dataclass(frozen=True)
class Pendencia:
    tipo: str
    descricao: str
    quantidade: int


@dataclass(frozen=True)
class EvidenciaDoPeriodo:
    id: str
    data: date
    turma: str
    # Liberada para circulação externa: todas as pessoas presentes têm autorização vigente.
    liberada_externa: bool


@dataclass(frozen=True)
class Relatorio:
    programa_id: str
    programa: str
    periodo: indicadores.Periodo
    finalidade: str
    secoes: List[str]
    documento: Documento
    pendencias: List[Pendencia]
    evidencias_disponiveis: List[EvidenciaDoPeriodo] = field(default_factory=list)


# --- Formatação ------------------------------------------------------------------------


def _data(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


def _numero(valor) -> str:
    valor = Decimal(str(valor))
    texto = f"{valor:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return texto[:-2] if texto.endswith(",0") else texto


def _porcento(valor) -> str:
    return "—" if valor is None else f"{_numero(valor)}%"


def _dinheiro(valor: float) -> str:
    texto = f"{Decimal(str(valor)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


# --- Dados -----------------------------------------------------------------------------


def _pessoas_no_periodo(conexao: Connection, programa_id: str, recorte: indicadores.Periodo) -> List[sa.Row]:
    """Uma linha por pessoa acompanhada: nome, turmas e presenças/ausências no período."""
    return list(
        conexao.execute(
            sa.text(
                """
                WITH acompanhadas AS (
                    SELECT DISTINCT m.pessoa_id, t.nome AS turma
                    FROM matriculas m
                    JOIN turmas t ON t.id = m.turma_id
                    WHERE t.programa_id = :programa
                      AND m.situacao <> 'espera'
                      AND m.data_entrada IS NOT NULL AND m.data_entrada <= :fim
                      AND (m.data_saida IS NULL OR m.data_saida > :inicio)
                ),
                frequencia AS (
                    SELECT c.pessoa_id,
                           count(*) FILTER (WHERE c.presente) AS presencas,
                           count(*) FILTER (WHERE NOT c.presente) AS ausencias
                    FROM chamadas c
                    JOIN atividades a ON a.id = c.atividade_id
                    WHERE a.programa_id = :programa AND a.data BETWEEN :inicio AND :fim
                    GROUP BY c.pessoa_id
                )
                SELECT p.id, p.nome, string_agg(DISTINCT ac.turma, ', ' ORDER BY ac.turma) AS turmas,
                       coalesce(max(f.presencas), 0) AS presencas, coalesce(max(f.ausencias), 0) AS ausencias
                FROM acompanhadas ac
                JOIN pessoas p ON p.id = ac.pessoa_id
                LEFT JOIN frequencia f ON f.pessoa_id = p.id
                GROUP BY p.id, p.nome
                ORDER BY lower(p.nome), p.id
                """
            ),
            {"programa": programa_id, "inicio": recorte.inicio, "fim": recorte.fim},
        )
    )


def _encontros(conexao: Connection, programa_id: str, recorte: indicadores.Periodo) -> List[sa.Row]:
    return list(
        conexao.execute(
            sa.text(
                """
                SELECT a.id, a.data, t.nome AS turma, a.conteudo,
                       count(c.id) FILTER (WHERE c.presente) AS presencas,
                       count(c.id) FILTER (WHERE NOT c.presente) AS ausencias
                FROM atividades a
                JOIN turmas t ON t.id = a.turma_id
                LEFT JOIN chamadas c ON c.atividade_id = a.id
                WHERE a.programa_id = :programa AND a.data BETWEEN :inicio AND :fim
                GROUP BY a.id, t.nome
                ORDER BY a.data, lower(t.nome), a.id
                """
            ),
            {"programa": programa_id, "inicio": recorte.inicio, "fim": recorte.fim},
        )
    )


def _evidencias(conexao: Connection, programa_id: str, recorte: indicadores.Periodo, hoje: date) -> List[dict]:
    linhas = list(
        conexao.execute(
            sa.text(
                """
                SELECT e.id, e.atividade_id, a.data, t.nome AS turma, e.descricao, e.nome_arquivo, e.content_type
                FROM evidencias e
                JOIN atividades a ON a.id = e.atividade_id
                JOIN turmas t ON t.id = a.turma_id
                WHERE a.programa_id = :programa AND a.data BETWEEN :inicio AND :fim
                ORDER BY a.data, lower(t.nome), e.criado_em, e.id
                """
            ),
            {"programa": programa_id, "inicio": recorte.inicio, "fim": recorte.fim},
        )
    )
    atividades = sorted({l.atividade_id for l in linhas})
    presentes: Dict[str, List[str]] = {}
    if atividades:
        for atividade_id, pessoa_id in conexao.execute(
            sa.text("SELECT atividade_id, pessoa_id FROM chamadas WHERE presente AND atividade_id = ANY(:ids)"),
            {"ids": atividades},
        ):
            presentes.setdefault(atividade_id, []).append(pessoa_id)
    todas = sorted({p for lista in presentes.values() for p in lista})
    autorizacoes = autorizacoes_por_pessoa(conexao, todas, hoje=hoje)
    vigentes: Set[str] = {p for p in todas if situacao_de_imagem(autorizacoes.get(p, [])) == VIGENTE}
    return [
        {**l._mapping, "liberada_externa": all(p in vigentes for p in presentes.get(l.atividade_id, []))}
        for l in linhas
    ]


# --- Seções ----------------------------------------------------------------------------


def _secao_plano(conexao: Connection, programa_id: str, recorte: indicadores.Periodo) -> Secao:
    no_periodo = {m.meta_id: m for m in execucao_fisica(conexao, programa_id, recorte.inicio, recorte.fim).metas}
    acumulado = execucao_fisica(conexao, programa_id, None, recorte.fim).metas
    resultados = dict(
        conexao.execute(
            sa.text(
                "SELECT a.id, a.resultado_esperado FROM acoes a JOIN objetivos o ON o.id = a.objetivo_id WHERE o.programa_id = :p"
            ),
            {"p": programa_id},
        ).all()
    )
    linhas = []
    for m in acumulado:
        unidade = f" {m.unidade}" if m.unidade else ""
        linhas.append([
            m.objetivo,
            m.acao,
            resultados.get(m.acao_id) or "",
            m.descricao,
            f"{_numero(m.planejado)}{unidade}",
            f"{_numero(no_periodo[m.meta_id].realizado)}{unidade}",
            f"{_numero(m.realizado)}{unidade}",
            _porcento(m.percentual),
        ])
    return Secao(
        SECOES[PLANO],
        ["Objetivo", "Ação", "Resultado esperado", "Meta", "Planejado", "Realizado no período", "Realizado acumulado", "%"],
        linhas,
        nota="O percentual usa o realizado acumulado até o fim do período.",
        vazio="O programa ainda não tem metas no plano de ação.",
    )


def _secao_pessoas(conexao: Connection, programa_id: str, recorte: indicadores.Periodo, finalidade: str) -> Secao:
    pessoas = _pessoas_no_periodo(conexao, programa_id, recorte)
    if finalidade == EXTERNA:
        por_turma: Dict[str, int] = {}
        for p in pessoas:
            for turma in p.turmas.split(", "):
                por_turma[turma] = por_turma.get(turma, 0) + 1
        linhas = [[turma, str(n)] for turma, n in sorted(por_turma.items(), key=lambda x: x[0].lower())]
        linhas.append(["Total (sem repetir quem está em mais de uma turma)", str(len(pessoas))])
        return Secao(
            SECOES[PESSOAS],
            ["Turma", "Pessoas"],
            linhas if pessoas else [],
            nota="Circulação externa: só o número de pessoas, sem nomes.",
            vazio="Nenhuma pessoa acompanhada no período.",
        )
    linhas = []
    for p in pessoas:
        total = p.presencas + p.ausencias
        freq = indicadores.percentual(Decimal(p.presencas), Decimal(total)) if total else None
        linhas.append([p.nome, p.turmas, str(p.presencas), str(p.ausencias), _porcento(freq)])
    return Secao(
        SECOES[PESSOAS],
        ["Pessoa", "Turmas", "Presenças", "Ausências", "Frequência"],
        linhas,
        nota="Consulta interna: contém dados pessoais. Não circular fora da instituição.",
        vazio="Nenhuma pessoa acompanhada no período.",
    )


def _secao_atividades(conexao: Connection, programa_id: str, recorte: indicadores.Periodo, finalidade: str) -> Secao:
    encontros = _encontros(conexao, programa_id, recorte)
    if finalidade == EXTERNA:
        return Secao(
            SECOES[ATIVIDADES],
            ["Data", "Turma", "Presenças", "Ausências"],
            [[_data(e.data), e.turma, str(e.presencas), str(e.ausencias)] for e in encontros],
            nota="Circulação externa: o conteúdo de cada encontro fica de fora, porque pode citar pessoas.",
            vazio="Nenhum encontro registrado no período.",
        )
    return Secao(
        SECOES[ATIVIDADES],
        ["Data", "Turma", "Presenças", "Ausências", "Conteúdo"],
        [[_data(e.data), e.turma, str(e.presencas), str(e.ausencias), e.conteudo] for e in encontros],
        vazio="Nenhum encontro registrado no período.",
    )


def _secao_indicadores(conexao: Connection, programa_id: str, recorte: indicadores.Periodo) -> Secao:
    n = indicadores.calcular(conexao, [programa_id], recorte).totais
    linhas = [
        ["Pessoas acompanhadas", _numero(n.pessoas_acompanhadas)],
        ["Encontros realizados", _numero(n.encontros_realizados)],
        ["Presenças", _numero(n.presencas)],
        ["Ausências", _numero(n.ausencias)],
        ["Frequência", _porcento(n.frequencia)],
        ["Horas de atividades", f"{_numero(n.horas_de_atividades)} h"],
        ["Média das metas", _porcento(n.percentual_medio_das_metas)],
    ]
    return Secao(SECOES[INDICADORES], ["Indicador", "Valor"], linhas, nota="Mesmo cálculo da tela de Indicadores, no recorte deste relatório.")


def _secao_evidencias(evidencias: List[dict], finalidade: str) -> Secao:
    if finalidade == EXTERNA:
        liberadas = [e for e in evidencias if e["liberada_externa"]]
        return Secao(
            SECOES[EVIDENCIAS],
            ["Data", "Turma", "Tipo"],
            [[_data(e["data"]), e["turma"], e["content_type"]] for e in liberadas],
            nota="Circulação externa: só evidências em que todas as pessoas presentes têm autorização de imagem vigente, sem descrição nem nome do arquivo.",
            vazio="Nenhuma evidência liberada para circulação externa.",
        )
    return Secao(
        SECOES[EVIDENCIAS],
        ["Data", "Turma", "Arquivo", "Descrição"],
        [[_data(e["data"]), e["turma"], e["nome_arquivo"], e["descricao"] or ""] for e in evidencias],
        vazio="Nenhuma evidência selecionada.",
    )


def _secao_financeiro(conexao: Connection, programa, recorte: indicadores.Periodo) -> Secao:
    f = execucao_financeira(conexao, programa, recorte.inicio, recorte.fim)
    if f.vinculo == "nenhum":
        return Secao(SECOES[FINANCEIRO], ["Item", "Valor"], [], vazio="O programa ainda não tem orçamento no Financeiro.")
    linhas = [
        ["Orçado", _dinheiro(f.orcado)],
        ["Realizado (lançamentos aprovados)", _dinheiro(f.realizado)],
        ["Saldo", _dinheiro(f.saldo)],
        ["Executado do orçamento", _porcento(f.percentual_executado)],
    ]
    return Secao(SECOES[FINANCEIRO], ["Item", "Valor"], linhas, nota="Valores do Financeiro no mesmo período, pelo mesmo cálculo da Visão integrada.")


# --- Montagem ---------------------------------------------------------------------------


def validar(finalidade: str, secoes: Sequence[str]) -> List[str]:
    if finalidade not in FINALIDADES:
        raise DadosInvalidos(FINALIDADE_INVALIDA)
    escolhidas = list(dict.fromkeys(secoes))
    if not escolhidas:
        raise DadosInvalidos(SEM_SECAO)
    desconhecidas = [s for s in escolhidas if s not in SECOES]
    if desconhecidas:
        raise DadosInvalidos(SECAO_INVALIDA.format(", ".join(desconhecidas)))
    # Na ordem do relatório, não na ordem pedida.
    return [s for s in SECOES if s in escolhidas]


def montar(
    conexao: Connection,
    programa_id: str,
    recorte: indicadores.Periodo,
    *,
    finalidade: str,
    secoes: Sequence[str],
    evidencias_escolhidas: Optional[Sequence[str]] = None,
    com_financeiro: bool = False,
    emitido_por: str = "",
    hoje: Optional[date] = None,
    agora: Optional[datetime] = None,
) -> Relatorio:
    """Relatório do programa no período. ``com_financeiro`` falso tira a seção financeira."""
    hoje = hoje or date.today()
    agora = agora or datetime.now(timezone.utc)
    escolhidas = validar(finalidade, secoes)
    if not com_financeiro:
        escolhidas = [s for s in escolhidas if s != FINANCEIRO]
        if not escolhidas:
            raise DadosInvalidos(SEM_SECAO)
    programa = buscar_programa(conexao, programa_id)

    evidencias = _evidencias(conexao, programa_id, recorte, hoje) if EVIDENCIAS in escolhidas else []
    disponiveis = [EvidenciaDoPeriodo(e["id"], e["data"], e["turma"], e["liberada_externa"]) for e in evidencias]
    if evidencias_escolhidas is not None:
        escolha = set(evidencias_escolhidas)
        evidencias = [e for e in evidencias if e["id"] in escolha]

    secoes_do_documento = []
    for secao in escolhidas:
        if secao == PLANO:
            secoes_do_documento.append(_secao_plano(conexao, programa_id, recorte))
        elif secao == PESSOAS:
            secoes_do_documento.append(_secao_pessoas(conexao, programa_id, recorte, finalidade))
        elif secao == ATIVIDADES:
            secoes_do_documento.append(_secao_atividades(conexao, programa_id, recorte, finalidade))
        elif secao == INDICADORES:
            secoes_do_documento.append(_secao_indicadores(conexao, programa_id, recorte))
        elif secao == EVIDENCIAS:
            secoes_do_documento.append(_secao_evidencias(evidencias, finalidade))
        elif secao == FINANCEIRO:
            secoes_do_documento.append(_secao_financeiro(conexao, programa, recorte))

    # Pendências antes da versão final.
    p = indicadores.pendencias(conexao, [programa_id], recorte, hoje).totais
    pendencias = [Pendencia("chamadas_sem_registro", "Chamadas sem registro no período", p.chamadas_sem_registro)]
    if EVIDENCIAS in escolhidas:
        pendencias.append(Pendencia("encontros_sem_evidencia", "Encontros sem evidência", p.encontros_sem_evidencia))
    if finalidade == EXTERNA:
        pendencias.append(Pendencia("autorizacoes_de_imagem_vencidas", "Autorizações de imagem vencidas ou revogadas", p.autorizacoes_de_imagem_vencidas))
        if EVIDENCIAS in escolhidas:
            bloqueadas = sum(1 for e in evidencias if not e["liberada_externa"])
            pendencias.append(Pendencia("evidencias_nao_liberadas", "Evidências escolhidas fora do relatório externo (falta autorização de imagem)", bloqueadas))
    pendencias = [x for x in pendencias if x.quantidade > 0]

    cabecalho = [
        ("Programa", f"{programa.nome} ({programa.identificador})" if programa.identificador else programa.nome),
        ("Período", f"{_data(recorte.inicio)} a {_data(recorte.fim)}" + ("" if recorte.fechado else " (em aberto)")),
        ("Finalidade", FINALIDADES[finalidade]),
        ("Emitido em", agora.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")),
    ]
    if emitido_por:
        cabecalho.append(("Emitido por", emitido_por))
    rodape = (
        "Documento para circulação externa: sem dados pessoais identificáveis."
        if finalidade == EXTERNA
        else "Documento de consulta interna: contém dados pessoais protegidos pela LGPD. Não circular fora da instituição."
    )
    documento = Documento(
        titulo=f"{TITULO} — {programa.nome} — {_data(recorte.inicio)} a {_data(recorte.fim)}",
        cabecalho=cabecalho,
        secoes=secoes_do_documento,
        rodape=rodape,
        autor="MDCA · Gestão",
        assunto=f"{TITULO} · {FINALIDADES[finalidade]}",
        colunas_numericas=NUMERICAS,
    )
    return Relatorio(
        programa_id=programa_id,
        programa=programa.nome,
        periodo=recorte,
        finalidade=finalidade,
        secoes=escolhidas,
        documento=documento,
        pendencias=pendencias,
        evidencias_disponiveis=disponiveis,
    )
