"""GET /auditoria — trilha única de auditoria da plataforma (T-34 · US-08).

``modulo`` escolhe a parte da trilha: ``financeiro`` (o padrão, como antes), ``gestao``,
``plataforma`` (login e administração de contas) ou ``todos``.

Quem lê:

- Coordenação, Direção e Administração: tudo;
- Psicologia: só os próprios registros (``escopo = "proprios"`` na resposta), como a
  trilha da Gestão já fazia no protótipo;
- os demais papéis: 403, e a tentativa fica na trilha.

Os papéis vêm da sessão (papéis da plataforma e vínculos ativos com programas); no modo
serviço, do ``X-Papel-Usuario``. Só leitura: nenhuma rota edita ou apaga ``log_auditoria``.

Cada item traz os campos que a tela Auditoria já usa nos dados de exemplo
(``quando``, ``quem``, ``acao`` em texto e ``alvo``), para a tela trocar
``AUDITORIA_EXEMPLO`` por esta rota sem remontar nada, e também os campos técnicos
(``codigo``, ``usuario_id``, ``alvo_tipo``, ``alvo_id``, ``detalhes``). Mais recentes
primeiro.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel

if __package__ == "routers":
    import auditoria
    from autenticacao import (
        CABECALHO_PAPEL,
        AcessoFinanceiro,
        _vinculos_ativos,
        exigir_autenticacao,
        obter_usuario,
        registrar_acesso_negado,
    )
    from persistencia import obter_repositorio
else:
    from .. import auditoria
    from ..autenticacao import (
        CABECALHO_PAPEL,
        AcessoFinanceiro,
        _vinculos_ativos,
        exigir_autenticacao,
        obter_usuario,
        registrar_acesso_negado,
    )
    from ..persistencia import obter_repositorio

router = APIRouter(tags=["auditoria"])

MODULOS_DA_TRILHA = {
    "financeiro": ("financeiro",),
    "gestao": ("gestao",),
    "plataforma": ("plataforma",),
    "todos": ("financeiro", "gestao", "plataforma"),
}
PAPEIS_QUE_LEEM_TUDO = frozenset({"coordenacao", "direcao", "administracao"})
PAPEL_QUE_LE_OS_PROPRIOS = "psicologo"
SEM_ACESSO = "A auditoria é para Coordenação, Direção e Administração; a Psicologia vê os próprios registros."


@dataclass(frozen=True)
class Leitor:
    usuario_id: Optional[str]
    # True: só os registros feitos pela própria pessoa (Psicologia).
    so_os_proprios: bool


def exigir_leitor_da_auditoria(
    request: Request,
    identidade=Depends(exigir_autenticacao),
    usuario: Optional[str] = Depends(obter_usuario),
    papel: Optional[str] = Header(None, alias=CABECALHO_PAPEL),
) -> Leitor:
    if identidade.servico:
        papeis = {(papel or "").strip().lower()}
        usuario_id = usuario
    else:
        usuario_id = identidade.usuario_id
        vinculos = _vinculos_ativos(usuario_id, date.today())
        papeis = set(identidade.papeis) | {v.papel_id for v in vinculos}
    if papeis & PAPEIS_QUE_LEEM_TUDO:
        return Leitor(usuario_id, so_os_proprios=False)
    if PAPEL_QUE_LE_OS_PROPRIOS in papeis and usuario_id:
        return Leitor(usuario_id, so_os_proprios=True)
    acesso = AcessoFinanceiro(
        usuario_id, frozenset(papeis - {""}), via_sessao=not identidade.servico, rota=f"{request.method} {request.url.path}"
    )
    registrar_acesso_negado(acesso, SEM_ACESSO)
    raise HTTPException(status_code=403, detail=SEM_ACESSO)


class EventoAuditoria(BaseModel):
    id: int
    quando: datetime
    modulo: str
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
    # "todos" ou "proprios" (Psicologia: só os registros feitos pela própria pessoa).
    escopo: Literal["todos", "proprios"] = "todos"


def _alvo(linha: Dict[str, Any]) -> Optional[str]:
    """O que a tela mostra em "Detalhe": a descrição gravada ou, nos eventos de contas,
    o nome da conta (ou o e-mail digitado, numa tentativa de entrar sem sucesso)."""
    if linha.get("descricao"):
        return linha["descricao"]
    if linha.get("alvo_nome"):
        return linha["alvo_nome"]
    if linha.get("acao") == "login_falhou":
        return linha.get("alvo_id")
    return None


def _evento(linha: Dict[str, Any]) -> EventoAuditoria:
    modulo = linha.get("modulo") or "financeiro"
    return EventoAuditoria(
        id=linha["id"],
        quando=linha["ocorrido_em"],
        modulo=modulo,
        # Nome da conta quando o usuário existe; senão, o id que a tela mandou.
        quem=linha.get("usuario_nome") or linha["usuario_id"],
        acao=auditoria.rotulo(linha["acao"], modulo),
        alvo=_alvo(linha),
        codigo=linha["acao"],
        usuario_id=linha["usuario_id"],
        alvo_tipo=linha["alvo_tipo"],
        alvo_id=linha["alvo_id"],
        detalhes=linha["detalhes"],
    )


@router.get("/auditoria", response_model=AuditoriaPaginada)
def listar_auditoria(
    modulo: Literal["financeiro", "gestao", "plataforma", "todos"] = Query(
        "financeiro", description="financeiro, gestao, plataforma (login e contas) ou todos."
    ),
    acao: Optional[str] = Query(None, description="Código da ação, ex.: aprovar_lancamento."),
    usuario_id: Optional[str] = Query(None),
    desde: Optional[date] = Query(None, description="A partir deste dia (AAAA-MM-DD)."),
    ate: Optional[date] = Query(None, description="Até este dia, inclusive (AAAA-MM-DD)."),
    pagina: int = Query(1, ge=1),
    tamanho: int = Query(50, ge=1, le=200),
    leitor: Leitor = Depends(exigir_leitor_da_auditoria),
    repositorio=Depends(obter_repositorio),
) -> AuditoriaPaginada:
    if desde and ate and ate < desde:
        raise HTTPException(status_code=422, detail="ate não pode ser anterior a desde")
    if leitor.so_os_proprios:
        # Psicologia: o filtro de pessoa não abre os registros dos outros.
        usuario_id = leitor.usuario_id
    linhas, total = repositorio.listar_auditoria(
        modulos=MODULOS_DA_TRILHA[modulo],
        acao=acao,
        usuario_id=usuario_id,
        desde=desde,
        ate=ate,
        pagina=pagina,
        tamanho=tamanho,
    )
    return AuditoriaPaginada(
        itens=[_evento(l) for l in linhas],
        total=total,
        pagina=pagina,
        tamanho=tamanho,
        escopo="proprios" if leitor.so_os_proprios else "todos",
    )
