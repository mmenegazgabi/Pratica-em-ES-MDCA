"""Visão integrada da execução física e financeira de um programa (T-78 · US-12).

- **Física (Gestão):** cada meta do plano de ação com planejado, realizado no período e
  percentual, a partir das tabelas da T-43 no PostgreSQL.
- **Financeira (Financeiro):** orçado, realizado (lançamentos aprovados) e saldo do
  projeto correspondente, calculados pela função de resumo do próprio Financeiro
  (``Financeiro/dashboard.resumo_por_projeto``, a mesma do dashboard da Diretoria).

O Financeiro ainda guarda projetos, orçamentos e lançamentos **em memória**, num cadastro
separado do canônico. Este módulo só **lê** esses dados, sem alterar nada do Financeiro,
e acha o projeto correspondente ao programa assim:

1. pelo **id** (vale quando o Financeiro passar a usar a tabela ``projetos``);
2. senão, pelo **nome**, sem diferenciar maiúsculas e acentos (a mesma regra que o
   Financeiro usa para não repetir nomes).

``vinculo`` diz qual dos dois casou (``id``, ``nome`` ou ``nenhum``). Os dados em memória
somem a cada reinício da API.
"""

import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from Gestao.plano_de_acao import percentual
from Gestao.programas import DadosInvalidos, ProgramaDetalhado, buscar_programa

VINCULO_ID = "id"
VINCULO_NOME = "nome"
VINCULO_NENHUM = "nenhum"


@dataclass(frozen=True)
class MetaNoPeriodo:
    meta_id: str
    descricao: str
    unidade: Optional[str]
    acao_id: str
    acao: str
    objetivo_id: str
    objetivo: str
    planejado: Decimal
    realizado: Decimal
    percentual: Decimal


@dataclass(frozen=True)
class ExecucaoFisica:
    metas: List[MetaNoPeriodo]
    # Média dos percentuais das metas (metas têm unidades diferentes); None sem metas.
    percentual_medio: Optional[Decimal]


@dataclass(frozen=True)
class ExecucaoFinanceira:
    vinculo: str
    projeto_id: Optional[str]
    projeto: Optional[str]
    orcado: float
    realizado: float
    saldo: float
    # Realizado sobre orçado, em %, com uma casa; None sem orçamento no período.
    percentual_executado: Optional[Decimal]


@dataclass(frozen=True)
class VisaoIntegrada:
    programa: ProgramaDetalhado
    inicio: Optional[date]
    fim: Optional[date]
    fisica: ExecucaoFisica
    # None quando o papel de quem consulta não vê valores financeiros.
    financeira: Optional[ExecucaoFinanceira]


def _chave(nome: str) -> str:
    decomposto = unicodedata.normalize("NFKD", nome.strip().casefold())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def execucao_fisica(
    conexao: Connection, programa_id: str, inicio: Optional[date], fim: Optional[date]
) -> ExecucaoFisica:
    """Metas do programa com o realizado registrado dentro do período (todo o período sem filtro)."""
    linhas = conexao.execute(
        sa.text(
            """
            SELECT m.id AS meta_id, m.descricao, m.unidade,
                   a.id AS acao_id, a.descricao AS acao,
                   o.id AS objetivo_id, o.descricao AS objetivo,
                   m.valor_planejado AS planejado,
                   coalesce(sum(r.valor_realizado) FILTER (
                       WHERE (CAST(:inicio AS date) IS NULL OR r.data >= :inicio)
                         AND (CAST(:fim AS date) IS NULL OR r.data <= :fim)
                   ), 0) AS realizado
            FROM metas m
            JOIN acoes a ON a.id = m.acao_id
            JOIN objetivos o ON o.id = a.objetivo_id
            LEFT JOIN registros_meta r ON r.meta_id = m.id
            WHERE o.programa_id = :programa
            GROUP BY m.id, a.id, o.id
            ORDER BY lower(o.descricao), a.periodo_inicio, lower(m.descricao), m.id
            """
        ),
        {"programa": programa_id, "inicio": inicio, "fim": fim},
    )
    metas = [
        MetaNoPeriodo(
            **linha._mapping,
            percentual=percentual(Decimal(linha.realizado), Decimal(linha.planejado)),
        )
        for linha in linhas
    ]
    medio = None
    if metas:
        medio = (sum(m.percentual for m in metas) / len(metas)).quantize(Decimal("0.1"))
    return ExecucaoFisica(metas=metas, percentual_medio=medio)


def execucao_financeira(
    programa: ProgramaDetalhado, inicio: Optional[date], fim: Optional[date]
) -> ExecucaoFinanceira:
    """Leitura dos dados em memória do Financeiro, sem alterá-los."""
    # Importados aqui: são os módulos da API integrada (Backend/main.py), os mesmos que
    # recebem os orçamentos e lançamentos.
    from Financeiro.dashboard import resumo_por_projeto
    from Financeiro.projetos import listar_projetos
    from Financeiro.routers.orcamentos import _orcamentos

    projetos = listar_projetos()
    projeto = next((p for p in projetos if p.id == programa.id), None)
    vinculo = VINCULO_ID
    if projeto is None:
        projeto = next((p for p in projetos if _chave(p.nome) == _chave(programa.nome)), None)
        vinculo = VINCULO_NOME
    if projeto is None:
        return ExecucaoFinanceira(VINCULO_NENHUM, None, None, 0.0, 0.0, 0.0, None)

    [resumo] = resumo_por_projeto([projeto], list(_orcamentos), inicio, fim)
    executado = None
    if resumo.orcado > 0:
        executado = percentual(Decimal(str(resumo.realizado)), Decimal(str(resumo.orcado)))
    return ExecucaoFinanceira(
        vinculo=vinculo,
        projeto_id=projeto.id,
        projeto=projeto.nome,
        orcado=resumo.orcado,
        realizado=resumo.realizado,
        saldo=resumo.saldo,
        percentual_executado=executado,
    )


def visao_integrada(
    conexao: Connection,
    programa_id: str,
    *,
    inicio: Optional[date] = None,
    fim: Optional[date] = None,
    com_financeiro: bool = True,
) -> VisaoIntegrada:
    if inicio and fim and fim < inicio:
        raise DadosInvalidos("O fim do período não pode ser anterior ao início.")
    programa = buscar_programa(conexao, programa_id)
    return VisaoIntegrada(
        programa=programa,
        inicio=inicio,
        fim=fim,
        fisica=execucao_fisica(conexao, programa_id, inicio, fim),
        financeira=execucao_financeira(programa, inicio, fim) if com_financeiro else None,
    )
