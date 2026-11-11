"""Acesso ao PostgreSQL do Módulo de Gestão.

A conexão é a mesma do Financeiro e do login único: vem de ``Shared/banco.py``. Este
módulo só reexporta os nomes que as rotas e os testes da Gestão já usam.

As rotas recebem a conexão por ``Depends(obter_conexao)``. Sem banco configurado ou
acessível, respondem 503, como o ``/db/health``.
"""

from Shared.banco import BANCO_INDISPONIVEL, _motor, obter_conexao, url_sqlalchemy

__all__ = ["BANCO_INDISPONIVEL", "_motor", "obter_conexao", "url_sqlalchemy"]
