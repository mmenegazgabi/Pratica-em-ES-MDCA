"""As rotas de Gestão são publicadas pela API integrada, junto com as do Financeiro."""


def test_rotas_de_gestao_aparecem_no_openapi_junto_com_as_do_financeiro(cliente):
    rotas = cliente.get("/openapi.json").json()["paths"]

    assert "/gestao/programas" in rotas
    assert "/gestao/programas/{programa_id}/painel" in rotas
    assert "/orcamentos" in rotas
    assert "/health" in rotas


def test_docs_da_api_integrada_disponivel(cliente):
    assert cliente.get("/docs").status_code == 200
