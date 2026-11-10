"""Entrada única da API publicada no Cloud Run."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from Acesso.routers.admin import router as admin_router
from Acesso.routers.auth import router as auth_router
from Financeiro.routers.auditoria import router as auditoria_financeiro_router
from Financeiro.routers.comprovantes import router as comprovantes_router
from Financeiro.routers.dashboard import router as dashboard_router
from Financeiro.routers.lancamentos import router as lancamentos_router
from Financeiro.routers.notificacoes import router as notificacoes_router
from Financeiro.routers.orcamentos import router as orcamentos_router
from Financeiro.routers.projetos import router as projetos_router
from Financeiro.routers.rascunhos import router as rascunhos_router
from Financeiro.routers.relatorios import router as relatorios_router
from Financeiro.validacao import registrar_erro_de_validacao
from Gestao.routers import router as gestao_router
from Shared.infra_api import router as infra_router

app = FastAPI(title="API — Plataforma MDCA")
registrar_erro_de_validacao(app)
app.include_router(infra_router)
app.include_router(orcamentos_router)
app.include_router(comprovantes_router)
app.include_router(lancamentos_router)
app.include_router(notificacoes_router)
app.include_router(rascunhos_router)
app.include_router(projetos_router)
app.include_router(dashboard_router)
app.include_router(relatorios_router)
app.include_router(auditoria_financeiro_router)
app.include_router(gestao_router)
app.include_router(auth_router)
app.include_router(admin_router)
origins = [origin.strip() for origin in os.getenv(
    "CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080"
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Papel-Usuario", "X-Usuario-Id"],
    # T-25: a tela de relatórios lê o nome do arquivo baixado.
    expose_headers=["Content-Disposition"],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
