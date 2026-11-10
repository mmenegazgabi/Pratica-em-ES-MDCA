"""Consultas e gravações da administração de pessoas e papéis (T-35)."""

from typing import Iterable, List, Optional

import sqlalchemy as sa
from sqlalchemy.engine import Connection

SITUACAO_ATIVO = "ativo"
SITUACAO_AGUARDANDO = "aguardando_primeiro_acesso"
SITUACAO_DESATIVADO = "desativado"


def situacao(ativo: bool, senha_hash: Optional[str]) -> str:
    if not ativo:
        return SITUACAO_DESATIVADO
    return SITUACAO_ATIVO if senha_hash else SITUACAO_AGUARDANDO


def _papeis_por_usuario(conexao: Connection) -> dict:
    por_usuario: dict = {}
    for linha in conexao.execute(
        sa.text(
            "SELECT up.usuario_id, p.id, p.nome FROM usuarios_papeis up "
            "JOIN papeis p ON p.id = up.papel_id ORDER BY p.nome"
        )
    ):
        por_usuario.setdefault(linha.usuario_id, []).append({"id": linha.id, "nome": linha.nome})
    return por_usuario


def listar(conexao: Connection) -> List[dict]:
    papeis = _papeis_por_usuario(conexao)
    linhas = conexao.execute(
        sa.text("SELECT id, nome, email, ativo, senha_hash FROM usuarios ORDER BY nome, id")
    ).all()
    return [
        {
            "id": u.id,
            "nome": u.nome,
            "email": u.email,
            "ativo": u.ativo,
            "papeis": papeis.get(u.id, []),
            "situacao": situacao(u.ativo, u.senha_hash),
        }
        for u in linhas
    ]


def obter(conexao: Connection, usuario_id: str) -> Optional[dict]:
    u = conexao.execute(
        sa.text("SELECT id, nome, email, ativo, senha_hash FROM usuarios WHERE id = :id"),
        {"id": usuario_id},
    ).first()
    if u is None:
        return None
    papeis = conexao.execute(
        sa.text(
            "SELECT p.id, p.nome FROM usuarios_papeis up JOIN papeis p ON p.id = up.papel_id "
            "WHERE up.usuario_id = :id ORDER BY p.nome"
        ),
        {"id": usuario_id},
    ).all()
    return {
        "id": u.id,
        "nome": u.nome,
        "email": u.email,
        "ativo": u.ativo,
        "papeis": [{"id": p.id, "nome": p.nome} for p in papeis],
        "situacao": situacao(u.ativo, u.senha_hash),
    }


def papeis_desconhecidos(conexao: Connection, papeis: Iterable[str]) -> List[str]:
    existentes = set(conexao.execute(sa.text("SELECT id FROM papeis")).scalars())
    return sorted(set(papeis) - existentes)


def definir_papeis(conexao: Connection, usuario_id: str, papeis: Iterable[str]) -> None:
    conexao.execute(
        sa.text("DELETE FROM usuarios_papeis WHERE usuario_id = :u"), {"u": usuario_id}
    )
    for papel in sorted(set(papeis)):
        conexao.execute(
            sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES (:u, :p)"),
            {"u": usuario_id, "p": papel},
        )
