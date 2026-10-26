from fastapi import FastAPI

if __package__:
    from .routers.comprovantes import router as comprovantes_router
    from .routers.lancamentos import router as lancamentos_router
    from .routers.orcamentos import router as orcamentos_router
else:
    from routers.comprovantes import router as comprovantes_router
    from routers.lancamentos import router as lancamentos_router
    from routers.orcamentos import router as orcamentos_router

app = FastAPI(title="MDCA — Financeiro")
app.include_router(orcamentos_router)
app.include_router(comprovantes_router)
app.include_router(lancamentos_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
