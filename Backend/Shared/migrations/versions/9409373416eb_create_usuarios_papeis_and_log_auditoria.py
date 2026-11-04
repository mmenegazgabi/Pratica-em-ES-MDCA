"""create usuarios, papeis, usuarios_papeis and log_auditoria

Revision ID: 9409373416eb
Revises: a3c5e7f9b1d2
Create Date: 2026-11-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9409373416eb'
down_revision: Union[str, Sequence[str], None] = 'a3c5e7f9b1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# T-32 · US-08: one role list for both modules. The first four ids are the ones
# the Financeiro API already accepts in X-Papel-Usuario (Financeiro/autenticacao.py).
PAPEIS = [
    {"id": "coordenacao", "nome": "Coordenação"},
    {"id": "direcao", "nome": "Direção"},
    {"id": "educador", "nome": "Educador(a) social"},
    {"id": "voluntario_financeiro", "nome": "Voluntário(a) financeiro"},
    {"id": "assistente_social", "nome": "Assistente social"},
    {"id": "psicologo", "nome": "Psicólogo(a)"},
    {"id": "administracao", "nome": "Administração do sistema"},
]


def upgrade() -> None:
    """Upgrade schema."""
    # Minimal account record shared by both modules; login data (T-35) comes later.
    # Text ids match lancamentos.autor_id and the X-Usuario-Id header already in use.
    op.create_table(
        "usuarios",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        # Accounts are deactivated, never deleted, so history keeps pointing at them.
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("length(btrim(nome)) > 0", name="ck_usuarios_nome_preenchido"),
    )
    op.create_index(
        "ux_usuarios_email", "usuarios", [sa.text("lower(email)")], unique=True
    )

    papeis = op.create_table(
        "papeis",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("nome", sa.String(), nullable=False, unique=True),
    )
    op.bulk_insert(papeis, PAPEIS)

    # Platform-wide roles. Roles inside a program live on the Gestão team links (T-38),
    # which reference the same papeis table.
    op.create_table(
        "usuarios_papeis",
        sa.Column(
            "usuario_id",
            sa.String(),
            sa.ForeignKey("usuarios.id", name="fk_usuarios_papeis_usuario_id_usuarios"),
            primary_key=True,
        ),
        sa.Column(
            "papel_id",
            sa.String(),
            sa.ForeignKey("papeis.id", name="fk_usuarios_papeis_papel_id_papeis"),
            primary_key=True,
        ),
        sa.Column(
            "atribuido_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_usuarios_papeis_papel_id", "usuarios_papeis", ["papel_id"])

    # Single audit trail for the whole platform. usuario_id has no FK so denied
    # attempts by unknown callers and Financeiro's free-text authors are still logged.
    op.create_table(
        "log_auditoria",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "ocorrido_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("usuario_id", sa.String(), nullable=True),
        sa.Column("modulo", sa.String(), nullable=False),
        sa.Column("acao", sa.String(), nullable=False),
        sa.Column("alvo_tipo", sa.String(), nullable=True),
        sa.Column("alvo_id", sa.String(), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("detalhes", postgresql.JSONB(), nullable=True),
        sa.CheckConstraint(
            "modulo IN ('gestao', 'financeiro', 'plataforma')",
            name="ck_log_auditoria_modulo",
        ),
        sa.CheckConstraint("length(btrim(acao)) > 0", name="ck_log_auditoria_acao_preenchida"),
    )
    # Filters required by US-13: by user, by period and by action type.
    op.create_index("ix_log_auditoria_ocorrido_em", "log_auditoria", ["ocorrido_em"])
    op.create_index(
        "ix_log_auditoria_usuario_id_ocorrido_em", "log_auditoria", ["usuario_id", "ocorrido_em"]
    )
    op.create_index(
        "ix_log_auditoria_acao_ocorrido_em", "log_auditoria", ["acao", "ocorrido_em"]
    )
    # Append-only: entries can be inserted but never changed or removed.
    op.execute(
        """
        CREATE FUNCTION log_auditoria_somente_inclusao() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'log_auditoria aceita apenas inclusões';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER tg_log_auditoria_somente_inclusao
        BEFORE UPDATE OR DELETE ON log_auditoria
        FOR EACH ROW EXECUTE FUNCTION log_auditoria_somente_inclusao()
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Dropping a table also drops its indexes, constraints and triggers.
    op.drop_table("log_auditoria")
    op.execute("DROP FUNCTION log_auditoria_somente_inclusao()")
    op.drop_table("usuarios_papeis")
    op.drop_table("papeis")
    op.drop_table("usuarios")
