"""Define a senha de login (T-35) de um usuário já cadastrado, pelo e-mail.

O caminho normal é a tela de administração (cadastro + código de primeiro acesso,
ver docs/login.md). Este script fica para o time técnico dar senha direto a uma conta
(por exemplo, as da demonstração). A senha é pedida no terminal, sem aparecer na tela
nem no histórico, e só o hash vai para o banco; as sessões abertas da pessoa terminam.

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


def main():
    parser = argparse.ArgumentParser(description="Define a senha de login de um usuário.")
    parser.add_argument("email", help="e-mail do usuário, como está em usuarios.email")
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(BACKEND / ".env", override=False)
    if not os.getenv("DATABASE_URL"):
        sys.exit("DATABASE_URL não definida (ambiente ou Backend/.env).")

    import sqlalchemy as sa
    from Acesso import senhas, sessoes
    from Gestao.banco import url_sqlalchemy

    senha = getpass.getpass("Nova senha: ")
    erro = senhas.validar(senha)
    if erro:
        sys.exit(erro)
    if getpass.getpass("Repita a senha: ") != senha:
        sys.exit("As senhas não conferem.")

    with sa.create_engine(url_sqlalchemy(os.environ["DATABASE_URL"])).connect() as conexao:
        usuario_id = conexao.execute(
            sa.text("UPDATE usuarios SET senha_hash = :hash WHERE lower(email) = lower(:email) RETURNING id"),
            {"hash": senhas.gerar_hash(senha), "email": args.email.strip()},
        ).scalar_one_or_none()
        if usuario_id is None:
            sys.exit(f"Nenhum usuário com o e-mail {args.email!r}.")
        sessoes.encerrar_todas(conexao, usuario_id)
        conexao.commit()
    print(f"Senha definida para {args.email}.")


if __name__ == "__main__":
    main()
