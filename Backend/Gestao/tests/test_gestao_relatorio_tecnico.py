"""Relatório técnico (T-75 · US-11), com os critérios da T-77.

1. Conteúdo consolidado: plano, pessoas, atividades, indicadores e evidências.
2. Pendências listadas antes da versão final.
3. Circulação externa sem dados pessoais identificáveis.
4. PDF e XLSX com os mesmos dados.
5. Quem emite e o histórico das emissões.

Usa os dados de setembro de 2026 dos testes de indicadores (``test_gestao_indicadores``).
"""

import json

import pytest
import sqlalchemy as sa

from Shared.relatorios import ler_pdf, ler_xlsx
from test_gestao_indicadores import NOMES, com_pendencias, como, dados  # noqa: F401 (fixtures)

PREVIA = "/gestao/relatorios-tecnicos/previa"
EXPORTACAO = "/gestao/relatorios-tecnicos/exportacao"
EMISSOES = "/gestao/relatorios-tecnicos/emissoes"
TODAS = ["plano", "pessoas", "atividades", "indicadores", "evidencias", "financeiro"]


@pytest.fixture
def relatorio(com_pendencias):
    """Sobre as pendências de setembro: o encontro de 02/09 cita a Lara no conteúdo, e o de
    16/09 (só a Lara, ausente; ninguém presente) ganha uma evidência que pode circular."""
    with com_pendencias.begin() as c:
        c.execute(sa.text("UPDATE atividades SET conteudo = 'Lara apresentou o desenho da família' WHERE id = 'a-1'"))
        c.execute(
            sa.text(
                "INSERT INTO evidencias (id, registro_id, atividade_id, programa_id, autor_id, data, descricao, chave_arquivo, nome_arquivo, content_type, tamanho) "
                "VALUES ('ev-2', 'ev-2', 'a-3', 'p-1', 'jessica', '2026-09-16', 'Mural da turma', 'gestao/evidencias/ev-2', 'mural.jpg', 'image/jpeg', 10)"
            )
        )
        c.execute(sa.text("UPDATE evidencias SET descricao = 'Lara e Davi no ateliê', nome_arquivo = 'lara-davi.jpg' WHERE id = 'ev-1'"))
    return com_pendencias


def pedido(finalidade="interna", secoes=TODAS, **extra):
    return {"programa_id": "p-1", "inicio": "2026-09-01", "fim": "2026-09-30", "finalidade": finalidade, "secoes": secoes, **extra}


def previa(cliente, cabecalhos, usuario="ana", **kwargs):
    resposta = cliente.post(PREVIA, json=pedido(**kwargs), headers=como(cabecalhos, usuario))
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def secao(corpo, titulo):
    return next(s for s in corpo["conteudo"] if s["titulo"] == titulo)


# --- 1. Conteúdo consolidado ---------------------------------------------------------


def test_consulta_interna_consolida_todas_as_secoes(cliente, cabecalhos, relatorio):
    corpo = previa(cliente, cabecalhos)

    assert corpo["secoes"] == TODAS
    assert [s["titulo"] for s in corpo["conteudo"]] == [
        "Objetivos, ações e resultados", "Pessoas atendidas", "Atividades e frequência", "Indicadores", "Evidências", "Execução física e financeira",
    ]
    assert ["Programa", "Semear (SEMEAR)"] in corpo["cabecalho"]
    assert ["Finalidade", "Consulta interna"] in corpo["cabecalho"]
    # Famílias: 10 em setembro, 20 até 30/09 de 40 (50%).
    assert secao(corpo, "Objetivos, ações e resultados")["linhas"][1] == [
        "Vínculos", "Encontros com famílias", "Famílias participando", "Famílias", "40 famílias", "10 famílias", "20 famílias", "50%",
    ]
    assert secao(corpo, "Pessoas atendidas")["linhas"] == [
        ["Davi Oliveira", "Oficina de arte", "1", "1", "50%"],
        ["Lara Oliveira", "Leitura, Oficina de arte", "2", "1", "66,7%"],
    ]
    assert secao(corpo, "Atividades e frequência")["linhas"][0] == ["02/09/2026", "Oficina de arte", "2", "0", "Lara apresentou o desenho da família"]
    assert ["Frequência", "60%"] in secao(corpo, "Indicadores")["linhas"]
    assert [l[2] for l in secao(corpo, "Evidências")["linhas"]] == ["lara-davi.jpg", "mural.jpg"]
    assert secao(corpo, "Execução física e financeira")["vazio"] == "O programa ainda não tem orçamento no Financeiro."


def test_so_as_secoes_e_evidencias_escolhidas(cliente, cabecalhos, relatorio):
    corpo = previa(cliente, cabecalhos, secoes=["evidencias", "plano"], evidencias=["ev-2"])

    assert corpo["secoes"] == ["plano", "evidencias"]
    assert [l[2] for l in secao(corpo, "Evidências")["linhas"]] == ["mural.jpg"]
    # A lista para escolher continua com todas as do período.
    assert [e["id"] for e in corpo["evidencias_disponiveis"]] == ["ev-1", "ev-2"]


@pytest.mark.parametrize(
    "extra, status",
    [({"secoes": []}, 400), ({"secoes": ["fofoca"]}, 400), ({"finalidade": "publica"}, 422), ({"inicio": "2026-09-30", "fim": "2026-09-01"}, 400)],
)
def test_pedido_invalido(cliente, cabecalhos, relatorio, extra, status):
    resposta = cliente.post(PREVIA, json={**pedido(), **extra}, headers=como(cabecalhos, "ana"))

    assert resposta.status_code == status


# --- 2. Pendências antes da versão final -----------------------------------------------


def test_pendencias_da_consulta_interna(cliente, cabecalhos, relatorio):
    pendencias = {p["tipo"]: p["quantidade"] for p in previa(cliente, cabecalhos)["pendencias"]}

    # Quartas sem registro em t-1 e t-2; só o encontro de 09/09 ficou sem evidência.
    assert pendencias == {"chamadas_sem_registro": 7, "encontros_sem_evidencia": 1}


def test_pendencias_da_circulacao_externa_incluem_autorizacoes_e_evidencias_barradas(cliente, cabecalhos, relatorio):
    pendencias = {p["tipo"]: p["quantidade"] for p in previa(cliente, cabecalhos, finalidade="externa")["pendencias"]}

    assert pendencias == {
        "chamadas_sem_registro": 7,
        "encontros_sem_evidencia": 1,
        # Lara vencida e Nina revogada.
        "autorizacoes_de_imagem_vencidas": 2,
        # A foto de 02/09 tem a Lara presente, sem autorização vigente.
        "evidencias_nao_liberadas": 1,
    }


def test_sem_evidencias_no_relatorio_nao_lista_pendencia_de_evidencia(cliente, cabecalhos, relatorio):
    tipos = {p["tipo"] for p in previa(cliente, cabecalhos, finalidade="externa", secoes=["indicadores"])["pendencias"]}

    assert tipos == {"chamadas_sem_registro", "autorizacoes_de_imagem_vencidas"}


# --- 3. Circulação externa sem dados pessoais ------------------------------------------


def test_circulacao_externa_nao_tem_dados_pessoais(cliente, cabecalhos, relatorio):
    corpo = previa(cliente, cabecalhos, finalidade="externa")
    texto = json.dumps(corpo["conteudo"], ensure_ascii=False)

    for nome in NOMES:
        assert nome.split()[0] not in texto
    assert "lara-davi.jpg" not in texto and "Mural da turma" not in texto
    assert secao(corpo, "Pessoas atendidas")["linhas"] == [
        ["Leitura", "1"],
        ["Oficina de arte", "2"],
        ["Total (sem repetir quem está em mais de uma turma)", "2"],
    ]
    assert secao(corpo, "Atividades e frequência")["colunas"] == ["Data", "Turma", "Presenças", "Ausências"]
    # Só a evidência liberada, sem descrição nem nome do arquivo.
    assert secao(corpo, "Evidências")["linhas"] == [["16/09/2026", "Leitura", "image/jpeg"]]
    assert ["Finalidade", "Circulação externa"] in corpo["cabecalho"]


@pytest.mark.parametrize("formato", ["pdf", "xlsx"])
def test_arquivo_externo_nao_tem_dados_pessoais(cliente, cabecalhos, relatorio, formato):
    resposta = cliente.post(f"{EXPORTACAO}?formato={formato}", json=pedido("externa"), headers=como(cabecalhos, "ana"))

    assert resposta.status_code == 200
    texto = ler_pdf(resposta.content) if formato == "pdf" else json.dumps(ler_xlsx(resposta.content), ensure_ascii=False)
    for nome in NOMES:
        assert nome.split()[0] not in texto


# --- 4. Paridade PDF e XLSX ------------------------------------------------------------


@pytest.mark.parametrize("finalidade", ["interna", "externa"])
def test_pdf_e_xlsx_tem_os_mesmos_dados_da_previa(cliente, cabecalhos, relatorio, finalidade):
    corpo = previa(cliente, cabecalhos, finalidade=finalidade)
    pdf = cliente.post(f"{EXPORTACAO}?formato=pdf", json=pedido(finalidade), headers=como(cabecalhos, "ana"))
    xlsx = cliente.post(f"{EXPORTACAO}?formato=xlsx", json=pedido(finalidade), headers=como(cabecalhos, "ana"))

    assert pdf.headers["content-type"] == "application/pdf"
    assert xlsx.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert 'filename="relatorio-tecnico-semear-01-09-2026-a-30-09-2026.pdf"' in pdf.headers["content-disposition"]
    celulas_xlsx = ler_xlsx(xlsx.content)
    palavras_pdf = set(ler_pdf(pdf.content).replace("\n", " ").split())
    # Toda linha das tabelas da prévia está no XLSX e todas as palavras dela, no PDF.
    for s in corpo["conteudo"]:
        for linha in s["linhas"]:
            assert [v for v in linha if v] in celulas_xlsx, linha
            for valor in linha:
                assert set(valor.split()) <= palavras_pdf, valor


# --- 5. Quem emite e histórico ---------------------------------------------------------


def test_direcao_emite_so_para_circulacao_externa(cliente, cabecalhos, relatorio):
    negado = cliente.post(PREVIA, json=pedido("interna"), headers=como(cabecalhos, "dora"))

    assert negado.status_code == 403
    assert "circulação externa" in negado.json()["detail"]
    corpo = previa(cliente, cabecalhos, "dora", finalidade="externa")
    assert corpo["finalidades_permitidas"] == ["externa"]
    with relatorio.connect() as c:
        assert c.execute(
            sa.text("SELECT usuario_id, detalhes->>'operacao' FROM log_auditoria WHERE acao = 'acesso_negado'")
        ).all() == [("dora", "relatorio_tecnico")]


@pytest.mark.parametrize("usuario", ["jessica", "zeca"])
def test_equipe_e_quem_nao_tem_papel_nao_emitem(cliente, cabecalhos, relatorio, usuario):
    assert cliente.post(PREVIA, json=pedido("externa"), headers=como(cabecalhos, usuario)).status_code == 403
    assert cliente.get(EMISSOES, headers=como(cabecalhos, usuario)).status_code == 403


def test_programa_que_nao_existe_recebe_404(cliente, cabecalhos, relatorio):
    resposta = cliente.post(PREVIA, json={**pedido(), "programa_id": "p-x"}, headers=como(cabecalhos, "ana"))

    assert resposta.status_code == 404


def test_previa_nao_entra_no_historico_e_exportacao_entra(cliente, cabecalhos, relatorio):
    previa(cliente, cabecalhos)
    assert cliente.get(EMISSOES, headers=como(cabecalhos, "ana")).json() == []

    cliente.post(f"{EXPORTACAO}?formato=xlsx", json=pedido("externa", secoes=["indicadores", "plano"]), headers=como(cabecalhos, "ana"))
    cliente.post(f"{EXPORTACAO}?formato=pdf", json=pedido("interna"), headers=como(cabecalhos, "ana"))

    historico = cliente.get(EMISSOES, headers=como(cabecalhos, "dora")).json()
    assert [(e["formato"], e["finalidade"], e["usuario"], e["programa"]) for e in historico] == [
        ("pdf", "interna", "Ana Martins", "Semear"),
        ("xlsx", "externa", "Ana Martins", "Semear"),
    ]
    assert historico[1]["secoes"] == ["plano", "indicadores"]
    assert (historico[1]["inicio"], historico[1]["fim"]) == ("2026-09-01", "2026-09-30")
    assert cliente.get(EMISSOES, params={"programa_id": "p-2"}, headers=como(cabecalhos, "ana")).json() == []
