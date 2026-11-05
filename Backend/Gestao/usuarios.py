"""Usuários e papéis da plataforma vistos por Gestão (US-01, tela "Usuários e acessos").

Só leitura: o cadastro e a edição de contas ainda não têm card. A lista alimenta a tela
da administração e a escolha de quem vincular à equipe de um programa (T-40).

Os vínculos listados são os ativos, com a mesma regra de ``equipe.py``: sem data de
saída ou com a saída ainda no futuro.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class Papel:
    id: str
    nome: str


@dataclass(frozen=True)
class VinculoAtivo:
    programa_id: str
    programa: str
    papel_id: str
    papel: str


@dataclass(frozen=True)
class Usuario:
    id: str
    nome: str
    email: Optional[str]
    ativo: bool
    papeis: List[Papel] = field(default_factory=list)
    vinculos: List[VinculoAtivo] = field(default_factory=list)


def listar_papeis(conexao: Connection) -> List[Papel]:
    linhas = conexao.execute(sa.text("SELECT id, nome FROM papeis ORDER BY lower(nome), id"))
    return [Papel(**linha._mapping) for linha in linhas]


def listar_usuarios(conexao: Connection, *, hoje: Optional[date] = None) -> List[Usuario]:
    """Todos os usuários (ativos e desativados), com papéis da plataforma e vínculos ativos."""
    papeis: Dict[str, List[Papel]] = {}
    for linha in conexao.execute(
        sa.text(
            """
            SELECT up.usuario_id, p.id, p.nome
            FROM usuarios_papeis up JOIN papeis p ON p.id = up.papel_id
            ORDER BY lower(p.nome), p.id
            """
        )
    ):
        papeis.setdefault(linha.usuario_id, []).append(Papel(id=linha.id, nome=linha.nome))

    vinculos: Dict[str, List[VinculoAtivo]] = {}
    for linha in conexao.execute(
        sa.text(
            """
            SELECT v.usuario_id, v.programa_id, pr.nome AS programa, v.papel_id, p.nome AS papel
            FROM vinculos_equipe v
            JOIN projetos pr ON pr.id = v.programa_id
            JOIN papeis p ON p.id = v.papel_id
            WHERE v.data_saida IS NULL OR v.data_saida > :hoje
            ORDER BY lower(pr.nome), pr.id, lower(p.nome)
            """
        ),
        {"hoje": hoje or date.today()},
    ):
        vinculos.setdefault(linha.usuario_id, []).append(
            VinculoAtivo(
                programa_id=linha.programa_id,
                programa=linha.programa,
                papel_id=linha.papel_id,
                papel=linha.papel,
            )
        )

    linhas = conexao.execute(
        sa.text("SELECT id, nome, email, ativo FROM usuarios ORDER BY lower(nome), id")
    )
    return [
        Usuario(
            id=linha.id,
            nome=linha.nome,
            email=linha.email,
            ativo=linha.ativo,
            papeis=papeis.get(linha.id, []),
            vinculos=vinculos.get(linha.id, []),
        )
        for linha in linhas
    ]
