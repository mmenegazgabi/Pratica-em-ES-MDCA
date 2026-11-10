"""Leitura da trilha de auditoria (``log_auditoria``) para a tela de auditoria.

Não devolve ``detalhes``: o campo pode guardar dado sensível. A tabela só aceita inclusão.
"""

from datetime import date
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.engine import Connection

LIMITE_PADRAO = 200
LIMITE_MAXIMO = 500
MODULOS = ("financeiro", "gestao", "plataforma")
# O período é em dias do calendário de quem usa a tela.
FUSO = "America/Sao_Paulo"

_CAMPOS_DO_TEXTO = ("l.acao", "l.descricao", "l.usuario_id", "l.alvo_id")


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def consultar(
    conexao: Connection,
    *,
    texto: Optional[str] = None,
    modulo: Optional[str] = None,
    desde: Optional[date] = None,
    ate: Optional[date] = None,
    limite: int = LIMITE_PADRAO,
) -> List[Dict[str, Any]]:
    """Eventos mais recentes primeiro, já com o nome de quem agiu (se houver cadastro)."""
    condicoes = []
    parametros: Dict[str, Any] = {"limite": min(max(limite, 1), LIMITE_MAXIMO)}
    texto = (texto or "").strip()
    if texto:
        parametros["texto"] = f"%{_escapar_like(texto)}%"
        condicoes.append(
            "(" + " OR ".join(f"{c} ILIKE :texto ESCAPE '\\'" for c in _CAMPOS_DO_TEXTO) + ")"
        )
    if modulo:
        parametros["modulo"] = modulo
        condicoes.append("l.modulo = :modulo")
    dia = f"(l.ocorrido_em AT TIME ZONE '{FUSO}')::date"
    if desde:
        parametros["desde"] = desde
        condicoes.append(f"{dia} >= :desde")
    if ate:
        parametros["ate"] = ate
        condicoes.append(f"{dia} <= :ate")

    onde = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    linhas = conexao.execute(
        sa.text(
            f"""
            SELECT l.id, l.ocorrido_em, l.usuario_id, u.nome AS usuario_nome, l.modulo,
                   l.acao, l.alvo_tipo, l.alvo_id, l.descricao
            FROM log_auditoria l
            LEFT JOIN usuarios u ON u.id = l.usuario_id
            {onde}
            ORDER BY l.ocorrido_em DESC, l.id DESC
            LIMIT :limite
            """
        ),
        parametros,
    ).mappings()
    return [dict(linha) for linha in linhas]
