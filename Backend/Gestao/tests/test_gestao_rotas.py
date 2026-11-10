"""As rotas de Gestão são publicadas pela API integrada, junto com as do Financeiro."""


def test_rotas_de_gestao_aparecem_no_openapi_junto_com_as_do_financeiro(cliente):
    rotas = cliente.get("/openapi.json").json()["paths"]

    assert "/gestao/programas" in rotas
    assert "/gestao/programas/{programa_id}/painel" in rotas
    assert "/gestao/programas/{programa_id}/equipe" in rotas
    assert "/gestao/programas/{programa_id}/equipe/{vinculo_id}/desligamento" in rotas
    assert "/gestao/programas/{programa_id}/espacos" in rotas
    assert "/gestao/usuarios" in rotas
    assert "/gestao/papeis" in rotas
    assert "/gestao/pessoas" in rotas
    assert "/gestao/pessoas/{pessoa_id}" in rotas
    assert "/gestao/pessoas/uso-de-imagem" in rotas
    assert "/gestao/programas/{programa_id}/turmas" in rotas
    assert "/gestao/programas/{programa_id}/turmas/{turma_id}/lista-de-espera/chamada" in rotas
    assert "/gestao/programas/{programa_id}/agenda" in rotas
    assert "/gestao/programas/{programa_id}/turmas/{turma_id}/atividades" in rotas
    assert "/gestao/programas/{programa_id}/atividades/{atividade_id}/evidencias" in rotas
    assert "/gestao/programas/{programa_id}/evidencias/{evidencia_id}/arquivo" in rotas
    assert "/gestao/alertas" in rotas
    assert "/gestao/alertas/{alerta_id}/acoes" in rotas
    assert "/gestao/alertas/{alerta_id}/encerramento" in rotas
    assert "/orcamentos" in rotas
    assert "/health" in rotas


def test_docs_da_api_integrada_disponivel(cliente):
    assert cliente.get("/docs").status_code == 200
