from dataclasses import dataclass, field
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
    valor_total: float
    lancamentos: list[Lancamento] = field(default_factory=list)

    @property
    def saldo(self) -> float:
        realizado = sum(
            lancamento.valor
            for lancamento in self.lancamentos
            if lancamento.status == StatusLancamento.APROVADO
        )
        return self.valor_total - realizado
