from fastapi import FastAPI

from routers.orcamentos import router as orcamentos_router

app = FastAPI(title="MDCA — Financeiro")
app.include_router(orcamentos_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
