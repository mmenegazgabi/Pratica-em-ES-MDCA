"""Fixtures comuns dos testes do Financeiro.

Os testes de rotas usam o armazenamento em memória, mesmo que a máquina tenha uma
``DATABASE_URL`` configurada: nada deles chega a um banco real. Os testes de
persistência no PostgreSQL ficam em ``test_persistencia_banco.py`` e usam um banco
descartável indicado por ``TEST_DATABASE_URL``.
"""

import pytest

from Financeiro.persistencia import VARIAVEL_ARMAZENAMENTO


@pytest.fixture(autouse=True)
def _financeiro_em_memoria(request, monkeypatch):
    if "banco_financeiro" in request.fixturenames:
        return
    monkeypatch.setenv(VARIAVEL_ARMAZENAMENTO, "memoria")
