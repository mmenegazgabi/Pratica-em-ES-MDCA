"""create plano de acao dos programas (convenios, objetivos, acoes, metas e vagas)

Revision ID: 5c2e8d41a7b3
Revises: 3fb5b9b4c7fa
Create Date: 2026-11-05 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c2e8d41a7b3'
down_revision: Union[str, Sequence[str], None] = '3fb5b9b4c7fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# T-45 · US-02: how often an action is followed up. CHECK instead of a Postgres
# ENUM so dropping the table leaves no type behind.
PERIODICIDADES = ("semanal", "quinzenal", "mensal", "bimestral", "trimestral", "semestral", "anual")

COLUNAS_PROGRAMA = (
    "identificador",
    "publico",
    "responsavel",
    "vigencia_inicio",
    "vigencia_fim",
    "descricao",
)


def _preenchido(coluna: str, nome: str, opcional: bool = False) -> sa.CheckConstraint:
    regra = f"length(btrim({coluna})) > 0"
    if opcional:
        regra = f"{coluna} IS NULL OR {regra}"
    return sa.CheckConstraint(regra, name=nome)


def _programa_fk(tabela: str) -> sa.Column:
    return sa.Column(
        "programa_id",
        sa.String(),
        sa.ForeignKey("projetos.id", name=f"fk_{tabela}_programa_id_projetos"),
        nullable=False,
    )


def upgrade() -> None:
    """Upgrade schema."""
    # T-45 · US-02: the rest of the canonical Programa record (ARQ-02). Nullable because
    # rows created before this migration (and by the Financeiro) only have a name; the
    # Gestão API requires them on every new program.
    op.add_column("projetos", sa.Column("identificador", sa.String(), nullable=True))
    op.add_column("projetos", sa.Column("publico", sa.Text(), nullable=True))
    op.add_column("projetos", sa.Column("responsavel", sa.Text(), nullable=True))
    op.add_column("projetos", sa.Column("vigencia_inicio", sa.Date(), nullable=True))
    op.add_column("projetos", sa.Column("vigencia_fim", sa.Date(), nullable=True))
    op.add_column("projetos", sa.Column("descricao", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_projetos_identificador_preenchido",
        "projetos",
        "identificador IS NULL OR length(btrim(identificador)) > 0",
    )
    op.create_check_constraint(
        "ck_projetos_vigencia_fim_depois_do_inicio",
        "projetos",
        "vigencia_inicio IS NULL OR vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
    )
    # The identifier shared with the Financeiro; unique without telling case apart.
    op.create_index(
        "ux_projetos_identificador", "projetos", [sa.text("lower(identificador)")], unique=True
    )

    # Agreements and partnerships that fund or support a program.
    op.create_table(
        "convenios",
        sa.Column("id", sa.String(), primary_key=True),
        _programa_fk("convenios"),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("concedente", sa.Text(), nullable=True),
        sa.Column("vigencia_inicio", sa.Date(), nullable=True),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        _preenchido("nome", "ck_convenios_nome_preenchido"),
        sa.CheckConstraint(
            "vigencia_inicio IS NULL OR vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
            name="ck_convenios_vigencia_fim_depois_do_inicio",
        ),
    )
    op.create_index("ix_convenios_programa_id", "convenios", ["programa_id"])

    # Action plan: objetivo -> acoes -> metas -> registros_meta.
    op.create_table(
        "objetivos",
        sa.Column("id", sa.String(), primary_key=True),
        _programa_fk("objetivos"),
        sa.Column("descricao", sa.Text(), nullable=False),
        _preenchido("descricao", "ck_objetivos_descricao_preenchida"),
    )
    op.create_index("ix_objetivos_programa_id", "objetivos", ["programa_id"])

    # "Period inside the program's validity" needs the program row, so it stays in the
    # API; the table only guarantees the fields exist and the period is ordered.
    op.create_table(
        "acoes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "objetivo_id",
            sa.String(),
            sa.ForeignKey("objetivos.id", name="fk_acoes_objetivo_id_objetivos"),
            nullable=False,
        ),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("periodo_inicio", sa.Date(), nullable=False),
        sa.Column("periodo_fim", sa.Date(), nullable=False),
        sa.Column("resultado_esperado", sa.Text(), nullable=False),
        sa.Column("periodicidade", sa.String(), nullable=False),
        _preenchido("descricao", "ck_acoes_descricao_preenchida"),
        _preenchido("resultado_esperado", "ck_acoes_resultado_esperado_preenchido"),
        sa.CheckConstraint(
            "periodo_fim >= periodo_inicio", name="ck_acoes_periodo_fim_depois_do_inicio"
        ),
        sa.CheckConstraint(
            "periodicidade IN (" + ", ".join(f"'{p}'" for p in PERIODICIDADES) + ")",
            name="ck_acoes_periodicidade",
        ),
    )
    op.create_index("ix_acoes_objetivo_id", "acoes", ["objetivo_id"])

    # Quantitative target of an action (e.g. 120 activities). unidade is free text.
    op.create_table(
        "metas",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "acao_id",
            sa.String(),
            sa.ForeignKey("acoes.id", name="fk_metas_acao_id_acoes"),
            nullable=False,
        ),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("valor_planejado", sa.Numeric(12, 2), nullable=False),
        sa.Column("unidade", sa.Text(), nullable=True),
        _preenchido("descricao", "ck_metas_descricao_preenchida"),
        sa.CheckConstraint("valor_planejado > 0", name="ck_metas_valor_planejado_positivo"),
    )
    op.create_index("ix_metas_acao_id", "metas", ["acao_id"])

    # What was achieved towards a goal; "realizado" on the dashboard is their sum.
    op.create_table(
        "registros_meta",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "meta_id",
            sa.String(),
            sa.ForeignKey("metas.id", name="fk_registros_meta_meta_id_metas"),
            nullable=False,
        ),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("valor_realizado", sa.Numeric(12, 2), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "valor_realizado > 0", name="ck_registros_meta_valor_realizado_positivo"
        ),
    )
    op.create_index("ix_registros_meta_meta_id", "registros_meta", ["meta_id"])

    # Places the program offers, by group (e.g. "Manhã · 6 a 10 anos").
    op.create_table(
        "vagas",
        sa.Column("id", sa.String(), primary_key=True),
        _programa_fk("vagas"),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        _preenchido("descricao", "ck_vagas_descricao_preenchida"),
        sa.CheckConstraint("quantidade > 0", name="ck_vagas_quantidade_positiva"),
    )
    op.create_index(
        "ux_vagas_programa_id_descricao",
        "vagas",
        ["programa_id", sa.text("lower(descricao)")],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Dropping a table also drops its indexes and constraints. Children first.
    op.drop_table("vagas")
    op.drop_table("registros_meta")
    op.drop_table("metas")
    op.drop_table("acoes")
    op.drop_table("objetivos")
    op.drop_table("convenios")
    op.drop_index("ux_projetos_identificador", table_name="projetos")
    op.drop_constraint("ck_projetos_vigencia_fim_depois_do_inicio", "projetos", type_="check")
    op.drop_constraint("ck_projetos_identificador_preenchido", "projetos", type_="check")
    for coluna in reversed(COLUNAS_PROGRAMA):
        op.drop_column("projetos", coluna)
