"""Entrada única da API publicada no Cloud Run."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from Financeiro.routers.comprovantes import router as comprovantes_router
from Financeiro.routers.lancamentos import router as lancamentos_router
from Financeiro.routers.notificacoes import router as notificacoes_router
from Financeiro.routers.orcamentos import router as orcamentos_router
from Shared.infra_api import router as infra_router

app = FastAPI(title="API — Plataforma MDCA")
app.include_router(infra_router)
app.include_router(orcamentos_router)
app.include_router(comprovantes_router)
app.include_router(lancamentos_router)
app.include_router(notificacoes_router)
origins = [origin.strip() for origin in os.getenv(
    "CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080"
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Papel-Usuario", "X-Usuario-Id"],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
