"""persistencia do Financeiro: campos que faltavam em lancamentos, notificacoes e rascunhos

O Financeiro passa a gravar no PostgreSQL o que antes ficava só em memória.
As tabelas projetos, orcamentos, orcamento_categorias e lancamentos já existiam;
aqui entram os campos que a API usa e o banco ainda não tinha, e as tabelas das
notificações in-app (T-17) e dos rascunhos de despesa (redesign).

Revision ID: c2d8e4f6a1b3
Revises: 4e3a59521428
Create Date: 2026-11-09 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c2d8e4f6a1b3'
down_revision: Union[str, Sequence[str], None] = '4e3a59521428'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # T-18 · US-04: a fila de aprovação ordena por quando o lançamento foi feito.
    # server_default preenche as linhas que já existem.
    op.add_column(
        "lancamentos",
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Redesign: quando foi aprovado (lista de lançamentos).
    op.add_column(
        "lancamentos",
        sa.Column("aprovado_em", sa.DateTime(timezone=True), nullable=True),
    )
    # Redesign: motivos de rejeições já corrigidas e reenviadas, em ordem.
    op.add_column(
        "lancamentos",
        sa.Column(
            "motivos_rejeicao_anteriores",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.create_index("ix_lancamentos_autor_id", "lancamentos", ["autor_id"])

    # T-17 · US-04: notificação in-app ao autor do lançamento.
    op.create_table(
        "notificacoes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("destinatario_id", sa.String(), nullable=False),
        sa.Column(
            "lancamento_id",
            sa.String(),
            sa.ForeignKey(
                "lancamentos.id",
                name="fk_notificacoes_lancamento_id_lancamentos",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("lida", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "tipo IN ('lancamento_aprovado', 'lancamento_rejeitado')",
            name="ck_notificacoes_tipo",
        ),
    )
    op.create_index(
        "ix_notificacoes_destinatario_id", "notificacoes", ["destinatario_id"]
    )

    # Redesign: foto do comprovante agora, dados da despesa depois.
    op.create_table(
        "rascunhos_despesa",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("autor_id", sa.String(), nullable=False),
        sa.Column("comprovante_chave", sa.String(), nullable=False),
        sa.Column("nome_original", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("tamanho", sa.Integer(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("tamanho > 0", name="ck_rascunhos_despesa_tamanho_positivo"),
    )
    op.create_index("ix_rascunhos_despesa_autor_id", "rascunhos_despesa", ["autor_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_rascunhos_despesa_autor_id", table_name="rascunhos_despesa")
    op.drop_table("rascunhos_despesa")
    op.drop_index("ix_notificacoes_destinatario_id", table_name="notificacoes")
    op.drop_table("notificacoes")
    op.drop_index("ix_lancamentos_autor_id", table_name="lancamentos")
    op.drop_column("lancamentos", "motivos_rejeicao_anteriores")
    op.drop_column("lancamentos", "aprovado_em")
    op.drop_column("lancamentos", "criado_em")
