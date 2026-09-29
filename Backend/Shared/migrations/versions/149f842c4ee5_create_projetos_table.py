"""create projetos table

Revision ID: 149f842c4ee5
Revises: 
Create Date: 2026-09-29 19:15:31.046777

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '149f842c4ee5'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Placeholder mínimo do cadastro canônico de Programa/Projeto.
    # Schema completo (campos, dono real da migration) precisa ser alinhado
    # com o time de Gestão antes de evoluir este contrato.
    op.create_table(
        "projetos",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("nome", sa.String(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("projetos")
