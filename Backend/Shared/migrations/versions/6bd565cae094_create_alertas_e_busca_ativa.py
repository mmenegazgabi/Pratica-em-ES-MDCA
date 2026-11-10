"""create alertas de infrequencia e acoes de busca ativa; limite de faltas do programa

Revision ID: 6bd565cae094
Revises: 4e3a59521428
Create Date: 2026-11-10 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6bd565cae094'
down_revision: Union[str, Sequence[str], None] = '4e3a59521428'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# T-59 · US-06. CHECK instead of a Postgres ENUM, as in the other Gestão tables.
TIPOS_ALERTA = ("infrequencia",)
SITUACOES_ALERTA = ("aberto", "encerrado")
# The follow-up actions of the E2 prototype.
TIPOS_ACAO = ("contato_familia", "busca_ativa", "articulacao_rede", "revisao_contrato")
LIMITE_PADRAO = 3


def _criado_em() -> sa.Column:
    return sa.Column(
        "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def _fk(coluna: str, alvo: str, tabela: str, *, nullable: bool, ondelete: str = None) -> sa.Column:
    nome_alvo = alvo.split(".")[0]
    return sa.Column(
        coluna,
        sa.String(),
        sa.ForeignKey(alvo, name=f"fk_{tabela}_{coluna}_{nome_alvo}", ondelete=ondelete),
        nullable=nullable,
    )


def _em_lista(coluna: str, valores: Sequence[str], nome: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"{coluna} IN ({', '.join(repr(v) for v in valores)})", name=nome)


def upgrade() -> None:
    """Upgrade schema."""
    # Consecutive absences that raise an alert, set per program (prototype default: 3).
    op.add_column(
        "projetos",
        sa.Column("limite_faltas", sa.Integer(), nullable=False, server_default=str(LIMITE_PADRAO)),
    )
    op.create_check_constraint("ck_projetos_limite_faltas_positivo", "projetos", "limite_faltas > 0")

    # An infrequency alert for a person in a class. It stays open until someone closes it
    # with a justification; the absence counters follow the streak while it is open.
    op.create_table(
        "alertas",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tipo", sa.String(), nullable=False),
        _fk("programa_id", "projetos.id", "alertas", nullable=False),
        _fk("pessoa_id", "pessoas.id", "alertas", nullable=False),
        _fk("turma_id", "turmas.id", "alertas", nullable=False),
        # Who in the team follows it up (social worker of the program, else coordination).
        _fk("responsavel_id", "usuarios.id", "alertas", nullable=True),
        sa.Column("situacao", sa.String(), nullable=False, server_default="aberto"),
        sa.Column("faltas_consecutivas", sa.Integer(), nullable=False),
        # The program limit when the alert was raised.
        sa.Column("limite", sa.Integer(), nullable=False),
        sa.Column("primeira_falta", sa.Date(), nullable=False),
        sa.Column("ultima_falta", sa.Date(), nullable=False),
        _criado_em(),
        sa.Column("encerrado_em", sa.DateTime(timezone=True), nullable=True),
        _fk("encerrado_por", "usuarios.id", "alertas", nullable=True),
        sa.Column("justificativa_encerramento", sa.Text(), nullable=True),
        _em_lista("tipo", TIPOS_ALERTA, "ck_alertas_tipo_valido"),
        _em_lista("situacao", SITUACOES_ALERTA, "ck_alertas_situacao_valida"),
        sa.CheckConstraint("faltas_consecutivas >= limite AND limite > 0", name="ck_alertas_faltas_no_limite"),
        sa.CheckConstraint("ultima_falta >= primeira_falta", name="ck_alertas_periodo_das_faltas"),
        # US-06: closing requires a justification (and records when and by whom).
        sa.CheckConstraint(
            "situacao <> 'encerrado' OR (encerrado_em IS NOT NULL AND encerrado_por IS NOT NULL "
            "AND length(btrim(coalesce(justificativa_encerramento, ''))) > 0)",
            name="ck_alertas_encerramento_com_justificativa",
        ),
    )
    # One open alert per person, class and type; a new one only after closing.
    op.create_index(
        "ux_alertas_em_aberto",
        "alertas",
        ["pessoa_id", "turma_id", "tipo"],
        unique=True,
        postgresql_where=sa.text("situacao = 'aberto'"),
    )
    op.create_index("ix_alertas_programa_situacao", "alertas", ["programa_id", "situacao", "criado_em"])
    op.create_index("ix_alertas_pessoa_id", "alertas", ["pessoa_id"])

    # Active search and other follow-up actions: what was done, when, by whom and the
    # result. Never deleted, so the alert keeps its timeline.
    op.create_table(
        "acoes_busca_ativa",
        sa.Column("id", sa.String(), primary_key=True),
        _fk("alerta_id", "alertas.id", "acoes_busca_ativa", nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("resultado", sa.Text(), nullable=False),
        _fk("responsavel_id", "usuarios.id", "acoes_busca_ativa", nullable=False),
        _criado_em(),
        _em_lista("tipo", TIPOS_ACAO, "ck_acoes_busca_ativa_tipo_valido"),
        sa.CheckConstraint("length(btrim(resultado)) > 0", name="ck_acoes_busca_ativa_resultado_preenchido"),
    )
    op.create_index("ix_acoes_busca_ativa_alerta_data", "acoes_busca_ativa", ["alerta_id", "data"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("acoes_busca_ativa")
    op.drop_table("alertas")
    op.drop_constraint("ck_projetos_limite_faltas_positivo", "projetos", type_="check")
    op.drop_column("projetos", "limite_faltas")
