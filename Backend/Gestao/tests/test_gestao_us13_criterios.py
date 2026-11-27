"""Critérios da US-13 na Gestão (T-81, testes da T-83): auditoria de dados sensíveis.

1. Abrir um registro sensível (cadastro, trajetória, chamada, alerta) gera um evento
   completo: quem, quando, operação e item consultado, sem nome de pessoa atendida.
2. Cada alteração da Gestão fica na trilha; o reenvio do mesmo encontro (fila offline)
   não duplica o evento.
3. O log não aceita edição nem exclusão.
4. Na consulta autorizada (``GET /auditoria``), os eventos da Gestão filtram por usuário,
   período e tipo, com o rótulo da ação.

Usa o cenário dos testes de alertas (``test_gestao_alertas``): p-1 (Semear) com a turma
t-1 (Lara, Davi e Nina), Jéssica educadora, Patrícia assistente social, Ana coordenação.
"""

import ast
from datetime import date, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from Gestao import auditoria
from test_gestao_alertas import ALERTAS, HOJE, P1, como, encontro, faltas_seguidas, programa  # noqa: F401 (fixture)

GESTAO = Path(__file__).resolve().parents[1]


def eventos(banco, acao=None):
    filtro, parametros = "", {}
    if acao:
        filtro, parametros = "AND acao = :acao", {"acao": acao}
    with banco.connect() as c:
        linhas = c.execute(
            sa.text(f"SELECT usuario_id, modulo, acao, alvo_tipo, alvo_id, descricao, detalhes, ocorrido_em FROM log_auditoria WHERE modulo = 'gestao' {filtro} ORDER BY id"),
            parametros,
        ).all()
    return [l._asdict() for l in linhas]


# --- 1. Leitura de registro sensível gera evento completo -----------------------------


@pytest.mark.parametrize(
    "rota, acao, alvo_tipo, alvo_id",
    [
        ("/gestao/pessoas/pe-lara", "consulta_pessoa", "pessoa", "pe-lara"),
        ("/gestao/pessoas/pe-lara/trajetoria", "consulta_trajetoria", "pessoa", "pe-lara"),
    ],
)
def test_abrir_cadastro_ou_trajetoria_gera_evento_completo(cliente, cabecalhos, programa, rota, acao, alvo_tipo, alvo_id):
    assert cliente.get(rota, headers=como(cabecalhos, "ana")).status_code == 200

    [evento] = eventos(programa, acao)
    assert evento["usuario_id"] == "ana"
    assert (evento["alvo_tipo"], evento["alvo_id"]) == (alvo_tipo, alvo_id)
    assert evento["detalhes"]["programa_id"] == "p-1"
    assert evento["ocorrido_em"] is not None
    # O detalhe diz o tipo e o programa, sem o nome da pessoa atendida.
    assert evento["descricao"] == "Pessoa atendida · Semear"
    assert "Lara" not in str(evento)


def test_abrir_a_chamada_de_um_encontro_gera_evento(cliente, cabecalhos, programa):
    atividade_id = encontro(cliente, cabecalhos, 1).json()["id"]

    assert cliente.get(f"{P1}/atividades/{atividade_id}", headers=como(cabecalhos, "ana")).status_code == 200

    [evento] = eventos(programa, "consulta_chamada")
    assert (evento["usuario_id"], evento["alvo_tipo"], evento["alvo_id"]) == ("ana", "atividade", atividade_id)
    assert evento["descricao"] == "Encontro · Semear"


def test_abrir_um_alerta_gera_evento(cliente, cabecalhos, programa):
    faltas_seguidas(cliente, cabecalhos)
    alerta_id = cliente.get(ALERTAS, headers=como(cabecalhos)).json()[0]["id"]

    assert cliente.get(f"{ALERTAS}/{alerta_id}", headers=como(cabecalhos)).status_code == 200

    [evento] = eventos(programa, "consulta_alerta")
    assert (evento["usuario_id"], evento["alvo_tipo"], evento["alvo_id"]) == ("patricia", "alerta", alerta_id)


def test_listas_nao_geram_evento_de_consulta(cliente, cabecalhos, programa):
    cliente.get("/gestao/pessoas", headers=como(cabecalhos, "ana"))
    cliente.get(f"{P1}/turmas", headers=como(cabecalhos, "ana"))

    assert eventos(programa) == []


def test_consulta_negada_gera_so_a_negacao(cliente, cabecalhos, programa):
    with programa.begin() as c:
        c.execute(sa.text("INSERT INTO usuarios (id, nome) VALUES ('zeca', 'Zeca Lima')"))

    assert cliente.get("/gestao/pessoas/pe-lara", headers=como(cabecalhos, "zeca")).status_code == 403

    assert [e["acao"] for e in eventos(programa)] == ["acesso_negado"]


# --- 2. Alterações ficam na trilha ------------------------------------------------------


def test_cadastros_e_alteracoes_ficam_na_trilha(cliente, cabecalhos, programa):
    ana = como(cabecalhos, "ana")
    assert cliente.post(f"{P1}/objetivos", json={"descricao": "Vínculos"}, headers=ana).status_code == 201
    turma = cliente.post(
        f"{P1}/turmas",
        json={"nome": "Música", "espaco_id": "e-1", "responsavel_id": "jessica", "capacidade": 10, "dias_semana": [2], "hora_inicio": "10:00", "hora_fim": "11:00"},
        headers=ana,
    )
    assert turma.status_code == 201, turma.text
    assert cliente.post(f"{P1}/turmas/{turma.json()['id']}/matriculas", json={"pessoa_id": "pe-davi"}, headers=ana).status_code == 201
    assert cliente.post(f"{P1}/espacos", json={"nome": "Quadra"}, headers=ana).status_code == 201

    acoes = [(e["usuario_id"], e["acao"], e["alvo_tipo"]) for e in eventos(programa)]
    assert acoes == [
        ("ana", "objetivo_cadastrado", "objetivo"),
        ("ana", "turma_cadastrada", "turma"),
        ("ana", "inscricao_registrada", "matricula"),
        ("ana", "espaco_cadastrado", "espaco"),
    ]
    inscricao = eventos(programa, "inscricao_registrada")[0]
    assert inscricao["detalhes"] == {"programa_id": "p-1", "turma_id": turma.json()["id"], "pessoa_id": "pe-davi", "situacao": "ativa"}


def test_encontro_registrado_uma_vez_mesmo_com_reenvio(cliente, cabecalhos, programa):
    encontro(cliente, cabecalhos, 1, registro_id="r-unico")
    encontro(cliente, cabecalhos, 1, registro_id="r-unico")

    [evento] = eventos(programa, "encontro_registrado")
    assert evento["usuario_id"] == "jessica"
    assert evento["detalhes"]["turma_id"] == "t-1"


def test_alteracao_que_falha_nao_deixa_evento(cliente, cabecalhos, programa):
    # Objetivo sem descrição: 400 (ou 422), e nada entra na trilha.
    resposta = cliente.post(f"{P1}/objetivos", json={"descricao": " "}, headers=como(cabecalhos, "ana"))

    assert resposta.status_code in (400, 422)
    assert eventos(programa, "objetivo_cadastrado") == []


# --- 3. Log imutável ---------------------------------------------------------------------


@pytest.mark.parametrize("comando", ["UPDATE log_auditoria SET usuario_id = 'outra-pessoa'", "DELETE FROM log_auditoria"])
def test_o_log_nao_aceita_edicao_nem_exclusao(cliente, cabecalhos, programa, comando):
    cliente.get("/gestao/pessoas/pe-lara", headers=como(cabecalhos, "ana"))

    with pytest.raises(DBAPIError, match="apenas inclus"):
        with programa.begin() as c:
            c.execute(sa.text(comando))
    assert [e["usuario_id"] for e in eventos(programa)] == ["ana"]


# --- 4. Filtros da consulta autorizada ----------------------------------------------------


def ler_auditoria(cliente, cabecalhos, **params):
    resposta = cliente.get("/auditoria", params=params, headers={**como(cabecalhos, "ana"), "X-Papel-Usuario": "coordenacao"})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["itens"]


def test_filtros_por_usuario_tipo_e_periodo(cliente, cabecalhos, programa):
    cliente.get("/gestao/pessoas/pe-lara", headers=como(cabecalhos, "ana"))
    cliente.get("/gestao/pessoas/pe-davi", headers=como(cabecalhos, "patricia"))
    cliente.post(f"{P1}/objetivos", json={"descricao": "Vínculos"}, headers=como(cabecalhos, "ana"))

    por_usuario = ler_auditoria(cliente, cabecalhos, modulo="gestao", usuario_id="patricia")
    assert [(i["codigo"], i["alvo_id"]) for i in por_usuario] == [("consulta_pessoa", "pe-davi")]

    por_tipo = ler_auditoria(cliente, cabecalhos, modulo="gestao", acao="consulta_pessoa")
    assert {i["alvo_id"] for i in por_tipo} == {"pe-lara", "pe-davi"}
    assert {i["acao"] for i in por_tipo} == {"Consultou cadastro de pessoa atendida"}

    combinados = ler_auditoria(cliente, cabecalhos, modulo="gestao", usuario_id="ana", acao="objetivo_cadastrado", desde=HOJE.isoformat(), ate=HOJE.isoformat())
    assert [i["acao"] for i in combinados] == ["Cadastrou objetivo do plano"]

    amanha = (HOJE + timedelta(days=1)).isoformat()
    assert ler_auditoria(cliente, cabecalhos, modulo="gestao", desde=amanha) == []


# --- Toda ação da Gestão tem rótulo -----------------------------------------------------


def acoes_gravadas_no_codigo():
    """Códigos passados em ``acao=`` nas chamadas a ``auditoria.registrar*`` da Gestão."""
    codigos = set()
    for arquivo in GESTAO.rglob("*.py"):
        if "tests" in arquivo.parts:
            continue
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Call) and getattr(no.func, "attr", "") in {"registrar", "registrar_evento"}:
                for kw in no.keywords:
                    if kw.arg != "acao":
                        continue
                    if isinstance(kw.value, ast.Constant):
                        codigos.add(kw.value.value)
                    elif isinstance(kw.value, ast.Attribute) and isinstance(kw.value.value, ast.Name) and kw.value.value.id == "auditoria":
                        codigos.add(getattr(auditoria, kw.value.attr))
                    elif isinstance(kw.value, ast.Name) and kw.value.id.isupper():
                        # Constante do próprio arquivo (ex.: ACAO_DE_BUSCA_ATIVA); a variável
                        # ``acao`` repassada dentro de ``registrar_evento`` não é um código.
                        codigos.add(kw.value.id)
    return codigos


def test_toda_acao_gravada_pela_gestao_tem_rotulo_na_tela_de_auditoria():
    from Financeiro.auditoria import rotulo

    codigos = acoes_gravadas_no_codigo()
    # Constantes de módulo usadas pelo nome (ex.: ACAO_DE_BUSCA_ATIVA) viram o valor delas.
    resolvidos = set()
    for codigo in codigos:
        if codigo.isupper():
            for arquivo in GESTAO.rglob("*.py"):
                texto = arquivo.read_text(encoding="utf-8")
                for linha in texto.splitlines():
                    if linha.startswith(f"{codigo} = "):
                        resolvidos.add(ast.literal_eval(linha.split(" = ", 1)[1]))
        else:
            resolvidos.add(codigo)
    assert len(resolvidos) > 20
    sem_rotulo = sorted(c for c in resolvidos if rotulo(c, "gestao") == c)
    assert sem_rotulo == []
