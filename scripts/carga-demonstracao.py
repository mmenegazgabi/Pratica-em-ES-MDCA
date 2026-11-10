"""Carga de demonstração: contas, papéis, vínculos, programas, orçamentos e lançamentos.

Para a apresentação integrada (E3): depois que o Financeiro passou a gravar no banco, o
que estava em memória no Cloud Run sumiu. Este script deixa o banco com dados para
mostrar os dois módulos funcionando juntos, e com as contas para entrar pelo login.

O que ele cria (tudo com id começando em ``demo-``, para não se misturar aos dados reais):

- contas (senha pedida no terminal, a mesma para todas):
  Luana Ferraz (Coordenação), Jane Almeida (Direção), Lucas Prado (voluntário
  financeiro) e Marcos Vieira (educador, com vínculo só no Divertidamente);
- programas Divertidamente e Adolescer (se já existir um programa com esse nome ou
  identificador, ele é usado; não cria outro);
- um orçamento de 2026 em cada programa que ainda não tem orçamento;
- no Divertidamente, lançamentos do Marcos em todos os estados: aprovados (um deles
  conciliado), pendentes e um rejeitado com motivo, com as notificações.

Pode rodar mais de uma vez: o que já existe fica como está. ``--remover`` apaga o que o
script criou (os ids ``demo-``). Os registros de auditoria ficam, porque a trilha não
aceita exclusão.

Uso (na raiz do repositório, com a DATABASE_URL no ambiente ou no Backend/.env):

    .venv/bin/python scripts/carga-demonstracao.py
    .venv/bin/python scripts/carga-demonstracao.py --remover

Os lançamentos de demonstração não têm foto de comprovante (o arquivo fica no R2).
"""

import argparse
import getpass
import os
import sys
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
sys.path.insert(0, str(BACKEND))

SENHA_MINIMA = 8
DOMINIO = "demo.mdca"

CONTAS = [
    # id, nome, e-mail, papel da plataforma (None = só pelo vínculo)
    ("demo-luana", "Luana Ferraz", f"luana.ferraz@{DOMINIO}", "coordenacao"),
    ("demo-jane", "Jane Almeida", f"jane.almeida@{DOMINIO}", "direcao"),
    ("demo-lucas", "Lucas Prado", f"lucas.prado@{DOMINIO}", "voluntario_financeiro"),
    ("demo-marcos", "Marcos Vieira", f"marcos.vieira@{DOMINIO}", None),
]

PROGRAMAS = [
    {
        "id": "demo-divertidamente",
        "nome": "Divertidamente",
        "identificador": "DIVERTIDAMENTE",
        "publico": "Crianças de 6 a 11 anos",
        "responsavel": "Luana Ferraz",
        "orcamento": (24000, {"Materiais": 8000, "Alimentação": 9000, "Transporte": 4000, "Oficinas e eventos": 3000}),
    },
    {
        "id": "demo-adolescer",
        "nome": "Adolescer",
        "identificador": "ADOLESCER",
        "publico": "Adolescentes de 12 a 17 anos",
        "responsavel": "Luana Ferraz",
        "orcamento": (18000, {"Materiais": 5000, "Alimentação": 7000, "Transporte": 6000}),
    },
]

# Lançamentos do Marcos no Divertidamente: (valor, categoria, descrição, dia, destino).
LANCAMENTOS = [
    (180.00, "Materiais", "Tintas e papel para a oficina de arte", date(2026, 3, 12), "conciliado"),
    (645.30, "Alimentação", "Lanches do mês de março", date(2026, 3, 28), "aprovado"),
    (96.00, "Transporte", "Passagens para o passeio ao museu", date(2026, 4, 9), "aprovado"),
    (64.00, "Alimentação", "Frutas para o encontro com as famílias", date(2026, 5, 6), "rejeitado"),
    (230.50, "Oficinas e eventos", "Material da festa junina", date(2026, 6, 20), "pendente"),
    (412.80, "Materiais", "Jogos pedagógicos", date(2026, 9, 2), "pendente"),
]


def _banco():
    from dotenv import load_dotenv
    import sqlalchemy as sa
    from sqlalchemy.engine import make_url

    from Shared.banco import url_sqlalchemy

    load_dotenv(BACKEND / ".env", override=False)
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("DATABASE_URL não definida (no ambiente ou em Backend/.env).")
    destino = make_url(url)
    print(f"Banco: {destino.host} / {destino.database} (usuário {destino.username})")
    return sa.create_engine(url_sqlalchemy(url), connect_args={"connect_timeout": 15})


def _confirmar(pergunta: str, sim: bool) -> None:
    if sim:
        return
    if input(f"{pergunta} Digite SIM para continuar: ").strip() != "SIM":
        raise SystemExit("Nada foi feito.")


def _pedir_senha() -> str:
    senha = os.environ.get("MDCA_SENHA_DEMO")
    if senha:
        return senha
    senha = getpass.getpass("Senha das contas de demonstração (mín. 8 caracteres): ")
    if len(senha) < SENHA_MINIMA:
        raise SystemExit(f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.")
    if getpass.getpass("Repita a senha: ") != senha:
        raise SystemExit("As senhas não conferem. Nada foi feito.")
    return senha


def _contas(conexao, senha: str, redefinir: bool) -> None:
    import sqlalchemy as sa

    from Shared.sessao import gerar_hash_senha

    hash_senha = gerar_hash_senha(senha)
    for usuario_id, nome, email, papel in CONTAS:
        outro = conexao.execute(
            sa.text("SELECT id FROM usuarios WHERE lower(email) = lower(:e) AND id <> :id"),
            {"e": email, "id": usuario_id},
        ).scalar_one_or_none()
        if outro:
            print(f"  ! {email} já é de outra conta ({outro}); {usuario_id} não foi criada.")
            continue
        conexao.execute(
            sa.text(
                "INSERT INTO usuarios (id, nome, email, senha_hash) VALUES (:id, :nome, :email, :h) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": usuario_id, "nome": nome, "email": email, "h": hash_senha},
        )
        if redefinir:
            conexao.execute(sa.text("UPDATE usuarios SET senha_hash = :h WHERE id = :id"), {"h": hash_senha, "id": usuario_id})
        if papel:
            conexao.execute(
                sa.text(
                    "INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES (:u, :p) ON CONFLICT DO NOTHING"
                ),
                {"u": usuario_id, "p": papel},
            )
        print(f"  conta {email} ({papel or 'educador pelo vínculo'})")


def _programa(conexao, dados) -> str:
    """Id do programa: o que já existe com esse identificador ou nome, ou um novo."""
    import sqlalchemy as sa

    existente = conexao.execute(
        sa.text(
            "SELECT id FROM projetos WHERE lower(identificador) = lower(:i) OR lower(nome) = lower(:n) "
            "ORDER BY (lower(identificador) = lower(:i)) DESC NULLS LAST LIMIT 1"
        ),
        {"i": dados["identificador"], "n": dados["nome"]},
    ).scalar_one_or_none()
    if existente:
        print(f"  programa {dados['nome']}: já existia ({existente})")
        return existente
    conexao.execute(
        sa.text(
            """
            INSERT INTO projetos (id, nome, identificador, publico, responsavel, vigencia_inicio, vigencia_fim)
            VALUES (:id, :nome, :identificador, :publico, :responsavel, '2026-01-01', '2026-12-31')
            """
        ),
        {k: dados[k] for k in ("id", "nome", "identificador", "publico", "responsavel")},
    )
    print(f"  programa {dados['nome']}: criado ({dados['id']})")
    return dados["id"]


def _orcamento_e_lancamentos(conexao, programa_id: str, dados, com_lancamentos: bool) -> None:
    import sqlalchemy as sa

    from Financeiro.moeda import formatar_reais
    from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
    from Financeiro.persistencia import RepositorioBanco

    if conexao.execute(sa.text("SELECT 1 FROM orcamentos WHERE projeto_id = :p LIMIT 1"), {"p": programa_id}).first():
        print(f"  orçamento de {dados['nome']}: já existia (nada mudou)")
        return
    total, categorias = dados["orcamento"]
    orcamento = Orcamento(
        id=f"demo-orcamento-{programa_id.removeprefix('demo-')}",
        projeto_id=programa_id,
        valor_total=total,
        data_inicio=date(2026, 1, 1),
        data_fim=date(2026, 12, 31),
        categorias_despesa=list(categorias),
        valores_categorias=dict(categorias),
    )
    repositorio = RepositorioBanco(conexao)
    repositorio.inserir_orcamento(orcamento)
    if com_lancamentos:
        for numero, (valor, categoria, descricao, dia, destino) in enumerate(LANCAMENTOS, start=1):
            lancamento = orcamento.registrar_lancamento(
                Lancamento(
                    id=f"demo-lancamento-{numero}",
                    valor=valor,
                    status=StatusLancamento.PENDENTE,
                    descricao=descricao,
                    categoria=categoria,
                    data_despesa=dia,
                    autor_id="demo-marcos",
                )
            )
            if destino in ("aprovado", "conciliado"):
                orcamento.aprovar_lancamento(lancamento.id)
            if destino == "conciliado":
                orcamento.conciliar_lancamento(lancamento.id, "EXT-0312-01")
            if destino == "rejeitado":
                orcamento.rejeitar_lancamento(lancamento.id, "A nota fiscal está ilegível. Envie outra foto.")
            repositorio.salvar_lancamento(orcamento, lancamento)
            repositorio.notificar_resultado(lancamento)
    print(
        f"  orçamento de {dados['nome']}: {formatar_reais(total)}, saldo {formatar_reais(orcamento.saldo)}"
        + (f", {len(LANCAMENTOS)} lançamentos" if com_lancamentos else "")
    )


def carregar(sim: bool, redefinir: bool) -> None:
    import sqlalchemy as sa

    motor = _banco()
    _confirmar("Vou incluir os dados de demonstração neste banco.", sim)
    senha = _pedir_senha()
    with motor.begin() as conexao:  # tudo numa transação: ou entra tudo, ou nada
        print("Contas:")
        _contas(conexao, senha, redefinir)
        print("Programas e orçamentos:")
        for dados in PROGRAMAS:
            programa_id = _programa(conexao, dados)
            if dados["nome"] == "Divertidamente":
                conexao.execute(
                    sa.text(
                        """
                        INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada)
                        SELECT 'demo-v-marcos', 'demo-marcos', :p, 'educador', '2026-01-05'
                        WHERE EXISTS (SELECT 1 FROM usuarios WHERE id = 'demo-marcos')
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {"p": programa_id},
                )
            _orcamento_e_lancamentos(conexao, programa_id, dados, com_lancamentos=dados["nome"] == "Divertidamente")
    print("Pronto. Entre com os e-mails acima e a senha que você definiu.")


def remover(sim: bool) -> None:
    import sqlalchemy as sa

    motor = _banco()
    _confirmar("Vou APAGAR os dados de demonstração (ids demo-) deste banco.", sim)
    with motor.begin() as conexao:
        apagados = {}
        for tabela, filtro in (
            ("lancamentos", "id LIKE 'demo-%' OR orcamento_id LIKE 'demo-%'"),
            ("orcamentos", "id LIKE 'demo-%'"),
            ("vinculos_equipe", "id LIKE 'demo-%' OR usuario_id LIKE 'demo-%'"),
            ("usuarios_papeis", "usuario_id LIKE 'demo-%'"),
            ("usuarios", "id LIKE 'demo-%'"),
        ):
            apagados[tabela] = conexao.execute(sa.text(f"DELETE FROM {tabela} WHERE {filtro}")).rowcount
        # Programas só se nada mais (da Gestão, por exemplo) estiver ligado a eles.
        for dados in PROGRAMAS:
            try:
                with conexao.begin_nested():
                    if conexao.execute(sa.text("DELETE FROM projetos WHERE id = :id"), {"id": dados["id"]}).rowcount:
                        apagados.setdefault("projetos", 0)
                        apagados["projetos"] += 1
            except sa.exc.IntegrityError:
                print(f"  programa {dados['nome']} mantido: já tem dados da Gestão ligados a ele.")
    print("Removido:", ", ".join(f"{t} {n}" for t, n in apagados.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Dados de demonstração da plataforma MDCA.")
    parser.add_argument("--remover", action="store_true", help="apaga o que o script criou (ids demo-)")
    parser.add_argument("--redefinir-senhas", action="store_true", help="troca a senha das contas de demonstração")
    parser.add_argument("--sim", action="store_true", help="não pede confirmação (para testes)")
    args = parser.parse_args()
    if args.remover:
        remover(args.sim)
    else:
        carregar(args.sim, args.redefinir_senhas)


if __name__ == "__main__":
    main()
