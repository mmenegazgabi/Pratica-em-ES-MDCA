"""Cria a primeira administradora e emite o código de primeiro acesso (T-35).

Uso (com ``DATABASE_URL`` configurada)::

    python -m Acesso.criar_admin --nome "Maria Silva" --email maria@mdca.org.br

Se já existir uma pessoa com o e-mail, ela é reaproveitada. Para promover alguém que
já está em ``usuarios`` (por exemplo, cadastrado antes do login e ainda sem e-mail),
use ``--id`` no lugar de ``--nome``; o e-mail informado passa a ser o dela::

    python -m Acesso.criar_admin --id maria-silva --email maria@mdca.org.br
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


def _promover(conexao: Connection, usuario_id: str, email: str) -> None:
    """Grava o e-mail na pessoa já cadastrada e a reativa, se preciso."""
    alvo = conexao.execute(
        sa.text("SELECT id FROM usuarios WHERE id = :id"), {"id": usuario_id}
    ).first()
    if alvo is None:
        raise ValueError(f"Não existe pessoa com o id {usuario_id!r}.")
    outra = usuarios.por_email(conexao, email)
    if outra is not None and outra.id != usuario_id:
        raise ValueError(f"O e-mail {email} já é de outra pessoa ({outra.id}).")
    conexao.execute(
        sa.text("UPDATE usuarios SET email = :e, ativo = true WHERE id = :id"),
        {"e": email, "id": usuario_id},
    )


def criar_admin(
    conexao: Connection,
    nome: str,
    email: str,
    agora: datetime,
    usuario_id: Optional[str] = None,
) -> Tuple[str, str, datetime]:
    """Garante a pessoa com o papel de administração e devolve (usuario_id, código, validade).

    Com ``usuario_id``, promove essa pessoa (o nome é ignorado); sem ele, procura pelo
    e-mail ou cria uma nova.
    """
    email = usuarios.normalizar_email(email)
    if "@" not in email:
        raise ValueError("Informe um e-mail válido.")
    if usuario_id is not None:
        _promover(conexao, usuario_id, email)
    elif not nome.strip():
        raise ValueError("O nome não pode ficar em branco.")
    elif (existente := usuarios.por_email(conexao, email)) is not None:
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
    quem = parser.add_mutually_exclusive_group(required=True)
    quem.add_argument("--nome", help="Nome da nova pessoa (ou da que já tem este e-mail).")
    quem.add_argument("--id", help="Id de uma pessoa já cadastrada em usuarios, para promovê-la.")
    parser.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    if args.nome is not None and not args.nome.strip():
        parser.error("--nome não pode ficar em branco.")

    url = os.getenv("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL não configurada.", file=sys.stderr)
        return 1
    from Gestao.banco import url_sqlalchemy

    motor = sa.create_engine(url_sqlalchemy(url))
    with motor.connect() as conexao:
        try:
            _, codigo, validade = criar_admin(
                conexao, args.nome or "", args.email, datetime.now(timezone.utc), usuario_id=args.id
            )
        except ValueError as erro:
            print(erro, file=sys.stderr)
            return 1
    print(f"Código de primeiro acesso: {codigo} (vale até {validade.astimezone().strftime('%d/%m/%Y %H:%M')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
