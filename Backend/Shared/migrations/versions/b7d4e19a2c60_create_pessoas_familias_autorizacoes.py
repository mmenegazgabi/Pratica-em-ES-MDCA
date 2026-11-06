"""create pessoas atendidas, responsaveis, nucleos familiares, documentos e autorizacoes

Revision ID: b7d4e19a2c60
Revises: 5c2e8d41a7b3
Create Date: 2026-11-05 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d4e19a2c60'
down_revision: Union[str, Sequence[str], None] = '5c2e8d41a7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# T-47 · US-03: CHECK instead of a Postgres ENUM so dropping the table leaves no type behind.
SITUACOES_PESSOA = ("ativo", "pendente", "inativo")
TIPOS_AUTORIZACAO = ("uso_de_imagem",)

# Created in this order, dropped in reverse.
TABELAS = (
    "nucleos_familiares",
    "pessoas",
    "responsaveis",
    "pessoas_responsaveis",
    "documentos_pessoa",
    "autorizacoes",
)


def _preenchido(coluna: str, nome: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"length(btrim({coluna})) > 0", name=nome)


def _em_lista(coluna: str, valores: Sequence[str], nome: str) -> sa.CheckConstraint:
    lista = ", ".join(f"'{v}'" for v in valores)
    return sa.CheckConstraint(f"{coluna} IN ({lista})", name=nome)


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


def upgrade() -> None:
    """Upgrade schema."""
    # T-47 · US-03: a family unit groups the people served who live together.
    op.create_table(
        "nucleos_familiares",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        _criado_em(),
        _preenchido("nome", "ck_nucleos_familiares_nome_preenchido"),
    )

    # People served (children, teenagers, young apprentices). nome_normalizado is
    # lowercase, without accents and with single spaces, computed by the application:
    # unaccent() is not IMMUTABLE and cannot back an index.
    op.create_table(
        "pessoas",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("nome_normalizado", sa.Text(), nullable=False),
        sa.Column("data_nascimento", sa.Date(), nullable=False),
        _fk("nucleo_familiar_id", "nucleos_familiares.id", "pessoas", nullable=False),
        # Reference program: who may see and edit the record (US-03 access rule).
        _fk("programa_id", "projetos.id", "pessoas", nullable=False),
        sa.Column("telefone", sa.Text(), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("situacao", sa.String(), nullable=False, server_default="ativo"),
        _fk("criado_por", "usuarios.id", "pessoas", nullable=True),
        _criado_em(),
        _preenchido("nome", "ck_pessoas_nome_preenchido"),
        _preenchido("nome_normalizado", "ck_pessoas_nome_normalizado_preenchido"),
        _em_lista("situacao", SITUACOES_PESSOA, "ck_pessoas_situacao_valida"),
    )
    # Duplicate search: same name with the same birth date (or the same guardian, below).
    op.create_index("ix_pessoas_nome_nascimento", "pessoas", ["nome_normalizado", "data_nascimento"])
    op.create_index("ix_pessoas_programa_id", "pessoas", ["programa_id"])
    op.create_index("ix_pessoas_nucleo_familiar_id", "pessoas", ["nucleo_familiar_id"])

    # Guardians are people in their own right: one guardian may answer for several
    # people served (siblings), so they are not columns of pessoas.
    op.create_table(
        "responsaveis",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("nome_normalizado", sa.Text(), nullable=False),
        sa.Column("telefone", sa.Text(), nullable=True),
        _criado_em(),
        _preenchido("nome", "ck_responsaveis_nome_preenchido"),
        _preenchido("nome_normalizado", "ck_responsaveis_nome_normalizado_preenchido"),
    )
    op.create_index("ix_responsaveis_nome", "responsaveis", ["nome_normalizado"])

    op.create_table(
        "pessoas_responsaveis",
        _fk("pessoa_id", "pessoas.id", "pessoas_responsaveis", nullable=False, ondelete="CASCADE"),
        _fk("responsavel_id", "responsaveis.id", "pessoas_responsaveis", nullable=False),
        sa.Column("parentesco", sa.Text(), nullable=True),
        # Legal guardian: required for minors (rule enforced by the API, T-48).
        sa.Column("responsavel_legal", sa.Boolean(), nullable=False, server_default=sa.false()),
        _criado_em(),
        sa.PrimaryKeyConstraint("pessoa_id", "responsavel_id", name="pk_pessoas_responsaveis"),
    )
    op.create_index("ix_pessoas_responsaveis_responsavel_id", "pessoas_responsaveis", ["responsavel_id"])

    # Only metadata for now; chave_arquivo will point to the file in storage (R2) when
    # the upload is added.
    op.create_table(
        "documentos_pessoa",
        sa.Column("id", sa.String(), primary_key=True),
        _fk("pessoa_id", "pessoas.id", "documentos_pessoa", nullable=False, ondelete="CASCADE"),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("nome_arquivo", sa.Text(), nullable=False),
        sa.Column("tamanho", sa.BigInteger(), nullable=True),
        sa.Column("chave_arquivo", sa.Text(), nullable=True),
        _fk("criado_por", "usuarios.id", "documentos_pessoa", nullable=True),
        _criado_em(),
        _preenchido("tipo", "ck_documentos_pessoa_tipo_preenchido"),
        _preenchido("nome_arquivo", "ck_documentos_pessoa_nome_arquivo_preenchido"),
        sa.CheckConstraint("tamanho IS NULL OR tamanho >= 0", name="ck_documentos_pessoa_tamanho_valido"),
    )
    op.create_index("ix_documentos_pessoa_pessoa_id", "documentos_pessoa", ["pessoa_id"])

    # Situation (vigente, vencida, revogada) is derived from revogada_em and valida_ate,
    # not stored: a stored "vigente" would turn wrong on the day it expires.
    op.create_table(
        "autorizacoes",
        sa.Column("id", sa.String(), primary_key=True),
        _fk("pessoa_id", "pessoas.id", "autorizacoes", nullable=False, ondelete="CASCADE"),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("valida_de", sa.Date(), nullable=False),
        sa.Column("valida_ate", sa.Date(), nullable=False),
        _fk("documento_id", "documentos_pessoa.id", "autorizacoes", nullable=True),
        sa.Column("revogada_em", sa.DateTime(timezone=True), nullable=True),
        _fk("revogada_por", "usuarios.id", "autorizacoes", nullable=True),
        _fk("criado_por", "usuarios.id", "autorizacoes", nullable=True),
        _criado_em(),
        _em_lista("tipo", TIPOS_AUTORIZACAO, "ck_autorizacoes_tipo_valido"),
        sa.CheckConstraint("valida_ate >= valida_de", name="ck_autorizacoes_validade_coerente"),
        # Who revoked only makes sense with when it was revoked.
        sa.CheckConstraint(
            "revogada_por IS NULL OR revogada_em IS NOT NULL",
            name="ck_autorizacoes_revogacao_coerente",
        ),
    )
    op.create_index("ix_autorizacoes_pessoa_tipo", "autorizacoes", ["pessoa_id", "tipo"])


def downgrade() -> None:
    """Downgrade schema."""
    # Dropping a table also drops its indexes and constraints.
    for tabela in reversed(TABELAS):
        op.drop_table(tabela)
