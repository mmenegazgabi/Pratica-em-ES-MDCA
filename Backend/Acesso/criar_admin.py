"""Cria a primeira administradora e emite o código de primeiro acesso (T-35).

Uso (com ``DATABASE_URL`` configurada)::

    python -m Acesso.criar_admin --nome "Maria Silva" --email maria@mdca.org.br

Se já existir uma pessoa com o e-mail, ela é reaproveitada.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Optional, Tuple

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from Acesso import auditoria, codigos, usuarios

PAPEL_ADMIN = "administracao"


def criar_admin(conexao: Connection, nome: str, email: str, agora: datetime) -> Tuple[str, str, datetime]:
    """Garante a pessoa com o papel de administração e devolve (usuario_id, código, validade)."""
    if not nome.strip():
        raise ValueError("O nome não pode ficar em branco.")
    email = usuarios.normalizar_email(email)
    existente = usuarios.por_email(conexao, email)
    if existente is not None:
        usuario_id = existente.id
        if not existente.ativo:
            conexao.execute(sa.text("UPDATE usuarios SET ativo = true WHERE id = :id"), {"id": usuario_id})
    else:
        usuario_id = usuarios.novo_id(conexao, nome)
        conexao.execute(
            sa.text("INSERT INTO usuarios (id, nome, email) VALUES (:id, :nome, :email)"),
            {"id": usuario_id, "nome": nome.strip(), "email": email},
        )
    conexao.execute(
        sa.text(
            "INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES (:u, :p) "
            "ON CONFLICT DO NOTHING"
        ),
        {"u": usuario_id, "p": PAPEL_ADMIN},
    )
    codigo, validade = codigos.emitir(conexao, usuario_id, None, agora)
    auditoria.registrar(
        conexao,
        usuario_id=None,
        acao="codigo_emitido",
        alvo_tipo="usuario",
        alvo_id=usuario_id,
        descricao="Código de primeiro acesso emitido pelo comando criar_admin",
    )
    conexao.commit()
    return usuario_id, codigo, validade


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Cria a primeira administradora.")
    parser.add_argument("--nome", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    if not args.nome.strip():
        parser.error("--nome não pode ficar em branco.")

    url = os.getenv("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL não configurada.", file=sys.stderr)
        return 1
    from Gestao.banco import url_sqlalchemy

    motor = sa.create_engine(url_sqlalchemy(url))
    with motor.connect() as conexao:
        _, codigo, validade = criar_admin(conexao, args.nome, args.email, datetime.now(timezone.utc))
    print(f"Código de primeiro acesso: {codigo} (vale até {validade.astimezone().strftime('%d/%m/%Y %H:%M')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
