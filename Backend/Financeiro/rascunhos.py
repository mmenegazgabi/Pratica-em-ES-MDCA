"""Rascunhos de despesa: o educador fotografa o comprovante agora e completa os dados depois.

Armazenamento em memória, como o restante do Financeiro por enquanto. Rascunho
não é lançamento: não aparece na fila de aprovação nem mexe no saldo.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


class RascunhoNaoEncontrado(ValueError):
    pass


@dataclass
class Rascunho:
    autor_id: str
    comprovante_chave: str
    nome_original: str
    content_type: str
    tamanho: int
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    criado_em: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CaixaDeRascunhos:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rascunhos: list[Rascunho] = []

    def criar(self, rascunho: Rascunho) -> Rascunho:
        with self._lock:
            self._rascunhos.append(rascunho)
        return rascunho

    def do_autor(self, autor_id: str) -> list[Rascunho]:
        """Rascunhos do autor, do mais recente para o mais antigo."""
        with self._lock:
            meus = [r for r in self._rascunhos if r.autor_id == autor_id]
        return list(reversed(meus))

    def retirar(self, rascunho_id: str, autor_id: str) -> Rascunho:
        # Rascunho de outro autor responde como inexistente.
        with self._lock:
            for rascunho in self._rascunhos:
                if rascunho.id == rascunho_id and rascunho.autor_id == autor_id:
                    self._rascunhos.remove(rascunho)
                    return rascunho
        raise RascunhoNaoEncontrado("Rascunho não encontrado")

    def limpar(self) -> None:
        with self._lock:
            self._rascunhos.clear()


caixa_de_rascunhos = CaixaDeRascunhos()
