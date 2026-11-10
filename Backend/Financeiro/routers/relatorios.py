"""GET /relatorios/prestacao-contas (T-25 · US-06).

Gera o relatório de prestação de contas de um projeto num período, em PDF ou
XLSX, usando o serviço da T-24 (``relatorio_prestacao``). Só Coordenação e
Direção podem gerar (403 para os outros papéis; 401 sem o código de acesso).

Parâmetros (query):

- ``projeto_id``: projeto cadastrado (404 se não existir);
- ``data_inicio`` e ``data_fim``: período, AAAA-MM-DD (422 se o fim for antes
  do início);
- ``formato``: ``pdf`` (padrão) ou ``xlsx``.

Projeto sem lançamentos aprovados no período (ou sem orçamento) gera o
relatório normalmente, com a lista vazia e realizado zero.
"""

import os
import re
from datetime import date
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

if __package__ == "routers":
    from autenticacao import Papel, exigir_papel
    from projetos import buscar_projeto
    from relatorio_prestacao import (
        CONTENT_TYPE_PDF,
        CONTENT_TYPE_XLSX,
        RelatorioInvalido,
        gerar_pdf,
        gerar_xlsx,
        montar_relatorio,
        nome_do_arquivo,
    )
    from persistencia import obter_repositorio
else:
    from ..autenticacao import Papel, exigir_papel
    from ..projetos import buscar_projeto
    from ..relatorio_prestacao import (
        CONTENT_TYPE_PDF,
        CONTENT_TYPE_XLSX,
        RelatorioInvalido,
        gerar_pdf,
        gerar_xlsx,
        montar_relatorio,
        nome_do_arquivo,
    )
    from ..persistencia import obter_repositorio

router = APIRouter(tags=["relatorios"])

# Endereço público da API, usado nos links dos comprovantes. Sem a variável,
# vale o endereço pelo qual a requisição chegou.
VARIAVEL_URL_PUBLICA = "FINANCEIRO_URL_PUBLICA"


class FormatoRelatorio(str, Enum):
    PDF = "pdf"
    XLSX = "xlsx"


_GERADORES = {
    FormatoRelatorio.PDF: (gerar_pdf, CONTENT_TYPE_PDF),
    FormatoRelatorio.XLSX: (gerar_xlsx, CONTENT_TYPE_XLSX),
}


def _url_base(request: Request) -> str:
    configurada = os.getenv(VARIAVEL_URL_PUBLICA, "").strip()
    if configurada:
        return configurada
    # No Cloud Run o HTTPS termina antes da API: o esquema original vem em
    # X-Forwarded-Proto. Só "http" e "https" são aceitos.
    esquema = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if esquema not in ("http", "https"):
        esquema = request.url.scheme
    return f"{esquema}://{request.url.netloc}"


@router.get(
    "/relatorios/prestacao-contas",
    response_class=Response,
    responses={
        200: {
            "description": "Arquivo do relatório (PDF ou XLSX).",
            "content": {CONTENT_TYPE_PDF: {}, CONTENT_TYPE_XLSX: {}},
        },
        401: {"description": "Sem o código de acesso."},
        403: {"description": "Papel diferente de Coordenação ou Direção."},
        404: {"description": "Projeto não encontrado."},
        422: {"description": "Parâmetros ausentes ou período inválido."},
    },
)
def gerar_prestacao_de_contas(
    request: Request,
    projeto_id: str = Query(..., min_length=1, description="Projeto do relatório."),
    data_inicio: date = Query(..., description="Início do período (AAAA-MM-DD)."),
    data_fim: date = Query(..., description="Fim do período (AAAA-MM-DD)."),
    formato: FormatoRelatorio = Query(FormatoRelatorio.PDF, description="pdf ou xlsx."),
    _papel: Papel = Depends(exigir_papel(Papel.COORDENACAO, Papel.DIRECAO)),
    repositorio=Depends(obter_repositorio),
) -> Response:
    projeto = buscar_projeto(projeto_id, repositorio)
    if projeto is None:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    try:
        relatorio = montar_relatorio(
            projeto,
            repositorio.listar_orcamentos(),
            data_inicio,
            data_fim,
            url_base=_url_base(request),
        )
    except RelatorioInvalido as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro

    gerar, content_type = _GERADORES[formato]
    nome = re.sub(r"[^A-Za-z0-9._-]", "-", nome_do_arquivo(relatorio, formato.value))
    return Response(
        content=gerar(relatorio),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{nome}"',
            # Dados financeiros: não guardar em cache de navegador nem de proxy.
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
