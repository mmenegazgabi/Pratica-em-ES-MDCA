"""Indicadores agregados por programa e período (T-72 · US-10).

Um cálculo só, usado pelo painel de Indicadores (T-73), pela Visão geral (T-91) e,
depois, pelo relatório técnico (US-11). Todos os números de uma consulta usam o mesmo
recorte: os mesmos programas e o mesmo período.

- **Registros válidos:** são os que já estão gravados. A chamada só é aceita quando o
  encontro termina e não muda depois (US-05), então o que está no banco é o que conta.
- **Período fechado:** quando o fim do período já passou (``fim < hoje``). Um período
  que inclui hoje ou o futuro está **em aberto**: os números ainda podem mudar com as
  próximas chamadas. Não existe fechamento manual.
- **Sem dados pessoais:** a resposta só tem contagens, somas e percentuais por programa.
  Nenhum nome, id ou data de pessoa sai daqui.

Indicadores de cada recorte:

- **Pessoas acompanhadas:** pessoas distintas com matrícula na turma durante o período
  (entrou até o fim e não saiu antes do início). Lista de espera não conta. No total,
  quem está em dois programas conta uma vez.
- **Encontros realizados:** encontros (atividades com chamada) com data no período.
- **Presenças e ausências:** linhas das chamadas desses encontros. Ausência justificada
  também é ausência.
- **Frequência:** presenças sobre o total da chamada, em %, com uma casa; vazio sem chamada.
- **Horas de atividades:** soma da duração da turma (fim menos início) de cada encontro.
- **Metas:** as metas do plano de ação com o realizado **acumulado até o fim do período**
  (o mesmo cálculo da Visão integrada) e a média dos percentuais. As metas têm unidades
  diferentes, por isso não se somam: só os percentuais.

As funções só leem; não fazem commit.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from Gestao.erros import DadosInvalidos
from Gestao.plano_de_acao import percentual
from Gestao.visao_integrada import execucao_fisica

MAXIMO_DIAS_NO_PERIODO = 366
FIM_ANTES_DO_INICIO = "O fim do período não pode ser anterior ao início."
PERIODO_LONGO_DEMAIS = f"O período pode ter no máximo {MAXIMO_DIAS_NO_PERIODO} dias."


@dataclass(frozen=True)
class Periodo:
    inicio: date
    fim: date
    # True quando o fim já passou; False quando os números ainda podem mudar.
    fechado: bool


@dataclass(frozen=True)
class Numeros:
    pessoas_acompanhadas: int
    encontros_realizados: int
    presencas: int
    ausencias: int
    # Presenças sobre o total das chamadas, em %; None quando não houve chamada.
    frequencia: Optional[Decimal]
    horas_de_atividades: Decimal
    metas: int
    # Média dos percentuais das metas até o fim do período; None sem metas.
    percentual_medio_das_metas: Optional[Decimal]


@dataclass(frozen=True)
class ProgramaNoRecorte:
    programa_id: str
    nome: str
    identificador: Optional[str]
    numeros: Numeros


@dataclass(frozen=True)
class Indicadores:
    periodo: Periodo
    totais: Numeros
    programas: List[ProgramaNoRecorte]


def mes_de(dia: date) -> tuple:
    """Primeiro e último dia do mês de ``dia``."""
    inicio = dia.replace(day=1)
    proximo = (inicio + timedelta(days=32)).replace(day=1)
    return inicio, proximo - timedelta(days=1)


def periodo(inicio: Optional[date], fim: Optional[date], hoje: date) -> Periodo:
    """Período do recorte; sem datas, o mês de hoje."""
    padrao_inicio, padrao_fim = mes_de(hoje)
    inicio = inicio or (mes_de(fim)[0] if fim else padrao_inicio)
    fim = fim or (mes_de(inicio)[1] if inicio else padrao_fim)
    if fim < inicio:
        raise DadosInvalidos(FIM_ANTES_DO_INICIO)
    if (fim - inicio).days + 1 > MAXIMO_DIAS_NO_PERIODO:
        raise DadosInvalidos(PERIODO_LONGO_DEMAIS)
    return Periodo(inicio=inicio, fim=fim, fechado=fim < hoje)


def _frequencia(presencas: int, ausencias: int) -> Optional[Decimal]:
    total = presencas + ausencias
    if not total:
        return None
    return percentual(Decimal(presencas), Decimal(total))


def _media(percentuais: Sequence[Decimal]) -> Optional[Decimal]:
    if not percentuais:
        return None
    return (sum(percentuais) / len(percentuais)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _horas(valor) -> Decimal:
    return Decimal(str(valor or 0)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _programas(conexao: Connection, programa_ids: Optional[Sequence[str]]) -> List[sa.Row]:
    """Programas do recorte, em ordem de nome; ``None`` são todos."""
    if programa_ids is not None and not programa_ids:
        return []
    filtro = "" if programa_ids is None else "WHERE id = ANY(:ids)"
    return list(
        conexao.execute(
            sa.text(f"SELECT id, nome, identificador FROM projetos {filtro} ORDER BY lower(nome), id"),
            {"ids": list(programa_ids or [])},
        )
    )


_PESSOAS = """
    FROM matriculas m
    JOIN turmas t ON t.id = m.turma_id
    WHERE t.programa_id = ANY(:ids)
      AND m.situacao <> 'espera'
      AND m.data_entrada IS NOT NULL AND m.data_entrada <= :fim
      AND (m.data_saida IS NULL OR m.data_saida > :inicio)
"""


def calcular(
    conexao: Connection,
    programa_ids: Optional[Sequence[str]],
    recorte: Periodo,
) -> Indicadores:
    """Indicadores dos programas (``None`` = todos) no período, por programa e no total."""
    programas = _programas(conexao, programa_ids)
    ids = [p.id for p in programas]
    parametros = {"ids": ids, "inicio": recorte.inicio, "fim": recorte.fim}

    pessoas: Dict[str, int] = dict(
        conexao.execute(
            sa.text(f"SELECT t.programa_id, count(DISTINCT m.pessoa_id) {_PESSOAS} GROUP BY t.programa_id"),
            parametros,
        ).all()
    )
    pessoas_no_total = conexao.execute(
        sa.text(f"SELECT count(DISTINCT m.pessoa_id) {_PESSOAS}"), parametros
    ).scalar_one()

    chamadas = {
        linha.programa_id: linha
        for linha in conexao.execute(
            sa.text(
                """
                SELECT a.programa_id,
                       count(DISTINCT a.id) AS encontros,
                       count(c.id) FILTER (WHERE c.presente) AS presencas,
                       count(c.id) FILTER (WHERE NOT c.presente) AS ausencias
                FROM atividades a
                LEFT JOIN chamadas c ON c.atividade_id = a.id
                WHERE a.programa_id = ANY(:ids) AND a.data BETWEEN :inicio AND :fim
                GROUP BY a.programa_id
                """
            ),
            parametros,
        )
    }
    horas: Dict[str, Decimal] = {
        programa_id: _horas(valor)
        for programa_id, valor in conexao.execute(
            sa.text(
                """
                SELECT a.programa_id,
                       sum(extract(epoch FROM t.hora_fim - t.hora_inicio)) / 3600
                FROM atividades a
                JOIN turmas t ON t.id = a.turma_id
                WHERE a.programa_id = ANY(:ids) AND a.data BETWEEN :inicio AND :fim
                GROUP BY a.programa_id
                """
            ),
            parametros,
        ).all()
    }

    por_programa: List[ProgramaNoRecorte] = []
    todas_as_metas: List[Decimal] = []
    for programa in programas:
        linha = chamadas.get(programa.id)
        encontros, presencas, ausencias = (linha.encontros, linha.presencas, linha.ausencias) if linha else (0, 0, 0)
        metas = execucao_fisica(conexao, programa.id, None, recorte.fim).metas
        todas_as_metas.extend(m.percentual for m in metas)
        por_programa.append(
            ProgramaNoRecorte(
                programa_id=programa.id,
                nome=programa.nome,
                identificador=programa.identificador,
                numeros=Numeros(
                    pessoas_acompanhadas=pessoas.get(programa.id, 0),
                    encontros_realizados=encontros,
                    presencas=presencas,
                    ausencias=ausencias,
                    frequencia=_frequencia(presencas, ausencias),
                    horas_de_atividades=horas.get(programa.id, _horas(0)),
                    metas=len(metas),
                    percentual_medio_das_metas=_media([m.percentual for m in metas]),
                ),
            )
        )

    presencas = sum(p.numeros.presencas for p in por_programa)
    ausencias = sum(p.numeros.ausencias for p in por_programa)
    totais = Numeros(
        pessoas_acompanhadas=pessoas_no_total,
        encontros_realizados=sum(p.numeros.encontros_realizados for p in por_programa),
        presencas=presencas,
        ausencias=ausencias,
        frequencia=_frequencia(presencas, ausencias),
        horas_de_atividades=_horas(sum((p.numeros.horas_de_atividades for p in por_programa), Decimal(0))),
        metas=len(todas_as_metas),
        percentual_medio_das_metas=_media(todas_as_metas),
    )
    return Indicadores(periodo=recorte, totais=totais, programas=por_programa)
