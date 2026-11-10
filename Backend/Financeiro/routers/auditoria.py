"""GET /auditoria?modulo=financeiro — trilha de auditoria do Financeiro (T-34 · US-08).

Para Coordenação e Direção. Só leitura: nenhuma rota edita ou apaga ``log_auditoria``.

Cada item traz os campos que a tela Auditoria já usa nos dados de exemplo
(``quando``, ``quem``, ``acao`` em texto e ``alvo``), para a tela trocar
``AUDITORIA_EXEMPLO`` por esta rota sem remontar nada, e também os campos técnicos
(``codigo``, ``usuario_id``, ``alvo_tipo``, ``alvo_id``, ``detalhes``). Mais recentes
primeiro.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

if __package__ == "routers":
    import auditoria
    from autenticacao import Papel, exigir_papel
    from persistencia import obter_repositorio
else:
    from .. import auditoria
    from ..autenticacao import Papel, exigir_papel
    from ..persistencia import obter_repositorio

router = APIRouter(tags=["auditoria"])


class EventoAuditoria(BaseModel):
    id: int
    quando: datetime
    quem: Optional[str]
    acao: str
    alvo: Optional[str]
    codigo: str
    usuario_id: Optional[str]
    alvo_tipo: Optional[str]
    alvo_id: Optional[str]
    detalhes: Optional[Dict[str, Any]]


class AuditoriaPaginada(BaseModel):
    itens: List[EventoAuditoria]
    total: int
    pagina: int
    tamanho: int


def _evento(linha: Dict[str, Any]) -> EventoAuditoria:
    return EventoAuditoria(
        id=linha["id"],
        quando=linha["ocorrido_em"],
        # Nome da conta quando o usuário existe; senão, o id que a tela mandou.
        quem=linha.get("usuario_nome") or linha["usuario_id"],
        acao=auditoria.rotulo(linha["acao"]),
        alvo=linha["descricao"],
        codigo=linha["acao"],
        usuario_id=linha["usuario_id"],
        alvo_tipo=linha["alvo_tipo"],
        alvo_id=linha["alvo_id"],
        detalhes=linha["detalhes"],
    )


@router.get("/auditoria", response_model=AuditoriaPaginada)
def listar_auditoria(
    modulo: Literal["financeiro"] = Query("financeiro", description="Por enquanto só o Financeiro."),
    acao: Optional[str] = Query(None, description="Código da ação, ex.: aprovar_lancamento."),
    usuario_id: Optional[str] = Query(None),
    desde: Optional[date] = Query(None, description="A partir deste dia (AAAA-MM-DD)."),
    ate: Optional[date] = Query(None, description="Até este dia, inclusive (AAAA-MM-DD)."),
    pagina: int = Query(1, ge=1),
    tamanho: int = Query(50, ge=1, le=200),
    _papel: Papel = Depends(exigir_papel(Papel.COORDENACAO, Papel.DIRECAO)),
    repositorio=Depends(obter_repositorio),
) -> AuditoriaPaginada:
    if desde and ate and ate < desde:
        raise HTTPException(status_code=422, detail="ate não pode ser anterior a desde")
    linhas, total = repositorio.listar_auditoria(
        acao=acao, usuario_id=usuario_id, desde=desde, ate=ate, pagina=pagina, tamanho=tamanho
    )
    return AuditoriaPaginada(itens=[_evento(l) for l in linhas], total=total, pagina=pagina, tamanho=tamanho)
