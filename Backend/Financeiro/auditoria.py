"""Auditoria do Financeiro na trilha única (T-34 · US-08; plano de integração, Trabalho 4).

As ações sensíveis do Financeiro vão para ``log_auditoria`` com ``modulo = 'financeiro'``,
pela mesma função da Gestão (``Shared/auditoria.py``), **na mesma transação da ação**: se
a ação falhar, o registro também não fica. As tentativas negadas (403) são registradas
em transação própria, porque a ação em si não acontece.

Ações registradas (``acao``):

- ``criar_projeto``, ``encerrar_projeto``, ``reabrir_projeto``;
- ``criar_orcamento``, ``editar_orcamento``;
- ``criar_lancamento``, ``aprovar_lancamento``, ``rejeitar_lancamento``,
  ``reenviar_lancamento``, ``conciliar_lancamento``;
- ``gerar_relatorio``;
- ``acesso_negado``.

``descricao`` guarda o texto que a tela Auditoria mostra como "alvo" (ex.:
``Materiais · R$ 180,00 · Leitura``), e ``ROTULOS`` o texto da ação ("Aprovou despesa").
"""

from typing import Any, Dict, Optional

if __package__:
    from .moeda import formatar_reais
else:
    from moeda import formatar_reais

MODULO = "financeiro"
ACESSO_NEGADO = "acesso_negado"

ROTULOS = {
    "criar_projeto": "Cadastrou projeto",
    "encerrar_projeto": "Encerrou projeto",
    "reabrir_projeto": "Reabriu projeto",
    "criar_orcamento": "Criou orçamento",
    "editar_orcamento": "Editou orçamento",
    "criar_lancamento": "Lançou despesa",
    "aprovar_lancamento": "Aprovou despesa",
    "rejeitar_lancamento": "Rejeitou despesa",
    "reenviar_lancamento": "Reenviou despesa",
    "conciliar_lancamento": "Conciliou lançamento",
    "gerar_relatorio": "Gerou prestação de contas",
    ACESSO_NEGADO: "Acesso negado",
}


def rotulo(acao: str) -> str:
    return ROTULOS.get(acao, acao)


def alvo(*partes: Optional[str]) -> str:
    """"Materiais · R$ 180,00 · Leitura": as partes preenchidas, separadas por ·."""
    return " · ".join(p for p in partes if p)


def alvo_lancamento(lancamento, projeto: Optional[str], *extra: Optional[str]) -> str:
    return alvo(lancamento.categoria, formatar_reais(lancamento.valor), projeto, *extra)


def registrar(
    repositorio,
    identidade,
    acao: str,
    *,
    alvo_tipo: Optional[str] = None,
    alvo_id: Optional[str] = None,
    descricao: Optional[str] = None,
    detalhes: Optional[Dict[str, Any]] = None,
) -> None:
    """Grava o evento pelo repositório da requisição (mesma transação da ação)."""
    repositorio.auditar(
        usuario_id=identidade.usuario_id if identidade else None,
        acao=acao,
        alvo_tipo=alvo_tipo,
        alvo_id=alvo_id,
        descricao=descricao,
        detalhes=detalhes,
    )
