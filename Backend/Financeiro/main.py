from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

if __package__:
    from .routers.comprovantes import router as comprovantes_router
    from .routers.lancamentos import router as lancamentos_router
    from .routers.notificacoes import router as notificacoes_router
    from .routers.orcamentos import router as orcamentos_router
    from .routers.projetos import router as projetos_router
    from .routers.rascunhos import router as rascunhos_router
else:
    from routers.comprovantes import router as comprovantes_router
    from routers.lancamentos import router as lancamentos_router
    from routers.notificacoes import router as notificacoes_router
    from routers.orcamentos import router as orcamentos_router
    from routers.projetos import router as projetos_router
    from routers.rascunhos import router as rascunhos_router

app = FastAPI(title="MDCA — Financeiro")


@app.exception_handler(RequestValidationError)
async def erro_de_validacao(_request: Request, erro: RequestValidationError):
    # Sem o "input" ecoado: NaN/Infinity não serializam em JSON e davam 500.
    detalhes = [{k: v for k, v in e.items() if k not in ("input", "ctx")} for e in erro.errors()]
    return JSONResponse(status_code=422, content={"detail": detalhes})


app.include_router(orcamentos_router)
app.include_router(comprovantes_router)
app.include_router(lancamentos_router)
app.include_router(notificacoes_router)
app.include_router(rascunhos_router)
app.include_router(projetos_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
