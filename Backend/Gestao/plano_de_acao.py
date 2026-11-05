"""Plano de ação de um programa (US-02, tabelas da T-45): objetivos, ações, metas e os
registros do que foi realizado, mais o painel de acompanhamento.

O período de cada ação precisa caber na vigência do programa; essa regra depende de
outra tabela, por isso fica aqui e não num CHECK. O realizado de uma meta é a soma dos
seus registros.

As funções não fazem commit: a rota decide quando a operação termina.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from Gestao.programas import (
    DadosInvalidos,
    NaoEncontrado,
    buscar_programa,
    faltando,
    formatar_data,
    texto,
)

PERIODICIDADES = ("semanal", "quinzenal", "mensal", "bimestral", "trimestral", "semestral", "anual")


@dataclass(frozen=True)
class Objetivo:
    id: str
    descricao: str


@dataclass(frozen=True)
class Acao:
    id: str
    objetivo_id: str
    descricao: str
    periodo_inicio: date
    periodo_fim: date
    resultado_esperado: str
    periodicidade: str


@dataclass(frozen=True)
class Meta:
    id: str
    acao_id: str
    descricao: str
    valor_planejado: Decimal
    unidade: Optional[str]


@dataclass(frozen=True)
class RegistroMeta:
    id: str
    meta_id: str
    data: date
    valor_realizado: Decimal
    observacao: Optional[str]


@dataclass(frozen=True)
class AcompanhamentoMeta:
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
class Painel:
    programa_id: str
    metas: List[AcompanhamentoMeta]


def percentual(realizado: Decimal, planejado: Decimal) -> Decimal:
    """Realizado sobre planejado, em %, com uma casa. Pode passar de 100."""
    return (realizado / planejado * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


# ---- Objetivos ---------------------------------------------------------------------


def listar_objetivos(conexao: Connection, programa_id: str) -> List[Objetivo]:
    buscar_programa(conexao, programa_id)
    linhas = conexao.execute(
        sa.text(
            "SELECT id, descricao FROM objetivos WHERE programa_id = :programa "
            "ORDER BY lower(descricao), id"
        ),
        {"programa": programa_id},
    )
    return [Objetivo(**linha._mapping) for linha in linhas]


def cadastrar_objetivo(conexao: Connection, programa_id: str, *, descricao: Optional[str]) -> Objetivo:
    buscar_programa(conexao, programa_id)
    objetivo = Objetivo(id=str(uuid.uuid4()), descricao=texto(descricao))
    if not objetivo.descricao:
        raise faltando(["descrição"], "Objetivo")
    conexao.execute(
        sa.text("INSERT INTO objetivos (id, programa_id, descricao) VALUES (:id, :programa, :descricao)"),
        {"id": objetivo.id, "programa": programa_id, "descricao": objetivo.descricao},
    )
    return objetivo


# ---- Ações -------------------------------------------------------------------------

_SELECIONAR_ACOES = """
    SELECT a.id, a.objetivo_id, a.descricao, a.periodo_inicio, a.periodo_fim,
           a.resultado_esperado, a.periodicidade
    FROM acoes a
    JOIN objetivos o ON o.id = a.objetivo_id
    WHERE o.programa_id = :programa
"""


def listar_acoes(conexao: Connection, programa_id: str) -> List[Acao]:
    buscar_programa(conexao, programa_id)
    linhas = conexao.execute(
        sa.text(f"{_SELECIONAR_ACOES} ORDER BY a.periodo_inicio, lower(a.descricao), a.id"),
        {"programa": programa_id},
    )
    return [Acao(**linha._mapping) for linha in linhas]


def cadastrar_acao(
    conexao: Connection,
    programa_id: str,
    *,
    objetivo_id: Optional[str],
    descricao: Optional[str],
    periodo_inicio: Optional[date],
    periodo_fim: Optional[date],
    resultado_esperado: Optional[str],
    periodicidade: Optional[str],
) -> Acao:
    programa = buscar_programa(conexao, programa_id)
    objetivo_id, descricao = texto(objetivo_id), texto(descricao)
    resultado_esperado = texto(resultado_esperado)
    periodicidade = (texto(periodicidade) or "").lower() or None

    ausentes = [
        rotulo
        for rotulo, valor in (
            ("objetivo", objetivo_id),
            ("descrição", descricao),
            ("período (início e fim)", periodo_inicio and periodo_fim),
            ("resultado esperado", resultado_esperado),
            ("periodicidade", periodicidade),
        )
        if not valor
    ]
    if ausentes:
        raise faltando(ausentes, "Ação")
    if periodicidade not in PERIODICIDADES:
        raise DadosInvalidos(
            "Periodicidade inválida. Use uma destas: " + ", ".join(PERIODICIDADES) + "."
        )
    if periodo_fim < periodo_inicio:
        raise DadosInvalidos("O fim do período da ação não pode ser anterior ao início.")
    # Programas antigos, sem vigência, não têm contra o que conferir.
    if programa.vigencia_inicio and programa.vigencia_fim and (
        periodo_inicio < programa.vigencia_inicio or periodo_fim > programa.vigencia_fim
    ):
        raise DadosInvalidos(
            "O período da ação deve estar dentro da vigência do programa "
            f"({formatar_data(programa.vigencia_inicio)} a {formatar_data(programa.vigencia_fim)})."
        )
    objetivo_do_programa = conexao.execute(
        sa.text("SELECT 1 FROM objetivos WHERE id = :id AND programa_id = :programa"),
        {"id": objetivo_id, "programa": programa_id},
    ).first()
    if objetivo_do_programa is None:
        raise DadosInvalidos("Objetivo não encontrado neste programa.")

    acao = Acao(
        id=str(uuid.uuid4()),
        objetivo_id=objetivo_id,
        descricao=descricao,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        resultado_esperado=resultado_esperado,
        periodicidade=periodicidade,
    )
    conexao.execute(
        sa.text(
            """
            INSERT INTO acoes (id, objetivo_id, descricao, periodo_inicio, periodo_fim,
                               resultado_esperado, periodicidade)
            VALUES (:id, :objetivo_id, :descricao, :periodo_inicio, :periodo_fim,
                    :resultado_esperado, :periodicidade)
            """
        ),
        acao.__dict__,
    )
    return acao


# ---- Metas e registros -------------------------------------------------------------

_SELECIONAR_METAS = """
    SELECT m.id, m.acao_id, m.descricao, m.valor_planejado, m.unidade
    FROM metas m
    JOIN acoes a ON a.id = m.acao_id
    JOIN objetivos o ON o.id = a.objetivo_id
    WHERE o.programa_id = :programa
"""


def listar_metas(conexao: Connection, programa_id: str) -> List[Meta]:
    buscar_programa(conexao, programa_id)
    linhas = conexao.execute(
        sa.text(f"{_SELECIONAR_METAS} ORDER BY lower(m.descricao), m.id"),
        {"programa": programa_id},
    )
    return [Meta(**linha._mapping) for linha in linhas]


def cadastrar_meta(
    conexao: Connection,
    programa_id: str,
    *,
    acao_id: Optional[str],
    descricao: Optional[str],
    valor_planejado: Optional[Decimal],
    unidade: Optional[str] = None,
) -> Meta:
    buscar_programa(conexao, programa_id)
    acao_id, descricao = texto(acao_id), texto(descricao)
    ausentes = [
        rotulo
        for rotulo, valor in (
            ("ação", acao_id),
            ("descrição", descricao),
            ("valor planejado", valor_planejado),
        )
        if valor is None
    ]
    if ausentes:
        raise faltando(ausentes, "Meta")
    if valor_planejado <= 0:
        raise DadosInvalidos("O valor planejado da meta deve ser maior que zero.")
    acao_do_programa = conexao.execute(
        sa.text(f"{_SELECIONAR_ACOES} AND a.id = :id"), {"programa": programa_id, "id": acao_id}
    ).first()
    if acao_do_programa is None:
        raise DadosInvalidos("Ação não encontrada neste programa.")

    meta = Meta(
        id=str(uuid.uuid4()),
        acao_id=acao_id,
        descricao=descricao,
        valor_planejado=valor_planejado,
        unidade=texto(unidade),
    )
    conexao.execute(
        sa.text(
            "INSERT INTO metas (id, acao_id, descricao, valor_planejado, unidade) "
            "VALUES (:id, :acao_id, :descricao, :valor_planejado, :unidade)"
        ),
        meta.__dict__,
    )
    return meta


def _buscar_meta(conexao: Connection, programa_id: str, meta_id: str) -> Meta:
    buscar_programa(conexao, programa_id)
    linha = conexao.execute(
        sa.text(f"{_SELECIONAR_METAS} AND m.id = :id"), {"programa": programa_id, "id": meta_id}
    ).first()
    if linha is None:
        raise NaoEncontrado("Meta não encontrada neste programa.")
    return Meta(**linha._mapping)


def listar_registros(conexao: Connection, programa_id: str, meta_id: str) -> List[RegistroMeta]:
    _buscar_meta(conexao, programa_id, meta_id)
    linhas = conexao.execute(
        sa.text(
            "SELECT id, meta_id, data, valor_realizado, observacao FROM registros_meta "
            "WHERE meta_id = :meta ORDER BY data, criado_em, id"
        ),
        {"meta": meta_id},
    )
    return [RegistroMeta(**linha._mapping) for linha in linhas]


def registrar_realizado(
    conexao: Connection,
    programa_id: str,
    meta_id: str,
    *,
    data: Optional[date],
    valor_realizado: Optional[Decimal],
    observacao: Optional[str] = None,
) -> RegistroMeta:
    _buscar_meta(conexao, programa_id, meta_id)
    ausentes = [r for r, v in (("data", data), ("valor realizado", valor_realizado)) if v is None]
    if ausentes:
        raise faltando(ausentes, "Registro")
    if valor_realizado <= 0:
        raise DadosInvalidos("O valor realizado deve ser maior que zero.")
    registro = RegistroMeta(
        id=str(uuid.uuid4()),
        meta_id=meta_id,
        data=data,
        valor_realizado=valor_realizado,
        observacao=texto(observacao),
    )
    conexao.execute(
        sa.text(
            "INSERT INTO registros_meta (id, meta_id, data, valor_realizado, observacao) "
            "VALUES (:id, :meta_id, :data, :valor_realizado, :observacao)"
        ),
        registro.__dict__,
    )
    return registro


# ---- Painel ------------------------------------------------------------------------


def painel(conexao: Connection, programa_id: str) -> Painel:
    """Planejado, realizado e percentual de cada meta do programa."""
    buscar_programa(conexao, programa_id)
    linhas = conexao.execute(
        sa.text(
            """
            SELECT m.id AS meta_id, m.descricao, m.unidade,
                   a.id AS acao_id, a.descricao AS acao,
                   o.id AS objetivo_id, o.descricao AS objetivo,
                   m.valor_planejado AS planejado,
                   coalesce(sum(r.valor_realizado), 0) AS realizado
            FROM metas m
            JOIN acoes a ON a.id = m.acao_id
            JOIN objetivos o ON o.id = a.objetivo_id
            LEFT JOIN registros_meta r ON r.meta_id = m.id
            WHERE o.programa_id = :programa
            GROUP BY m.id, a.id, o.id
            ORDER BY lower(o.descricao), a.periodo_inicio, lower(m.descricao), m.id
            """
        ),
        {"programa": programa_id},
    )
    metas = [
        AcompanhamentoMeta(
            **linha._mapping,
            percentual=percentual(Decimal(linha.realizado), Decimal(linha.planejado)),
        )
        for linha in linhas
    ]
    return Painel(programa_id=programa_id, metas=metas)
