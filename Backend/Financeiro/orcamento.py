import math
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

if __package__:
    from .alerta_saldo import _em_centavos
    from .moeda import formatar_reais
else:
    from alerta_saldo import _em_centavos
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


class OrcamentoInvalido(ValueError):
    """Valor total e valores das categorias não fecham (US-01)."""


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
        valor_total: Optional[float] = None,
        data_inicio: Optional[date] = None,
        data_fim: Optional[date] = None,
        categorias_despesa: Optional[list[str]] = None,
        categorias: Optional[list[tuple[str, float]]] = None,
    ) -> None:
        """Edição parcial do orçamento: o que vier como ``None`` fica como está.

        Redesign Financeiro: a coordenação ajusta valor, vigência e
        categorias; o saldo é recalculado sobre o que já foi aprovado.

        US-01: ``categorias`` (pares nome, valor orçado) substitui a lista
        inteira com os limites. ``categorias_despesa`` (só nomes, o que o
        formulário do redesign envia) também substitui a lista, mas mantém o
        valor orçado das categorias que continuam.
        """
        if categorias is not None and categorias_despesa is not None:
            raise OrcamentoInvalido(
                "Informe categorias ou categorias_despesa (só um dos dois)."
            )
        with self._lock:
            novo_total = self.valor_total if valor_total is None else valor_total
            novo_inicio = self.data_inicio if data_inicio is None else data_inicio
            novo_fim = self.data_fim if data_fim is None else data_fim
            if categorias is not None:
                novas_categorias = [nome for nome, _ in categorias]
                novos_valores = dict(categorias)
            elif categorias_despesa is not None:
                novas_categorias = list(categorias_despesa)
                novos_valores = {
                    nome: valor
                    for nome, valor in self.valores_categorias.items()
                    if nome in novas_categorias
                }
            else:
                novas_categorias = list(self.categorias_despesa)
                novos_valores = dict(self.valores_categorias)

            if not novas_categorias:
                raise OrcamentoInvalido("Informe ao menos uma categoria.")
            if novo_fim < novo_inicio:
                raise OrcamentoInvalido("data_fim não pode ser anterior a data_inicio")

            # Em centavos (Decimal) para não acumular erro de ponto flutuante.
            realizado = sum(
                (
                    _em_centavos(l.valor)
                    for l in self.lancamentos
                    if l.status == StatusLancamento.APROVADO
                ),
                Decimal("0"),
            )
            if _em_centavos(novo_total) < realizado:
                raise OrcamentoInvalido(
                    "O valor total não pode ser menor que o já gasto "
                    f"({formatar_reais(float(realizado))})."
                )
            for categoria in self.categorias_despesa:
                if categoria in novas_categorias:
                    continue
                if any(
                    l.categoria == categoria
                    and l.status != StatusLancamento.REJEITADO
                    for l in self.lancamentos
                ):
                    raise OrcamentoInvalido(
                        f'A categoria "{categoria}" tem lançamentos e não pode ser removida.'
                    )
            validar_categorias(
                novo_total, novas_categorias, novos_valores, self.realizado_por_categoria()
            )

            self.valor_total = novo_total
            self.data_inicio = novo_inicio
            self.data_fim = novo_fim
            self.categorias_despesa = novas_categorias
            self.valores_categorias = novos_valores
            self.saldo_atual = float(_em_centavos(novo_total) - realizado)

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
