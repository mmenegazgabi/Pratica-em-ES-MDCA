from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class StatusLancamento(Enum):
    APROVADO = "aprovado"
    PENDENTE = "pendente"
    REJEITADO = "rejeitado"


@dataclass
class Lancamento:
    valor: float
    status: StatusLancamento


@dataclass
class Orcamento:
    id: str
    projeto_id: str
    valor_total: float
    data_inicio: date
    data_fim: date
    categorias_despesa: list[str]
    lancamentos: list[Lancamento] = field(default_factory=list)

    @property
    def saldo(self) -> float:
        realizado = sum(
            lancamento.valor
            for lancamento in self.lancamentos
            if lancamento.status == StatusLancamento.APROVADO
        )
        return self.valor_total - realizado
