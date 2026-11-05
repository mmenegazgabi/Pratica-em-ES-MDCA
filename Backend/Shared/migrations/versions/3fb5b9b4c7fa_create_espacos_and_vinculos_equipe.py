"""create espacos and vinculos_equipe

Revision ID: 3fb5b9b4c7fa
Revises: 9409373416eb
Create Date: 2026-11-04 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3fb5b9b4c7fa'
down_revision: Union[str, Sequence[str], None] = '9409373416eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # T-38 · US-01: rooms and places each program uses (turmas point here in T-51).
    op.create_table(
        "espacos",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "programa_id",
            sa.String(),
            sa.ForeignKey("projetos.id", name="fk_espacos_programa_id_projetos"),
            nullable=False,
        ),
        sa.Column("nome", sa.Text(), nullable=False),
        # Nullable: not every space has a fixed number of places.
        sa.Column("capacidade", sa.Integer(), nullable=True),
        sa.CheckConstraint("length(btrim(nome)) > 0", name="ck_espacos_nome_preenchido"),
        sa.CheckConstraint(
            "capacidade IS NULL OR capacidade > 0", name="ck_espacos_capacidade_positiva"
        ),
    )
    op.create_index(
        "ux_espacos_programa_id_nome",
        "espacos",
        ["programa_id", sa.text("lower(nome)")],
        unique=True,
    )

    # T-38 · US-01: who works in each program and with which role. Leaving a program
    # sets data_saida; the row stays so the history linked to it is kept.
    op.create_table(
        "vinculos_equipe",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "usuario_id",
            sa.String(),
            sa.ForeignKey("usuarios.id", name="fk_vinculos_equipe_usuario_id_usuarios"),
            nullable=False,
        ),
        sa.Column(
            "programa_id",
            sa.String(),
            sa.ForeignKey("projetos.id", name="fk_vinculos_equipe_programa_id_projetos"),
            nullable=False,
        ),
        # Same role list as the rest of the platform (T-32); no table of its own.
        sa.Column(
            "papel_id",
            sa.String(),
            sa.ForeignKey("papeis.id", name="fk_vinculos_equipe_papel_id_papeis"),
            nullable=False,
        ),
        sa.Column("data_entrada", sa.Date(), nullable=False),
        sa.Column("data_saida", sa.Date(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "data_saida IS NULL OR data_saida >= data_entrada",
            name="ck_vinculos_equipe_saida_depois_da_entrada",
        ),
    )
    # One open link per person, program and role; closed ones may repeat (leaves and returns).
    op.create_index(
        "ux_vinculos_equipe_ativo",
        "vinculos_equipe",
        ["usuario_id", "programa_id", "papel_id"],
        unique=True,
        postgresql_where=sa.text("data_saida IS NULL"),
    )
    op.create_index("ix_vinculos_equipe_programa_id", "vinculos_equipe", ["programa_id"])
    op.create_index("ix_vinculos_equipe_usuario_id", "vinculos_equipe", ["usuario_id"])


def downgrade() -> None:
    """Downgrade schema."""
    # Dropping a table also drops its indexes and constraints.
    op.drop_table("vinculos_equipe")
    op.drop_table("espacos")
