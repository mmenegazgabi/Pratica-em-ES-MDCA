"""junção: login único (T-35) e persistência do Financeiro (E3)

As duas migrations partiram da mesma anterior (6bd565cae094) em paralelo:
b7d4e2a9c1f0 (tabelas do login) e c2d8e4f6a1b3 (Financeiro no banco). Esta revisão
só junta os dois ramos de novo; não muda nada no banco.

Funciona para qualquer banco: o que está em c2d8e4f6a1b3 (a produção em 10/11) ganha
as tabelas do login; o que está em b7d4e2a9c1f0 ganha as do Financeiro; um banco novo
ganha as duas.

Revision ID: d9f1a7c3b5e2
Revises: b7d4e2a9c1f0, c2d8e4f6a1b3
Create Date: 2026-11-10 18:45:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'd9f1a7c3b5e2'
down_revision: Union[str, Sequence[str], None] = ('b7d4e2a9c1f0', 'c2d8e4f6a1b3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Só junta os dois ramos."""


def downgrade() -> None:
    """Só separa os dois ramos."""
