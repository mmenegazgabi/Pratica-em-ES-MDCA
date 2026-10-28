import math
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Optional


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


class OrcamentoInvalido(ValueError):
    """Valor total e valores das categorias não fecham (US-01)."""


def formatar_reais(valor: float) -> str:
    """1234.5 -> "R$ 1.234,50"."""
    texto = f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


def _em_centavos(valor: float) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validar_categorias(
    valor_total: float,
    categorias: list[str],
    valores_categorias: dict[str, float],
    realizado_por_categoria: Optional[dict[str, float]] = None,
) -> None:
    """Regras do valor orçado por categoria (US-01).

    - nome de categoria não vazio e sem repetição;
    - valor orçado de cada categoria >= 0;
    - soma das categorias <= valor total (pode sobrar valor sem categoria);
    - nenhuma categoria abaixo do que já foi gasto nela (só aprovados).

    Os valores são comparados em centavos, como no alerta de saldo.
    """
    realizado_por_categoria = realizado_por_categoria or {}

    if not math.isfinite(valor_total) or valor_total < 0:
        raise OrcamentoInvalido("valor_total não pode ser negativo")

    vistos = set()
    for nome in categorias:
        if not nome.strip():
            raise OrcamentoInvalido("Nome de categoria não pode ser vazio.")
        if nome.casefold() in vistos:
            raise OrcamentoInvalido(f"Categoria repetida: {nome}.")
        vistos.add(nome.casefold())

    for nome, valor in valores_categorias.items():
        if not math.isfinite(valor) or valor < 0:
            raise OrcamentoInvalido(
                f"O valor orçado da categoria {nome} deve ser maior ou igual a zero."
            )

    soma = sum((_em_centavos(v) for v in valores_categorias.values()), Decimal(0))
    if soma > _em_centavos(valor_total):
        raise OrcamentoInvalido(
            f"A soma das categorias ({formatar_reais(float(soma))}) passa do "
            f"valor total do orçamento ({formatar_reais(valor_total)})."
        )

    for nome, valor in valores_categorias.items():
        gasto = realizado_por_categoria.get(nome, 0.0)
        if _em_centavos(valor) < _em_centavos(gasto):
            raise OrcamentoInvalido(
                f"O valor orçado da categoria {nome} ({formatar_reais(valor)}) é "
                f"menor do que já foi gasto nela ({formatar_reais(gasto)})."
            )


@dataclass
class CategoriaOrcada:
    """Resumo de uma categoria para leitura: limite e quanto já foi gasto."""

    nome: str
    valor_orcado: Optional[float]
    realizado: float


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
    # T-17 · US-04: quem lançou, para receber a notificação do resultado.
    autor_id: Optional[str] = None
    # T-18 · US-04: quando foi lançado, para a fila de aprovação mostrar
    # primeiro o que está esperando há mais tempo.
    criado_em: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
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
    # US-01: valor orçado de cada categoria. Categoria fora do dicionário
    # não tem limite (orçamentos criados só com a lista de nomes).
    valores_categorias: dict[str, float] = field(default_factory=dict)
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

    def realizado_por_categoria(self) -> dict[str, float]:
        """Soma dos lançamentos aprovados de cada categoria."""
        realizado = {nome: 0.0 for nome in self.categorias_despesa}
        for lancamento in self.lancamentos:
            if lancamento.status == StatusLancamento.APROVADO:
                realizado[lancamento.categoria] = (
                    realizado.get(lancamento.categoria, 0.0) + lancamento.valor
                )
        return realizado

    @property
    def categorias(self) -> list[CategoriaOrcada]:
        realizado = self.realizado_por_categoria()
        return [
            CategoriaOrcada(
                nome=nome,
                valor_orcado=self.valores_categorias.get(nome),
                realizado=float(_em_centavos(realizado[nome])),
            )
            for nome in self.categorias_despesa
        ]

    def redefinir(
        self,
        valor_total: Optional[float] = None,
        categorias: Optional[list[tuple[str, float]]] = None,
    ) -> None:
        """Edita o valor total e/ou as categorias com seus valores (US-01).

        ``categorias`` (pares nome, valor orçado) substitui a lista inteira,
        na ordem informada. Categoria com lançamento que não foi rejeitado
        não pode sair do orçamento.
        """
        with self._lock:
            novo_total = self.valor_total if valor_total is None else valor_total
            if categorias is None:
                novas_categorias = list(self.categorias_despesa)
                novos_valores = dict(self.valores_categorias)
            else:
                novas_categorias = [nome for nome, _ in categorias]
                novos_valores = dict(categorias)

            em_uso = {
                l.categoria
                for l in self.lancamentos
                if l.categoria and l.status != StatusLancamento.REJEITADO
            }
            removidas = sorted(em_uso - set(novas_categorias))
            if removidas:
                raise OrcamentoInvalido(
                    "Não é possível remover categoria com lançamentos: "
                    + ", ".join(removidas)
                    + "."
                )

            realizado = self.realizado_por_categoria()
            validar_categorias(novo_total, novas_categorias, novos_valores, realizado)
            gasto_total = sum(realizado.values())
            if _em_centavos(novo_total) < _em_centavos(gasto_total):
                raise OrcamentoInvalido(
                    f"O valor total ({formatar_reais(novo_total)}) é menor do que "
                    f"já foi gasto no orçamento ({formatar_reais(gasto_total)})."
                )

            self.saldo_atual += novo_total - self.valor_total
            self.valor_total = novo_total
            self.categorias_despesa = novas_categorias
            self.valores_categorias = novos_valores

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
            self.saldo_atual -= lancamento.valor
            return lancamento

    def reverter_aprovacao(self, lancamento_id: str) -> None:
        with self._lock:
            lancamento = self._buscar_lancamento(lancamento_id)
            if lancamento.status != StatusLancamento.APROVADO:
                raise AprovacaoInvalida("Lançamento não está aprovado")

            lancamento.status = StatusLancamento.PENDENTE
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
