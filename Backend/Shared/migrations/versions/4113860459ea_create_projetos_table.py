"""create projetos table

Revision ID: 4113860459ea
Revises: 
Create Date: 2026-10-27 17:47:49.639989

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4113860459ea'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Minimal placeholder for the canonical Programa/Projeto registry shared
    # with the Gestao module. The full schema (and which team owns this
    # migration) must be agreed with the Gestao team before extending it.
    op.create_table(
        "projetos",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("nome", sa.String(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("projetos")
