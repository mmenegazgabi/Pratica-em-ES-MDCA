import threading
import uuid
from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class StatusLancamento(Enum):
    APROVADO = "aprovado"
    PENDENTE = "pendente"
    REJEITADO = "rejeitado"


class LancamentoNaoEncontrado(ValueError):
    pass


class AprovacaoInvalida(ValueError):
    pass


@dataclass
class Lancamento:
    valor: float
    status: StatusLancamento
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class Orcamento:
    id: str
    projeto_id: str
    valor_total: float
    data_inicio: date
    data_fim: date
    categorias_despesa: list[str]
    lancamentos: list[Lancamento] = field(default_factory=list)
    saldo_atual: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        realizado = sum(
            lancamento.valor
            for lancamento in self.lancamentos
            if lancamento.status == StatusLancamento.APROVADO
        )
        self.saldo_atual = self.valor_total - realizado

    @property
    def saldo(self) -> float:
        return self.saldo_atual

    def _buscar_lancamento(self, lancamento_id: str) -> Lancamento:
        lancamento = next(
            (l for l in self.lancamentos if l.id == lancamento_id), None
        )
        if lancamento is None:
            raise LancamentoNaoEncontrado("Lançamento não encontrado")
        return lancamento

    def aprovar_lancamento(self, lancamento_id: str) -> None:
        with self._lock:
            lancamento = self._buscar_lancamento(lancamento_id)
            if lancamento.status == StatusLancamento.APROVADO:
                return
            if lancamento.status == StatusLancamento.REJEITADO:
                raise AprovacaoInvalida(
                    "Lançamento rejeitado não pode ser aprovado"
                )

            lancamento.status = StatusLancamento.APROVADO
            self.saldo_atual -= lancamento.valor

    def reverter_aprovacao(self, lancamento_id: str) -> None:
        with self._lock:
            lancamento = self._buscar_lancamento(lancamento_id)
            if lancamento.status != StatusLancamento.APROVADO:
                raise AprovacaoInvalida("Lançamento não está aprovado")

            lancamento.status = StatusLancamento.PENDENTE
            self.saldo_atual += lancamento.valor