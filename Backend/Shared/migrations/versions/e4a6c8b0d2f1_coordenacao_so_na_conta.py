"""coordenação só na conta (T-87)

A coordenação passa a ser um papel só, dado na conta (``usuarios_papeis``), que vale
para todos os programas. Ela deixa de existir como vínculo de programa
(``vinculos_equipe``).

Passo de dados: quem tinha vínculo de coordenação ganha ``coordenacao`` na conta (se
ainda não tinha), e esses vínculos são apagados. Cada conversão fica registrada no
``log_auditoria`` (módulo ``gestao``, ação ``converter_coordenacao``), com os dados do
vínculo apagado em ``detalhes``.

Depois, um CHECK impede vínculo novo com ``coordenacao``.

O Financeiro não muda: ele já lê ``coordenacao`` da conta e trata como "vê todos".

Revision ID: e4a6c8b0d2f1
Revises: d9f1a7c3b5e2
Create Date: 2026-11-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e4a6c8b0d2f1'
down_revision: Union[str, Sequence[str], None] = 'd9f1a7c3b5e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Converte vínculos de coordenação em papel da conta e proíbe novos."""
    op.execute(
        """
        INSERT INTO usuarios_papeis (usuario_id, papel_id)
        SELECT DISTINCT usuario_id, 'coordenacao' FROM vinculos_equipe
        WHERE papel_id = 'coordenacao'
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO log_auditoria (usuario_id, modulo, acao, alvo_tipo, alvo_id, descricao, detalhes)
        SELECT v.usuario_id, 'gestao', 'converter_coordenacao', 'vinculo', v.id,
               'Vínculo de coordenação convertido em papel da conta (T-87)',
               jsonb_build_object(
                   'programa_id', v.programa_id,
                   'data_entrada', v.data_entrada,
                   'data_saida', v.data_saida
               )
        FROM vinculos_equipe v
        WHERE v.papel_id = 'coordenacao'
        """
    )
    op.execute("DELETE FROM vinculos_equipe WHERE papel_id = 'coordenacao'")
    op.create_check_constraint(
        "ck_vinculos_equipe_sem_coordenacao",
        "vinculos_equipe",
        "papel_id <> 'coordenacao'",
    )


def downgrade() -> None:
    """Tira o CHECK. Os vínculos apagados não voltam (estão no log_auditoria)."""
    op.drop_constraint("ck_vinculos_equipe_sem_coordenacao", "vinculos_equipe", type_="check")
