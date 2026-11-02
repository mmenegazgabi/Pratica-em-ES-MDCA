"""Resumo orçado x realizado por projeto para o dashboard da Diretoria (T-29 · US-07).

Com período informado:

- orçado: soma do ``valor_total`` dos orçamentos cuja vigência cruza o período;
- realizado: soma dos lançamentos aprovados com ``data_despesa`` no período
  (lançamento sem data da despesa fica de fora, porque não dá para situá-lo);
- saldo: orçado - realizado.

Sem período, entram todos os orçamentos e todos os lançamentos aprovados.
As somas são feitas em centavos para não acumular erro de float.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, List, Optional

if __package__:
    from .orcamento import Lancamento, Orcamento, StatusLancamento
    from .projetos import Projeto, StatusProjeto
else:
    from orcamento import Lancamento, Orcamento, StatusLancamento
    from projetos import Projeto, StatusProjeto

_CENTAVO = Decimal("0.01")


@dataclass
class ResumoProjeto:
    projeto_id: str
    nome: str
    status: StatusProjeto
    orcado: float
    realizado: float
    saldo: float


def _em_centavos(valor: float) -> Decimal:
    return Decimal(str(valor)).quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def _no_periodo(dia: date, inicio: Optional[date], fim: Optional[date]) -> bool:
    return (inicio is None or dia >= inicio) and (fim is None or dia <= fim)


def _cruza_periodo(orcamento: Orcamento, inicio: Optional[date], fim: Optional[date]) -> bool:
    return (fim is None or orcamento.data_inicio <= fim) and (
        inicio is None or orcamento.data_fim >= inicio
    )


def _conta_no_realizado(
    lancamento: Lancamento, inicio: Optional[date], fim: Optional[date]
) -> bool:
    if lancamento.status != StatusLancamento.APROVADO:
        return False
    if inicio is None and fim is None:
        return True
    return lancamento.data_despesa is not None and _no_periodo(
        lancamento.data_despesa, inicio, fim
    )


def resumo_por_projeto(
    projetos: Iterable[Projeto],
    orcamentos: Iterable[Orcamento],
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    status: Optional[StatusProjeto] = None,
) -> List[ResumoProjeto]:
    orcamentos = list(orcamentos)
    resumos = []
    for projeto in projetos:
        if status is not None and projeto.status != status:
            continue
        orcado = Decimal(0)
        realizado = Decimal(0)
        for orcamento in orcamentos:
            if orcamento.projeto_id != projeto.id:
                continue
            if _cruza_periodo(orcamento, data_inicio, data_fim):
                orcado += _em_centavos(orcamento.valor_total)
            realizado += sum(
                (
                    _em_centavos(l.valor)
                    for l in orcamento.lancamentos
                    if _conta_no_realizado(l, data_inicio, data_fim)
                ),
                Decimal(0),
            )
        resumos.append(
            ResumoProjeto(
                projeto_id=projeto.id,
                nome=projeto.nome,
                status=projeto.status,
                orcado=float(orcado),
                realizado=float(realizado),
                saldo=float(orcado - realizado),
            )
        )
    return resumos
