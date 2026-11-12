"""Cadastro de projetos do Financeiro.

Com ``DATABASE_URL`` os projetos são as linhas da tabela ``projetos``: o mesmo cadastro
canônico de programas da Gestão (ARQ-02). Um programa cadastrado na Gestão já aparece
aqui, e orçamentos e lançamentos apontam para ele pelo ``id``, o que faz a Visão
integrada da Gestão casar pelo id. Sem banco (testes, execução local), a lista em
memória ``_projetos`` faz esse papel.

As regras (nome obrigatório, sem repetir nome) ficam aqui; onde guardar fica com o
repositório (``persistencia.py``). Sem ``repositorio``, as funções usam a memória.
"""

import threading
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class ProjetoInvalido(ValueError):
    pass


class ProjetoDuplicado(ProjetoInvalido):
    pass


class StatusProjeto(str, Enum):
    ATIVO = "ativo"
    ENCERRADO = "encerrado"


@dataclass
class Projeto:
    nome: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # T-29 · US-07: filtro do dashboard da Diretoria.
    status: StatusProjeto = StatusProjeto.ATIVO
    criado_em: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Cadastro em memória, usado sem banco. RLock: o repositório em memória reentra nele.
_projetos: List[Projeto] = []
_trava = threading.RLock()


def _chave(nome: str) -> str:
    decomposto = unicodedata.normalize("NFKD", nome.strip().casefold())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def ordenar(projetos: List[Projeto]) -> List[Projeto]:
    return sorted(projetos, key=lambda p: (_chave(p.nome), p.id))


def _repositorio(repositorio):
    if repositorio is not None:
        return repositorio
    # Importado aqui: persistencia.py importa este módulo.
    if __package__:
        from .persistencia import MEMORIA
    else:
        from persistencia import MEMORIA
    return MEMORIA


def buscar_projeto(projeto_id: str, repositorio=None) -> Optional[Projeto]:
    return _repositorio(repositorio).buscar_projeto(projeto_id)


def listar_projetos(repositorio=None) -> List[Projeto]:
    return _repositorio(repositorio).listar_projetos()


def registrar_projeto(nome: str, repositorio=None) -> Projeto:
    repositorio = _repositorio(repositorio)
    nome = nome.strip()
    if not 1 <= len(nome) <= 120:
        raise ProjetoInvalido("Informe o nome do projeto.")
    # A trava impede que duas requisições cadastrem o mesmo nome ao mesmo tempo.
    with repositorio.cadastro_de_projetos():
        if any(_chave(p.nome) == _chave(nome) for p in repositorio.listar_projetos()):
            raise ProjetoDuplicado("Já existe um projeto com esse nome.")
        projeto = Projeto(nome=nome)
        repositorio.inserir_projeto(projeto)
    return projeto


def alterar_status(
    projeto_id: str, status: StatusProjeto, repositorio=None
) -> Optional[Projeto]:
    """Encerra ou reabre o projeto; ``None`` se ele não existir."""
    repositorio = _repositorio(repositorio)
    with repositorio.cadastro_de_projetos():
        projeto = repositorio.buscar_projeto(projeto_id)
        if projeto is not None:
            projeto.status = status
            repositorio.salvar_status_projeto(projeto)
        return projeto
