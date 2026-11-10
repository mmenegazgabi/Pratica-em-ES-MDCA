"""A matriz de permissões (docs/permissoes-gestao.md, T-42) acompanha o acesso.py.

Se uma regra de papel mudar no código, este teste falha até o documento ser atualizado.
Não usa banco.
"""

import ast
import re
from pathlib import Path

import pytest

from Gestao import acesso

RAIZ = Path(__file__).resolve().parents[3]
DOCUMENTO = RAIZ / "docs" / "permissoes-gestao.md"
MIGRATION_PAPEIS = (
    RAIZ / "Backend" / "Shared" / "migrations" / "versions"
    / "9409373416eb_create_usuarios_papeis_and_log_auditoria.py"
)

PAPEIS_DE_GESTAO = {"coordenacao", "educador", "assistente_social", "psicologo", "direcao", "administracao"}


def conjuntos_do_documento():
    texto = DOCUMENTO.read_text(encoding="utf-8")
    secao = texto.split("## Fonte no código", 1)[1]
    bloco = re.search(r"```python\n(.*?)```", secao, re.S).group(1)
    return {
        alvo.id: ast.literal_eval(no.value)
        for no in ast.parse(bloco).body
        for alvo in no.targets
    }


def conjuntos_do_codigo():
    return {
        nome: valor
        for nome, valor in vars(acesso).items()
        if nome.startswith("PAPEIS_") and isinstance(valor, (set, frozenset))
    }


def test_documento_lista_todos_os_conjuntos_de_papeis_do_acesso():
    assert set(conjuntos_do_documento()) == set(conjuntos_do_codigo())


@pytest.mark.parametrize("nome", sorted(conjuntos_do_codigo()))
def test_cada_conjunto_do_documento_e_igual_ao_do_codigo(nome):
    assert conjuntos_do_documento()[nome] == set(conjuntos_do_codigo()[nome])


def test_documento_cobre_os_seis_papeis_de_gestao_do_catalogo():
    texto = DOCUMENTO.read_text(encoding="utf-8")
    catalogo = set(re.findall(r'\{"id": "(\w+)"', MIGRATION_PAPEIS.read_text(encoding="utf-8")))

    assert PAPEIS_DE_GESTAO <= catalogo
    for papel in PAPEIS_DE_GESTAO:
        assert f"`{papel}`" in texto, papel
