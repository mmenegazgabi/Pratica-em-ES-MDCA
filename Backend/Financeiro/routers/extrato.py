"""Extrato bancário (US-05).

POST /extrato   -> importa um CSV do banco (campo ``arquivo``)
GET  /extrato   -> itens do extrato, filtrando os que ainda não foram conciliados

A conciliação com um lançamento é feita em PATCH /lancamentos/{id}/conciliar. Os
itens ficam no repositório do Financeiro (tabela ``extrato_itens`` com banco).
"""

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

if __package__ == "routers":
    import auditoria
    from autenticacao import AcessoFinanceiro, Papel, exigir_acesso_financeiro, exigir_papel, obter_acesso
    from extrato import TAMANHO_MAXIMO_BYTES, ExtratoInvalido, ItemExtrato, ler_csv
    from persistencia import obter_repositorio
else:
    from .. import auditoria
    from ..autenticacao import AcessoFinanceiro, Papel, exigir_acesso_financeiro, exigir_papel, obter_acesso
    from ..extrato import TAMANHO_MAXIMO_BYTES, ExtratoInvalido, ItemExtrato, ler_csv
    from ..persistencia import obter_repositorio

router = APIRouter(
    prefix="/extrato", tags=["extrato"], dependencies=[Depends(exigir_acesso_financeiro)]
)


class ItemExtratoSaida(BaseModel):
    id: str
    data: date
    descricao: str
    valor: float
    importado_em: datetime
    conciliado_com: Optional[str]


class ExtratoImportado(BaseModel):
    importados: int
    ignorados_repetidos: int
    itens: List[ItemExtratoSaida]


def _saida(item: ItemExtrato) -> ItemExtratoSaida:
    return ItemExtratoSaida(
        id=item.id,
        data=item.data,
        descricao=item.descricao,
        valor=item.valor,
        importado_em=item.importado_em,
        conciliado_com=item.conciliado_com,
    )


def _quantos(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


@router.post("", response_model=ExtratoImportado, status_code=201)
async def importar_extrato(
    arquivo: Optional[UploadFile] = File(None),
    _papel: Papel = Depends(exigir_papel(Papel.VOLUNTARIO_FINANCEIRO, Papel.COORDENACAO)),
    repositorio=Depends(obter_repositorio),
    identidade: AcessoFinanceiro = Depends(obter_acesso),
) -> ExtratoImportado:
    if arquivo is None:
        raise HTTPException(status_code=400, detail="Envie o arquivo CSV do extrato.")
    conteudo = await arquivo.read(TAMANHO_MAXIMO_BYTES + 1)
    try:
        itens = ler_csv(conteudo)
    except ExtratoInvalido as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    guardados, repetidos = repositorio.importar_extrato(itens)
    if guardados:  # reimportar o mesmo arquivo não muda nada nem gera registro
        auditoria.registrar(
            repositorio,
            identidade,
            "importar_extrato",
            alvo_tipo="extrato",
            descricao=auditoria.alvo(
                _quantos(len(guardados), "item novo", "itens novos"),
                _quantos(repetidos, "repetido", "repetidos") if repetidos else None,
            ),
            detalhes={"importados": len(guardados), "ignorados_repetidos": repetidos},
        )
    repositorio.confirmar()
    return ExtratoImportado(
        importados=len(guardados),
        ignorados_repetidos=repetidos,
        itens=[_saida(i) for i in guardados],
    )


@router.get("", response_model=List[ItemExtratoSaida])
def listar_extrato(
    em_aberto: Optional[bool] = Query(
        None, description="true: só os não conciliados; false: só os conciliados."
    ),
    _papel: Papel = Depends(
        exigir_papel(Papel.VOLUNTARIO_FINANCEIRO, Papel.COORDENACAO, Papel.DIRECAO)
    ),
    repositorio=Depends(obter_repositorio),
) -> List[ItemExtratoSaida]:
    return [_saida(i) for i in repositorio.listar_extrato(em_aberto)]
