"""Cadastro de projetos do Financeiro (em memória, como o restante por enquanto).

Combinar com o time de Gestão: quando existir o cadastro compartilhado,
``buscar_projeto`` passa a consultá-lo e a regra do POST /orcamentos continua igual.
"""

import threading
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


class ProjetoInvalido(ValueError):
    pass


class ProjetoDuplicado(ProjetoInvalido):
    pass


@dataclass
class Projeto:
    nome: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    criado_em: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


_projetos: List[Projeto] = []
_trava = threading.Lock()


def _chave(nome: str) -> str:
    decomposto = unicodedata.normalize("NFKD", nome.strip().casefold())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def buscar_projeto(projeto_id: str) -> Optional[Projeto]:
    with _trava:
        return next((p for p in _projetos if p.id == projeto_id), None)


def listar_projetos() -> List[Projeto]:
    with _trava:
        return sorted(_projetos, key=lambda p: _chave(p.nome))


def registrar_projeto(nome: str) -> Projeto:
    nome = nome.strip()
    if not 1 <= len(nome) <= 120:
        raise ProjetoInvalido("Informe o nome do projeto.")
    with _trava:
        if any(_chave(p.nome) == _chave(nome) for p in _projetos):
            raise ProjetoDuplicado("Já existe um projeto com esse nome.")
        projeto = Projeto(nome=nome)
        _projetos.append(projeto)
    return projeto
