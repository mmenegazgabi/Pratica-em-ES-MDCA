"""create login tables (senha, sessoes e codigos_acesso)

Revision ID: b7d4e2a9c1f0
Revises: 5c2e8d41a7b3
Create Date: 2026-11-05 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d4e2a9c1f0'
down_revision: Union[str, Sequence[str], None] = '5c2e8d41a7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# T-35: login único. Só guardamos hashes: da senha (scrypt), do token de sessão e do
# código de acesso (SHA-256).
def upgrade() -> None:
    op.add_column("usuarios", sa.Column("senha_hash", sa.Text(), nullable=True))

    op.create_table(
        "sessoes",
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("usuario_id", sa.Text(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_sessoes")),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], name=op.f("fk_sessoes_usuario_id_usuarios")),
    )
    op.create_index("ix_sessoes_usuario_id", "sessoes", ["usuario_id"])

    op.create_table(
        "codigos_acesso",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("usuario_id", sa.Text(), nullable=False),
        sa.Column("codigo_hash", sa.Text(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_por", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_codigos_acesso")),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], name=op.f("fk_codigos_acesso_usuario_id_usuarios")),
    )
    op.create_index("ix_codigos_acesso_usuario_id", "codigos_acesso", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_codigos_acesso_usuario_id", table_name="codigos_acesso")
    op.drop_table("codigos_acesso")
    op.drop_index("ix_sessoes_usuario_id", table_name="sessoes")
    op.drop_table("sessoes")
    op.drop_column("usuarios", "senha_hash")
