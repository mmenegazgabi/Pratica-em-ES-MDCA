import math
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

if __package__:
    from .moeda import formatar_reais
else:
    from moeda import formatar_reais


class StatusLancamento(Enum):
    APROVADO = "aprovado"
    PENDENTE = "pendente"
    REJEITADO = "rejeitado"


class LancamentoNaoEncontrado(ValueError):
    pass


class AprovacaoInvalida(ValueError):
    pass


class LancamentoInvalido(ValueError):
    """Dados do lançamento não batem com o orçamento (T-12)."""


class ConciliacaoInvalida(ValueError):
    """Lançamento não pode ser conciliado no estado atual (T-21)."""


@dataclass
class Lancamento:
    valor: float
    status: StatusLancamento
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # T-12 · US-03: dados da despesa e chave do comprovante no R2.
    descricao: str = ""
    categoria: str = ""
    data_despesa: Optional[date] = None
    comprovante_chave: Optional[str] = None
    # T-16 · US-04: motivo informado por quem rejeitou.
    motivo_rejeicao: Optional[str] = None
    # Redesign Financeiro: motivos de rejeições já corrigidas e reenviadas.
    motivos_rejeicao_anteriores: list[str] = field(default_factory=list)
    # T-17 · US-04: quem lançou, para receber a notificação do resultado.
    autor_id: Optional[str] = None
    # T-18 · US-04: quando foi lançado, para a fila de aprovação mostrar
    # primeiro o que está esperando há mais tempo.
    criado_em: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Redesign Financeiro: quando foi aprovado, para a lista de lançamentos.
    aprovado_em: Optional[datetime] = None
    # T-21 · US-05: vínculo com o item do extrato bancário.
    conciliado: bool = False
    referencia_extrato: Optional[str] = None


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

    def aprovar_lancamento(self, lancamento_id: str) -> Lancamento:
        # T-15 · US-04: só "pendente -> aprovado" é transição válida; aprovar
        # de novo é erro (antes era ignorado), e o saldo continua debitado
        # uma única vez.
        with self._lock:
            lancamento = self._buscar_lancamento(lancamento_id)
            if lancamento.status == StatusLancamento.APROVADO:
                raise AprovacaoInvalida("Lançamento já está aprovado")
            if lancamento.status == StatusLancamento.REJEITADO:
                raise AprovacaoInvalida(
                    "Lançamento rejeitado não pode ser aprovado"
                )

            lancamento.status = StatusLancamento.APROVADO
            lancamento.aprovado_em = datetime.now(timezone.utc)
            self.saldo_atual -= lancamento.valor
            return lancamento

    def editar(
        self,
        *,
        valor_total: float,
        data_inicio: date,
        data_fim: date,
        categorias_despesa: list[str],
    ) -> None:
        # Redesign Financeiro: a coordenação ajusta valor, vigência e
        # categorias; o saldo é recalculado sobre o que já foi aprovado.
        if not categorias_despesa:
            raise LancamentoInvalido("Informe ao menos uma categoria.")
        if data_fim < data_inicio:
            raise LancamentoInvalido("data_fim não pode ser anterior a data_inicio")
        with self._lock:
            realizado = self.valor_total - self.saldo_atual
            if valor_total < realizado:
                raise LancamentoInvalido(
                    "O valor total não pode ser menor que o já gasto "
                    f"({formatar_reais(realizado)})."
                )
            for categoria in self.categorias_despesa:
                if categoria in categorias_despesa:
                    continue
                if any(
                    l.categoria == categoria
                    and l.status != StatusLancamento.REJEITADO
                    for l in self.lancamentos
                ):
                    raise LancamentoInvalido(
                        f'A categoria "{categoria}" tem lançamentos e não pode ser removida.'
                    )
            self.valor_total = valor_total
            self.data_inicio = data_inicio
            self.data_fim = data_fim
            self.categorias_despesa = list(categorias_despesa)
            self.saldo_atual = valor_total - realizado

    def reverter_aprovacao(self, lancamento_id: str) -> None:
        with self._lock:
            lancamento = self._buscar_lancamento(lancamento_id)
            if lancamento.status != StatusLancamento.APROVADO:
                raise AprovacaoInvalida("Lançamento não está aprovado")

            lancamento.status = StatusLancamento.PENDENTE
            lancamento.aprovado_em = None
            self.saldo_atual += lancamento.valor

    def rejeitar_lancamento(self, lancamento_id: str, motivo: str) -> Lancamento:
        # T-16 · US-04: só "pendente -> rejeitado" é transição válida. Como
        # pendente nunca entrou no saldo, rejeitar não altera o saldo.
        motivo = (motivo or "").strip()
        if not motivo:
            raise LancamentoInvalido("Motivo da rejeição é obrigatório.")
        with self._lock:
            lancamento = self._buscar_lancamento(lancamento_id)
            if lancamento.status == StatusLancamento.REJEITADO:
                raise AprovacaoInvalida("Lançamento já está rejeitado")
            if lancamento.status == StatusLancamento.APROVADO:
                raise AprovacaoInvalida(
                    "Lançamento aprovado não pode ser rejeitado"
                )
            lancamento.status = StatusLancamento.REJEITADO
            lancamento.motivo_rejeicao = motivo
            return lancamento

    def reenviar_lancamento(
        self,
        lancamento_id: str,
        *,
        valor: float,
        descricao: str,
        categoria: str,
        data_despesa: date,
        comprovante_chave: Optional[str],
    ) -> Lancamento:
        # Redesign Financeiro: corrige uma despesa rejeitada e a devolve para
        # a fila. Não mexe no saldo (rejeitada nunca entrou nele).
        with self._lock:
            lancamento = self._buscar_lancamento(lancamento_id)
            if lancamento.status != StatusLancamento.REJEITADO:
                raise AprovacaoInvalida("Só despesas rejeitadas podem ser reenviadas")
            self.validar_lancamento(valor, categoria, data_despesa)
            if lancamento.motivo_rejeicao:
                lancamento.motivos_rejeicao_anteriores.append(lancamento.motivo_rejeicao)
            lancamento.motivo_rejeicao = None
            lancamento.valor = valor
            lancamento.descricao = descricao
            lancamento.categoria = categoria
            lancamento.data_despesa = data_despesa
            if comprovante_chave is not None:
                lancamento.comprovante_chave = comprovante_chave
            lancamento.status = StatusLancamento.PENDENTE
            lancamento.criado_em = datetime.now(timezone.utc)
            return lancamento

    def conciliar_lancamento(
        self, lancamento_id: str, referencia_extrato: str
    ) -> Lancamento:
        # T-21 · US-05: só lançamento aprovado pode ser conciliado. Repetir
        # com a mesma referência é idempotente; com outra referência é erro,
        # para não trocar o vínculo com o extrato sem querer.
        referencia_extrato = (referencia_extrato or "").strip()
        if not referencia_extrato:
            raise LancamentoInvalido("Referência do extrato é obrigatória.")
        with self._lock:
            lancamento = self._buscar_lancamento(lancamento_id)
            if lancamento.status != StatusLancamento.APROVADO:
                raise ConciliacaoInvalida(
                    "Apenas lançamentos aprovados podem ser conciliados"
                )
            if lancamento.conciliado:
                if lancamento.referencia_extrato == referencia_extrato:
                    return lancamento
                raise ConciliacaoInvalida(
                    "Lançamento já está conciliado com outra referência do extrato"
                )
            lancamento.conciliado = True
            lancamento.referencia_extrato = referencia_extrato
            return lancamento

    def registrar_lancamento(self, lancamento: Lancamento) -> Lancamento:
        """Adiciona um lançamento novo, sempre como pendente de aprovação.

        Lançamento pendente não altera o saldo; só a aprovação (T-07) debita.
        """
        self.validar_lancamento(
            lancamento.valor, lancamento.categoria, lancamento.data_despesa
        )
        with self._lock:
            lancamento.status = StatusLancamento.PENDENTE
            self.lancamentos.append(lancamento)
        return lancamento

    def validar_lancamento(
        self, valor: float, categoria: str, data_despesa: Optional[date]
    ) -> None:
        if not math.isfinite(valor) or valor <= 0:
            raise LancamentoInvalido("O valor do lançamento deve ser maior que zero.")
        if categoria not in self.categorias_despesa:
            raise LancamentoInvalido(
                "Categoria não pertence ao orçamento. Categorias válidas: "
                + ", ".join(self.categorias_despesa)
            )
        if data_despesa is not None and not (
            self.data_inicio <= data_despesa <= self.data_fim
        ):
            raise LancamentoInvalido(
                "A data da despesa está fora da vigência do orçamento."
            )
