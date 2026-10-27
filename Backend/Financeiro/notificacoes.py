"""Notificações in-app ao autor do lançamento (T-17 · US-04).

Quando a coordenação/direção aprova ou rejeita um lançamento, quem lançou
recebe uma notificação no sistema. Na rejeição, a notificação leva o motivo.

Só existe o canal in-app. E-mail/WhatsApp ficam para uma integração externa
futura: o ponto de extensão é ``CaixaDeNotificacoes.notificar_resultado``,
que é o único lugar onde uma notificação nasce.

Lançamento sem autor (criado antes da T-17 ou sem ``X-Usuario-Id``) não gera
notificação: não há para quem enviar.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

if __package__:
    from .orcamento import Lancamento, StatusLancamento, formatar_reais
else:
    from orcamento import Lancamento, StatusLancamento, formatar_reais


class TipoNotificacao(str, Enum):
    LANCAMENTO_APROVADO = "lancamento_aprovado"
    LANCAMENTO_REJEITADO = "lancamento_rejeitado"


class NotificacaoNaoEncontrada(ValueError):
    pass


@dataclass
class Notificacao:
    destinatario_id: str
    lancamento_id: str
    tipo: TipoNotificacao
    mensagem: str
    motivo: Optional[str] = None
    lida: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    criada_em: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def montar_mensagem(lancamento: Lancamento) -> str:
    descricao = f'"{lancamento.descricao}"' if lancamento.descricao else ""
    alvo = " ".join(p for p in ["Seu lançamento", descricao] if p)
    valor = formatar_reais(lancamento.valor)
    if lancamento.status == StatusLancamento.APROVADO:
        return f"{alvo} de {valor} foi aprovado."
    return f"{alvo} de {valor} foi rejeitado. Motivo: {lancamento.motivo_rejeicao}"


TIPO_POR_STATUS = {
    StatusLancamento.APROVADO: TipoNotificacao.LANCAMENTO_APROVADO,
    StatusLancamento.REJEITADO: TipoNotificacao.LANCAMENTO_REJEITADO,
}


class CaixaDeNotificacoes:
    """Armazenamento em memória, como o restante do Financeiro por enquanto."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._notificacoes: list[Notificacao] = []

    def notificar_resultado(self, lancamento: Lancamento) -> Optional[Notificacao]:
        """Avisa o autor que o lançamento foi aprovado ou rejeitado."""
        tipo = TIPO_POR_STATUS.get(lancamento.status)
        if tipo is None or not lancamento.autor_id:
            return None
        notificacao = Notificacao(
            destinatario_id=lancamento.autor_id,
            lancamento_id=lancamento.id,
            tipo=tipo,
            mensagem=montar_mensagem(lancamento),
            motivo=lancamento.motivo_rejeicao
            if tipo == TipoNotificacao.LANCAMENTO_REJEITADO
            else None,
        )
        with self._lock:
            self._notificacoes.append(notificacao)
        return notificacao

    def listar(self, destinatario_id: str, apenas_nao_lidas: bool = False) -> list[Notificacao]:
        """Notificações do usuário, das mais recentes para as mais antigas."""
        with self._lock:
            minhas = [
                n
                for n in self._notificacoes
                if n.destinatario_id == destinatario_id
                and not (apenas_nao_lidas and n.lida)
            ]
        return list(reversed(minhas))

    def marcar_como_lida(self, notificacao_id: str, destinatario_id: str) -> Notificacao:
        # Notificação de outro usuário responde como inexistente, para não
        # revelar que ela existe.
        with self._lock:
            for notificacao in self._notificacoes:
                if notificacao.id == notificacao_id and notificacao.destinatario_id == destinatario_id:
                    notificacao.lida = True
                    return notificacao
        raise NotificacaoNaoEncontrada("Notificação não encontrada")

    def limpar(self) -> None:
        with self._lock:
            self._notificacoes.clear()


caixa_de_notificacoes = CaixaDeNotificacoes()
