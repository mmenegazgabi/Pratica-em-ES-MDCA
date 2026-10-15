"""Rotas de comprovantes (T-11 · US-03).

POST /comprovantes                      -> envia o arquivo para o bucket privado
GET  /comprovantes/{ano}/{mes}/{arquivo} -> devolve o arquivo pela API

As duas rotas exigem autenticação. Não existe URL pública do arquivo.
"""

import os
from functools import lru_cache

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

if __package__ == "routers":
    from autenticacao import exigir_autenticacao
    from comprovantes import (
        TAMANHO_MAXIMO_BYTES,
        ArmazenamentoComprovantes,
        ArmazenamentoR2,
        ComprovanteInvalido,
        chave_valida,
        gerar_chave,
        limpar_nome_original,
        validar_comprovante,
    )
else:
    from ..autenticacao import exigir_autenticacao
    from ..comprovantes import (
        TAMANHO_MAXIMO_BYTES,
        ArmazenamentoComprovantes,
        ArmazenamentoR2,
        ComprovanteInvalido,
        chave_valida,
        gerar_chave,
        limpar_nome_original,
        validar_comprovante,
    )

router = APIRouter(
    prefix="/comprovantes",
    tags=["comprovantes"],
    dependencies=[Depends(exigir_autenticacao)],
)

_VARIAVEIS_R2 = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME")


class ComprovanteEnviado(BaseModel):
    chave: str
    url: str
    nome_original: str
    content_type: str
    tamanho: int


@lru_cache(maxsize=1)
def _armazenamento_r2() -> ArmazenamentoR2:
    return ArmazenamentoR2()


def obter_armazenamento() -> ArmazenamentoComprovantes:
    if any(not os.getenv(nome) for nome in _VARIAVEIS_R2):
        raise HTTPException(status_code=503, detail="Armazenamento não configurado.")
    return _armazenamento_r2()


@router.post("", response_model=ComprovanteEnviado, status_code=201)
async def enviar_comprovante(
    arquivo: UploadFile = File(...),
    armazenamento: ArmazenamentoComprovantes = Depends(obter_armazenamento),
) -> ComprovanteEnviado:
    # Lê no máximo 1 byte além do limite, para recusar arquivos grandes
    # sem carregar tudo na memória.
    conteudo = await arquivo.read(TAMANHO_MAXIMO_BYTES + 1)
    try:
        tipo = validar_comprovante(conteudo)
    except ComprovanteInvalido as erro:
        status = 413 if len(conteudo) > TAMANHO_MAXIMO_BYTES else 400
        raise HTTPException(status_code=status, detail=str(erro)) from erro

    chave = gerar_chave(tipo)
    nome_original = limpar_nome_original(arquivo.filename)
    try:
        armazenamento.salvar(chave, conteudo, tipo.content_type, nome_original)
    except Exception as erro:
        raise HTTPException(
            status_code=503, detail="Falha ao salvar o comprovante."
        ) from erro

    return ComprovanteEnviado(
        chave=chave,
        url=f"/{chave}",
        nome_original=nome_original,
        content_type=tipo.content_type,
        tamanho=len(conteudo),
    )


@router.get("/{ano}/{mes}/{arquivo}")
def baixar_comprovante(
    ano: str,
    mes: str,
    arquivo: str,
    armazenamento: ArmazenamentoComprovantes = Depends(obter_armazenamento),
) -> Response:
    chave = f"comprovantes/{ano}/{mes}/{arquivo}"
    if not chave_valida(chave):
        raise HTTPException(status_code=404, detail="Comprovante não encontrado.")

    try:
        armazenado = armazenamento.ler(chave)
    except Exception as erro:
        raise HTTPException(
            status_code=503, detail="Falha ao ler o comprovante."
        ) from erro
    if armazenado is None:
        raise HTTPException(status_code=404, detail="Comprovante não encontrado.")

    return Response(
        content=armazenado.conteudo,
        media_type=armazenado.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": (
                f'inline; filename="{limpar_nome_original(armazenado.nome_original)}"'
            ),
        },
    )
