"""Define a senha de login (T-35) de um usuário já cadastrado, pelo e-mail.

Ainda não há cadastro de contas pela API: um administrador usa este script para dar
senha às contas (inclusive as da demonstração). A senha é pedida no terminal, sem
aparecer na tela nem no histórico, e só o hash vai para o banco.

Uso (na raiz do repositório):
    .venv/bin/python scripts/definir-senha.py ana@mdca.org.br

O banco é o da ``DATABASE_URL`` do ambiente ou, sem ela, o do ``Backend/.env``.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
sys.path.insert(0, str(BACKEND))

TAMANHO_MINIMO = 8


def main():
    parser = argparse.ArgumentParser(description="Define a senha de login de um usuário.")
    parser.add_argument("email", help="e-mail do usuário, como está em usuarios.email")
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(BACKEND / ".env", override=False)
    if not os.getenv("DATABASE_URL"):
        sys.exit("DATABASE_URL não definida (ambiente ou Backend/.env).")

    import sqlalchemy as sa
    from Shared import sessao

    senha = getpass.getpass("Nova senha: ")
    if len(senha) < TAMANHO_MINIMO:
        sys.exit(f"A senha precisa ter pelo menos {TAMANHO_MINIMO} caracteres.")
    if getpass.getpass("Repita a senha: ") != senha:
        sys.exit("As senhas não conferem.")

    with sessao.conectar() as conexao:
        alterados = conexao.execute(
            sa.text("UPDATE usuarios SET senha_hash = :hash WHERE lower(email) = lower(:email)"),
            {"hash": sessao.gerar_hash_senha(senha), "email": args.email.strip()},
        ).rowcount
        if alterados != 1:
            sys.exit(f"Nenhum usuário com o e-mail {args.email!r}.")
        conexao.commit()
    print(f"Senha definida para {args.email}.")


if __name__ == "__main__":
    main()
