from fastapi import FastAPI

if __package__:
    from .routers.auditoria import router as auditoria_router
    from .routers.comprovantes import router as comprovantes_router
    from .routers.dashboard import router as dashboard_router
    from .routers.extrato import router as extrato_router
    from .routers.lancamentos import router as lancamentos_router
    from .routers.notificacoes import router as notificacoes_router
    from .routers.orcamentos import router as orcamentos_router
    from .routers.projetos import router as projetos_router
    from .routers.rascunhos import router as rascunhos_router
    from .routers.relatorios import router as relatorios_router
    from .validacao import registrar_erro_de_validacao
else:
    from routers.auditoria import router as auditoria_router
    from routers.comprovantes import router as comprovantes_router
    from routers.dashboard import router as dashboard_router
    from routers.extrato import router as extrato_router
    from routers.lancamentos import router as lancamentos_router
    from routers.notificacoes import router as notificacoes_router
    from routers.orcamentos import router as orcamentos_router
    from routers.projetos import router as projetos_router
    from routers.rascunhos import router as rascunhos_router
    from routers.relatorios import router as relatorios_router
    from validacao import registrar_erro_de_validacao

app = FastAPI(title="MDCA — Financeiro")
registrar_erro_de_validacao(app)

app.include_router(orcamentos_router)
app.include_router(comprovantes_router)
app.include_router(lancamentos_router)
app.include_router(notificacoes_router)
app.include_router(rascunhos_router)
app.include_router(projetos_router)
app.include_router(dashboard_router)
app.include_router(relatorios_router)
app.include_router(extrato_router)
app.include_router(auditoria_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
