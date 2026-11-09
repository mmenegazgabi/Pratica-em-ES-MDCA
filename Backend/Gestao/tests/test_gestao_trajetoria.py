"""Trajetória da pessoa atendida: linha do tempo vinda do cadastro (T-49 · US-03)."""

from datetime import date, timedelta

import pytest
import sqlalchemy as sa

HOJE = date.today()


@pytest.fixture
def programa(banco):
    """p-1 (Semear) com ana na coordenação; p-2 (Oficina) com bruno na coordenação."""
    with banco.begin() as c:
        c.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear'), ('p-2', 'Oficina')"))
        c.execute(sa.text("INSERT INTO usuarios (id, nome) VALUES ('ana', 'Ana'), ('bruno', 'Bruno')"))
        c.execute(
            sa.text(
                "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) VALUES "
                "('v1', 'ana', 'p-1', 'coordenacao', '2025-01-01'), ('v2', 'bruno', 'p-2', 'coordenacao', '2025-01-01')"
            )
        )
    return banco


def como(cabecalhos, usuario="ana"):
    return {**cabecalhos, "X-Usuario-Id": usuario}


def cadastrar_lara(cliente, cabecalhos):
    resposta = cliente.post(
        "/gestao/pessoas",
        json={
            "programa_id": "p-1",
            "nome": "Lara Oliveira",
            "data_nascimento": "2013-05-12",
            "nucleo_familiar_nome": "Oliveira",
            "responsaveis": [{"nome": "Marina Oliveira", "parentesco": "Mãe", "responsavel_legal": True}],
        },
        headers=como(cabecalhos),
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def trajetoria(cliente, cabecalhos, pessoa_id, usuario="ana"):
    resposta = cliente.get(f"/gestao/pessoas/{pessoa_id}/trajetoria", headers=como(cabecalhos, usuario))
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def test_logo_depois_do_cadastro_a_trajetoria_mostra_a_entrada_no_programa(cliente, cabecalhos, programa):
    pessoa_id = cadastrar_lara(cliente, cabecalhos)

    eventos = trajetoria(cliente, cabecalhos, pessoa_id)

    assert [(e["tipo"], e["titulo"], e["descricao"]) for e in eventos] == [
        ("cadastro", "Cadastro no programa Semear", "Núcleo familiar Oliveira.")
    ]


def test_responsavel_documento_e_autorizacao_entram_do_mais_recente_para_o_mais_antigo(cliente, cabecalhos, programa):
    pessoa_id = cadastrar_lara(cliente, cabecalhos)
    base = f"/gestao/pessoas/{pessoa_id}"
    assert cliente.post(f"{base}/responsaveis", json={"nome": "José Oliveira", "parentesco": "Avô"}, headers=como(cabecalhos)).status_code == 201
    assert cliente.post(f"{base}/documentos", json={"tipo": "Certidão de nascimento", "nome_arquivo": "certidao.pdf"}, headers=como(cabecalhos)).status_code == 201
    autorizacao = cliente.post(
        f"{base}/autorizacoes",
        json={"tipo": "uso_de_imagem", "valida_de": HOJE.isoformat(), "valida_ate": (HOJE + timedelta(days=365)).isoformat()},
        headers=como(cabecalhos),
    )
    assert autorizacao.status_code == 201
    assert cliente.post(f"{base}/autorizacoes/{autorizacao.json()['id']}/revogacao", headers=como(cabecalhos)).status_code == 200

    eventos = trajetoria(cliente, cabecalhos, pessoa_id)

    assert [e["titulo"] for e in eventos] == [
        "Autorização de uso de imagem revogada",
        "Autorização de uso de imagem registrada",
        "Documento registrado: Certidão de nascimento",
        "Responsável incluído",
        "Cadastro no programa Semear",
    ]
    assert eventos[3]["descricao"] == "José Oliveira (Avô)"
    datas = [e["data"] for e in eventos]
    assert datas == sorted(datas, reverse=True)


def test_autorizacao_vencida_aparece_no_dia_seguinte_ao_fim_da_validade(cliente, cabecalhos, programa):
    pessoa_id = cadastrar_lara(cliente, cabecalhos)
    fim = HOJE - timedelta(days=10)
    with programa.begin() as c:
        c.execute(
            sa.text(
                "INSERT INTO autorizacoes (id, pessoa_id, tipo, valida_de, valida_ate) "
                "VALUES ('au-1', :p, 'uso_de_imagem', :de, :ate)"
            ),
            {"p": pessoa_id, "de": fim - timedelta(days=365), "ate": fim},
        )

    vencida = next(e for e in trajetoria(cliente, cabecalhos, pessoa_id) if e["titulo"].endswith("vencida"))

    assert vencida["data"].startswith((fim + timedelta(days=1)).isoformat())
    assert fim.strftime("%d/%m/%Y") in vencida["descricao"]


def test_quem_nao_atua_no_programa_nao_ve_a_trajetoria(cliente, cabecalhos, programa):
    pessoa_id = cadastrar_lara(cliente, cabecalhos)

    resposta = cliente.get(f"/gestao/pessoas/{pessoa_id}/trajetoria", headers=como(cabecalhos, "bruno"))

    assert resposta.status_code == 403


def test_pessoa_inexistente_responde_404(cliente, cabecalhos, programa):
    resposta = cliente.get("/gestao/pessoas/nao-existe/trajetoria", headers=como(cabecalhos))

    assert resposta.status_code == 404
