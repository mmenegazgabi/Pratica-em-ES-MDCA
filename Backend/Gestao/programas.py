"""Programas/Projetos do cadastro canônico (tabela ``projetos``, ARQ-02).

Por enquanto só a leitura, como exemplo da estrutura do módulo (T-00f). O esquema
completo (convênios, objetivos, ações, metas e vagas) chega com a US-02, combinado
com o Financeiro, que já referencia ``projetos`` em orçamentos e lançamentos.
"""

from dataclasses import dataclass
from typing import List

import sqlalchemy as sa
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class Programa:
    id: str
    nome: str


def listar_programas(conexao: Connection) -> List[Programa]:
    linhas = conexao.execute(
        sa.text("SELECT id, nome FROM projetos ORDER BY lower(nome), id")
    )
    return [Programa(id=linha.id, nome=linha.nome) for linha in linhas]
