"""create login tables (sessoes e codigos_acesso)

Revision ID: b7d4e2a9c1f0
Revises: 6bd565cae094
Create Date: 2026-11-05 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d4e2a9c1f0'
down_revision: Union[str, Sequence[str], None] = '6bd565cae094'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# T-35: login único. A coluna usuarios.senha_hash vem da 62959ecab341; aqui ficam as
# sessões e os códigos de primeiro acesso, guardados só como hash (SHA-256).
def upgrade() -> None:

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
