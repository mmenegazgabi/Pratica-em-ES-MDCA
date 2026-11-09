"""add senha_hash to usuarios

Revision ID: 62959ecab341
Revises: b7d4e19a2c60
Create Date: 2026-11-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '62959ecab341'
down_revision: Union[str, Sequence[str], None] = 'b7d4e19a2c60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # T-35 · US-08: password for the single sign-on, stored as a scrypt hash (never the
    # password itself). Nullable: an account without a password cannot log in, and the
    # accounts created before this migration keep working with the old access code.
    op.add_column("usuarios", sa.Column("senha_hash", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("usuarios", "senha_hash")
