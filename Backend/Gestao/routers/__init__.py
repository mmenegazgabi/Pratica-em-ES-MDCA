"""Todas as rotas de Gestão num router só.

``Backend/main.py`` inclui apenas este ``router``: uma rota nova de Gestão entra
aqui, sem mexer no arquivo de entrada compartilhado com o Financeiro.
"""

from fastapi import APIRouter

from Gestao.routers.equipe import router as equipe_router
from Gestao.routers.pessoas import router as pessoas_router
from Gestao.routers.programas import router as programas_router
from Gestao.routers.usuarios import router as usuarios_router

router = APIRouter()
router.include_router(programas_router)
router.include_router(equipe_router)
router.include_router(usuarios_router)
router.include_router(pessoas_router)
