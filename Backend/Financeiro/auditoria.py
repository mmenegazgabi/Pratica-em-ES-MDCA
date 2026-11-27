"""Auditoria do Financeiro na trilha única (T-34 · US-08; plano de integração, Trabalho 4).

As ações sensíveis do Financeiro vão para ``log_auditoria`` com ``modulo = 'financeiro'``,
pela mesma função da Gestão (``Shared/auditoria.py``), **na mesma transação da ação**: se
a ação falhar, o registro também não fica. As tentativas negadas (403) são registradas
em transação própria, porque a ação em si não acontece.

Ações registradas (``acao``):

- ``criar_projeto``, ``encerrar_projeto``, ``reabrir_projeto``;
- ``criar_orcamento``, ``editar_orcamento``;
- ``criar_lancamento``, ``aprovar_lancamento``, ``rejeitar_lancamento``,
  ``reenviar_lancamento``, ``conciliar_lancamento`` (com ``item_extrato_id`` nos
  detalhes quando a referência é um item do extrato importado);
- ``importar_extrato`` (só quando algum item novo entrou);
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
    "importar_extrato": "Importou extrato bancário",
    "gerar_relatorio": "Gerou prestação de contas",
    ACESSO_NEGADO: "Acesso negado",
}


# Ações dos outros módulos da trilha, para a tela única de Auditoria (GET /auditoria
# com ``modulo=gestao``, ``plataforma`` ou ``todos``). Os códigos são os que
# ``Gestao/`` e ``Acesso/`` gravam; um código sem rótulo aparece como veio.
# Os rótulos da Gestão moram no próprio módulo (``Gestao/auditoria.py``, T-81): ação nova
# da Gestão ganha rótulo lá, sem mexer neste arquivo.
from Gestao.auditoria import ROTULOS as ROTULOS_DA_GESTAO  # noqa: E402
ROTULOS_DA_PLATAFORMA = {
    "login": "Entrou no sistema",
    "login_falhou": "Tentativa de entrar sem sucesso",
    "logout": "Saiu do sistema",
    "primeiro_acesso": "Fez o primeiro acesso",
    "usuario_criado": "Cadastrou conta",
    "usuario_editado": "Editou conta",
    "usuario_desativado": "Desativou conta",
    "usuario_reativado": "Reativou conta",
    "codigo_gerado": "Gerou código de acesso",
    "codigo_emitido": "Emitiu código de primeiro acesso",
    ACESSO_NEGADO: "Acesso negado",
}
_ROTULOS_POR_MODULO = {"financeiro": ROTULOS, "gestao": ROTULOS_DA_GESTAO, "plataforma": ROTULOS_DA_PLATAFORMA}


def rotulo(acao: str, modulo: str = MODULO) -> str:
    return _ROTULOS_POR_MODULO.get(modulo, ROTULOS).get(acao, acao)


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
