"""T-25 · US-06 — GET /relatorios/prestacao-contas (projeto + período, PDF ou XLSX)."""

import io
from datetime import date

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pypdf import PdfReader

from Financeiro.comprovantes import TIPOS_ACEITOS, gerar_chave
from Financeiro.main import app
from Financeiro.orcamento import Lancamento, Orcamento, StatusLancamento
from Financeiro.projetos import _projetos, registrar_projeto
from Financeiro.relatorio_prestacao import CONTENT_TYPE_PDF, CONTENT_TYPE_XLSX, SEM_LANCAMENTOS
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-123"
ROTA = "/relatorios/prestacao-contas"
PERIODO = {"data_inicio": "2026-01-01", "data_fim": "2026-06-30"}

client = TestClient(app)


def cabecalhos(papel="coordenacao"):
    return {"Authorization": f"Bearer {TOKEN}", "X-Papel-Usuario": papel}


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("FINANCEIRO_API_TOKEN", TOKEN)
    monkeypatch.delenv("FINANCEIRO_URL_PUBLICA", raising=False)
    _orcamentos.clear()
    _projetos.clear()
    yield
    _orcamentos.clear()
    _projetos.clear()


def aprovado(valor, dia, descricao):
    return Lancamento(
        valor=valor,
        status=StatusLancamento.APROVADO,
        data_despesa=dia,
        categoria="Alimentação",
        descricao=descricao,
        comprovante_chave=gerar_chave(TIPOS_ACEITOS["jpg"]),
    )


@pytest.fixture
def semear():
    projeto = registrar_projeto("Semear")
    _orcamentos.append(
        Orcamento(
            id="o-semear",
            projeto_id=projeto.id,
            valor_total=15000,
            data_inicio=date(2026, 1, 1),
            data_fim=date(2026, 12, 31),
            categorias_despesa=["Alimentação"],
            lancamentos=[
                aprovado(486.9, date(2026, 3, 12), "Lanche da oficina"),
                aprovado(1200, date(2026, 4, 2), "Fretamento"),
                aprovado(50, date(2026, 9, 1), "Fora do período"),
            ],
        )
    )
    return projeto


def pedir(projeto_id, papel="coordenacao", **params):
    return client.get(ROTA, params={"projeto_id": projeto_id, **PERIODO, **params}, headers=cabecalhos(papel))


def texto_do_pdf(conteudo):
    return "".join(p.extract_text() for p in PdfReader(io.BytesIO(conteudo)).pages)


def celulas_do_xlsx(conteudo):
    ws = load_workbook(io.BytesIO(conteudo)).active
    return [c.value for linha in ws.iter_rows() for c in linha if c.value is not None]


# --- Critério 1: projeto e período válidos → arquivo no formato pedido --------


def test_formato_pdf_devolve_o_arquivo_pdf(semear):
    resposta = pedir(semear.id, formato="pdf")

    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == CONTENT_TYPE_PDF
    assert resposta.content.startswith(b"%PDF-")
    assert resposta.headers["content-disposition"] == (
        'attachment; filename="prestacao-contas_semear_2026-01-01_2026-06-30.pdf"'
    )
    texto = texto_do_pdf(resposta.content)
    assert "Semear" in texto
    assert "Lanche da oficina" in texto and "Fretamento" in texto
    assert "Fora do período" not in texto
    assert "R$ 1.686,90" in texto  # realizado no período


def test_formato_xlsx_devolve_a_planilha(semear):
    resposta = pedir(semear.id, formato="xlsx")

    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == CONTENT_TYPE_XLSX
    assert resposta.content.startswith(b"PK")  # XLSX é um arquivo zip
    assert resposta.headers["content-disposition"].endswith('_2026-01-01_2026-06-30.xlsx"')
    celulas = celulas_do_xlsx(resposta.content)
    assert "Semear" in celulas
    assert "Lanche da oficina" in celulas and "Fretamento" in celulas
    assert "Fora do período" not in celulas
    assert 1686.9 in celulas


def test_sem_formato_o_padrao_e_pdf(semear):
    resposta = pedir(semear.id)
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == CONTENT_TYPE_PDF


def test_formato_desconhecido_e_recusado(semear):
    assert pedir(semear.id, formato="docx").status_code == 422


def test_resposta_nao_fica_em_cache(semear):
    resposta = pedir(semear.id)
    assert resposta.headers["cache-control"] == "no-store"
    assert resposta.headers["x-content-type-options"] == "nosniff"


def test_link_do_comprovante_usa_o_endereco_da_api(semear):
    chave = _orcamentos[0].lancamentos[0].comprovante_chave

    padrao = celulas_do_xlsx(pedir(semear.id, formato="xlsx").content)
    assert f"http://testserver/{chave}" in padrao

    atras_do_https = client.get(
        ROTA,
        params={"projeto_id": semear.id, **PERIODO, "formato": "xlsx"},
        headers={**cabecalhos(), "X-Forwarded-Proto": "https"},
    )
    assert f"https://testserver/{chave}" in celulas_do_xlsx(atras_do_https.content)


def test_endereco_publico_configurado_tem_prioridade(semear, monkeypatch):
    monkeypatch.setenv("FINANCEIRO_URL_PUBLICA", "https://api.mdca.org")
    chave = _orcamentos[0].lancamentos[0].comprovante_chave

    celulas = celulas_do_xlsx(pedir(semear.id, formato="xlsx").content)
    assert f"https://api.mdca.org/{chave}" in celulas


def test_projeto_inexistente_404():
    resposta = pedir("nao-existe")
    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Projeto não encontrado."


def test_periodo_invertido_422(semear):
    resposta = client.get(
        ROTA,
        params={"projeto_id": semear.id, "data_inicio": "2026-06-30", "data_fim": "2026-01-01"},
        headers=cabecalhos(),
    )
    assert resposta.status_code == 422
    assert "antes do início" in resposta.json()["detail"]


@pytest.mark.parametrize("falta", ["projeto_id", "data_inicio", "data_fim"])
def test_parametro_obrigatorio_ausente_422(semear, falta):
    params = {"projeto_id": semear.id, **PERIODO}
    del params[falta]
    assert client.get(ROTA, params=params, headers=cabecalhos()).status_code == 422


def test_data_em_formato_errado_422(semear):
    params = {"projeto_id": semear.id, "data_inicio": "01/01/2026", "data_fim": "2026-06-30"}
    assert client.get(ROTA, params=params, headers=cabecalhos()).status_code == 422


# --- Critério 2: projeto sem lançamentos no período → relatório vazio, sem erro --


@pytest.mark.parametrize("formato", ["pdf", "xlsx"])
def test_periodo_sem_lancamentos_gera_relatorio_vazio(semear, formato):
    resposta = client.get(
        ROTA,
        params={"projeto_id": semear.id, "data_inicio": "2026-05-01", "data_fim": "2026-05-31", "formato": formato},
        headers=cabecalhos(),
    )

    assert resposta.status_code == 200
    if formato == "pdf":
        texto = texto_do_pdf(resposta.content)
        assert SEM_LANCAMENTOS in texto
        assert "R$ 15.000,00" in texto  # orçado continua aparecendo
        assert "R$ 0,00" in texto  # realizado zero
    else:
        celulas = celulas_do_xlsx(resposta.content)
        assert SEM_LANCAMENTOS in celulas
        assert 15000 in celulas and 0 in celulas


@pytest.mark.parametrize("formato", ["pdf", "xlsx"])
def test_projeto_sem_orcamento_tambem_gera_relatorio_vazio(formato):
    novo = registrar_projeto("Projeto novo")
    resposta = pedir(novo.id, formato=formato)

    assert resposta.status_code == 200
    conteudo = texto_do_pdf(resposta.content) if formato == "pdf" else " ".join(map(str, celulas_do_xlsx(resposta.content)))
    assert SEM_LANCAMENTOS in conteudo
    assert "Projeto novo" in conteudo


# --- Critério 3: fora de Coordenação/Direção → 403 ---------------------------------


@pytest.mark.parametrize("papel", ["coordenacao", "direcao"])
@pytest.mark.parametrize("formato", ["pdf", "xlsx"])
def test_coordenacao_e_direcao_podem_gerar(semear, papel, formato):
    assert pedir(semear.id, papel=papel, formato=formato).status_code == 200


@pytest.mark.parametrize("papel", ["educador", "voluntario_financeiro", "", "admin", "COORDENACAO-falso"])
@pytest.mark.parametrize("formato", ["pdf", "xlsx"])
def test_outros_papeis_recebem_403_sem_arquivo(semear, papel, formato):
    resposta = pedir(semear.id, papel=papel, formato=formato)

    assert resposta.status_code == 403
    assert resposta.headers["content-type"].startswith("application/json")
    assert "coordenacao, direcao" in resposta.json()["detail"]


def test_sem_cabecalho_de_papel_403(semear):
    resposta = client.get(ROTA, params={"projeto_id": semear.id, **PERIODO}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert resposta.status_code == 403


def test_papel_com_maiusculas_e_espacos_e_aceito(semear):
    assert pedir(semear.id, papel="  Direcao ").status_code == 200


def test_sem_codigo_de_acesso_401(semear):
    resposta = client.get(ROTA, params={"projeto_id": semear.id, **PERIODO}, headers={"X-Papel-Usuario": "coordenacao"})
    assert resposta.status_code == 401


def test_codigo_de_acesso_errado_401(semear):
    resposta = client.get(
        ROTA,
        params={"projeto_id": semear.id, **PERIODO},
        headers={"Authorization": "Bearer errado", "X-Papel-Usuario": "coordenacao"},
    )
    assert resposta.status_code == 401


def test_papel_sem_permissao_nao_descobre_se_o_projeto_existe():
    """403 vem antes do 404: quem não pode gerar não fica sabendo quais projetos existem."""
    assert pedir("nao-existe", papel="educador").status_code == 403
