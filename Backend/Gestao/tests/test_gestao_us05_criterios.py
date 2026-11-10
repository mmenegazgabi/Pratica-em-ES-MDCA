"""Critérios de aceitação da US-05 (T-58): chamada, registro offline e vínculo das evidências.

Os testes de cada rota ficam em ``test_gestao_atividades.py`` (T-56). Aqui cada critério
é verificado como um percurso completo, conferindo também o que ficou gravado no banco:

1. Encerrar a chamada grava todos os campos: data, turma, educador, conteúdo, quem
   esteve presente e quem faltou (com a justificativa).
2. Um registro feito sem conexão e sincronizado depois não duplica: nem no reenvio da
   fila inteira, nem quando a resposta se perdeu, nem com envios ao mesmo tempo.
3. A evidência fica ligada à atividade, ao programa, ao autor e à data, e o arquivo vai
   para o armazenamento (R2) com só os metadados no banco.

O envio offline segue o que a fila do aparelho faz (``Frontend/Gestao/base/fila.js``):
primeiro o encontro, depois cada evidência com o id que a API devolveu, todos com o
``registro_id`` gerado no aparelho.
"""

import threading
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.routers.comprovantes import obter_armazenamento

HOJE = date.today()
ONTEM = HOJE - timedelta(days=1)
SEMANA_PASSADA = HOJE - timedelta(days=7)

P1 = "/gestao/programas/p-1"
ENCONTROS_T1 = f"{P1}/turmas/t-1/atividades"
JPEG = b"\xff\xd8\xff\xe0" + b"foto do mural" * 20
PDF = b"%PDF-1.4\n" + b"lista de presenca" * 20


@pytest.fixture
def programa(banco):
    """p-1 com a turma t-1 (todos os dias) e três crianças matriculadas há um mês; p-2 com t-9.

    - jessica: educadora em p-1 (responsável da t-1)   - ana: coordenação em p-1
    - bruno: educador em p-2
    """
    inicio = HOJE - timedelta(days=30)
    with banco.begin() as c:
        c.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear'), ('p-2', 'Oficina')"))
        c.execute(
            sa.text("INSERT INTO usuarios (id, nome) VALUES ('jessica', 'Jéssica Almeida'), ('ana', 'Ana Martins'), ('bruno', 'Bruno Lima')")
        )
        c.execute(
            sa.text(
                "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) VALUES "
                "('v1', 'jessica', 'p-1', 'educador', :inicio), ('v2', 'ana', 'p-1', 'coordenacao', :inicio), "
                "('v3', 'bruno', 'p-2', 'educador', :inicio)"
            ),
            {"inicio": inicio},
        )
        c.execute(sa.text("INSERT INTO espacos (id, programa_id, nome) VALUES ('e-1', 'p-1', 'Ateliê'), ('e-9', 'p-2', 'Sala')"))
        c.execute(
            sa.text(
                """
                INSERT INTO turmas (id, programa_id, nome, espaco_id, responsavel_id, capacidade, dias_semana, hora_inicio, hora_fim) VALUES
                    ('t-1', 'p-1', 'Oficina de arte', 'e-1', 'jessica', 20, '{1,2,3,4,5,6,7}', '14:00', '16:00'),
                    ('t-9', 'p-2', 'Reforço', 'e-9', 'bruno', 10, '{2}', '08:00', '10:00')
                """
            )
        )
        c.execute(sa.text("INSERT INTO nucleos_familiares (id, nome) VALUES ('f-1', 'Oliveira')"))
        c.execute(
            sa.text(
                "INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id) "
                "VALUES (:id, :nome, lower(:nome), '2014-01-01', 'f-1', 'p-1')"
            ),
            [{"id": "pe-lara", "nome": "Lara Oliveira"}, {"id": "pe-davi", "nome": "Davi Oliveira"}, {"id": "pe-nina", "nome": "Nina Oliveira"}],
        )
        c.execute(
            sa.text(
                "INSERT INTO matriculas (id, turma_id, pessoa_id, situacao, data_entrada) VALUES "
                "('m-1', 't-1', 'pe-lara', 'ativa', :inicio), ('m-2', 't-1', 'pe-davi', 'ativa', :inicio), "
                "('m-3', 't-1', 'pe-nina', 'ativa', :inicio)"
            ),
            {"inicio": inicio},
        )
    return banco


@pytest.fixture
def armazenamento(app):
    memoria = ArmazenamentoEmMemoria()
    app.dependency_overrides[obter_armazenamento] = lambda: memoria
    yield memoria
    app.dependency_overrides.pop(obter_armazenamento, None)


def como(cabecalhos, usuario_id="jessica"):
    return {**cabecalhos, "X-Usuario-Id": usuario_id}


def chamada(registro_id="aparelho-7/enc-1", data=HOJE, **extra):
    """A chamada como a fila do aparelho envia (presencasParaApi, T-57)."""
    dados = {
        "registro_id": registro_id,
        "data": data.isoformat(),
        "conteudo": "Pintura com guache e roda de conversa",
        "observacao": None,
        "presencas": [
            {"pessoa_id": "pe-lara", "presente": True, "justificativa": None},
            {"pessoa_id": "pe-davi", "presente": False, "justificativa": "Consulta médica"},
            {"pessoa_id": "pe-nina", "presente": False, "justificativa": None},
        ],
    }
    return {**dados, **extra}


def enviar_encontro(cliente, cabecalhos, usuario="jessica", **extra):
    return cliente.post(ENCONTROS_T1, json=chamada(**extra), headers=como(cabecalhos, usuario))


def enviar_evidencia(cliente, cabecalhos, atividade_id, registro_id, conteudo=JPEG, nome="mural.jpg", usuario="jessica", **campos):
    return cliente.post(
        f"{P1}/atividades/{atividade_id}/evidencias",
        data={"registro_id": registro_id, **campos},
        files={"arquivo": (nome, conteudo, "application/octet-stream")},
        headers=como(cabecalhos, usuario),
    )


def sincronizar_fila(cliente, cabecalhos, encontro, evidencias):
    """O que a fila do aparelho faz ao sincronizar: o encontro e, com o id devolvido, cada evidência."""
    resposta = enviar_encontro(cliente, cabecalhos, **encontro)
    respostas = [resposta]
    for registro_id, conteudo, nome in evidencias:
        respostas.append(enviar_evidencia(cliente, cabecalhos, resposta.json()["id"], registro_id, conteudo, nome))
    return respostas


def linhas(banco, sql, **params):
    with banco.connect() as c:
        return [tuple(l) for l in c.execute(sa.text(sql), params)]


def contar(banco, tabela):
    return linhas(banco, f"SELECT count(*) FROM {tabela}")[0][0]


# --- 1. Encerrar a chamada grava todos os campos ---------------------------------------


def test_chamada_encerrada_grava_data_turma_educador_conteudo_presentes_e_ausentes(cliente, cabecalhos, programa):
    resposta = enviar_encontro(cliente, cabecalhos)

    assert resposta.status_code == 201
    atividade_id = resposta.json()["id"]
    assert linhas(
        programa,
        "SELECT registro_id, programa_id, turma_id, data, educador_id, conteudo, criado_por FROM atividades",
    ) == [("aparelho-7/enc-1", "p-1", "t-1", HOJE, "jessica", "Pintura com guache e roda de conversa", "jessica")]
    assert linhas(
        programa,
        "SELECT atividade_id, pessoa_id, presente, justificativa FROM chamadas ORDER BY pessoa_id",
    ) == [
        (atividade_id, "pe-davi", False, "Consulta médica"),
        (atividade_id, "pe-lara", True, None),
        (atividade_id, "pe-nina", False, None),
    ]


def test_o_que_foi_gravado_volta_igual_na_consulta_do_encontro(cliente, cabecalhos, programa):
    atividade_id = enviar_encontro(cliente, cabecalhos).json()["id"]

    detalhe = cliente.get(f"{P1}/atividades/{atividade_id}", headers=como(cabecalhos, "ana")).json()

    assert {k: detalhe[k] for k in ("data", "turma_id", "turma", "educador_id", "educador", "conteudo", "presentes", "ausentes")} == {
        "data": HOJE.isoformat(),
        "turma_id": "t-1",
        "turma": "Oficina de arte",
        "educador_id": "jessica",
        "educador": "Jéssica Almeida",
        "conteudo": "Pintura com guache e roda de conversa",
        "presentes": 1,
        "ausentes": 2,
    }
    assert [(p["pessoa"], p["presente"], p["justificativa"]) for p in detalhe["chamada"]] == [
        ("Davi Oliveira", False, "Consulta médica"),
        ("Lara Oliveira", True, None),
        ("Nina Oliveira", False, None),
    ]


def test_encontro_registrado_aparece_como_feito_na_agenda(cliente, cabecalhos, programa):
    atividade_id = enviar_encontro(cliente, cabecalhos).json()["id"]

    agenda = cliente.get(f"{P1}/agenda", params={"inicio": HOJE.isoformat()}, headers=como(cabecalhos)).json()

    assert [(e["turma_id"], e["atividades"]) for e in agenda] == [("t-1", [atividade_id])]


def test_chamada_recusada_nao_grava_nada_pela_metade(cliente, cabecalhos, programa):
    presencas = chamada()["presencas"] + [{"pessoa_id": "pe-de-fora", "presente": True, "justificativa": None}]

    resposta = enviar_encontro(cliente, cabecalhos, presencas=presencas)

    assert resposta.status_code == 400
    assert (contar(programa, "atividades"), contar(programa, "chamadas")) == (0, 0)


# --- 2. Registro offline sincronizado depois, sem duplicar ---------------------------


def test_encontro_feito_sem_conexao_e_sincronizado_dias_depois(cliente, cabecalhos, programa, armazenamento):
    # A educadora fez a chamada sem rede na semana passada; o aparelho só sincroniza hoje.
    encontro, evidencia = sincronizar_fila(
        cliente, cabecalhos, {"data": SEMANA_PASSADA}, [("aparelho-7/ev-1", JPEG, "mural.jpg")]
    )

    assert (encontro.status_code, evidencia.status_code) == (201, 201)
    assert linhas(programa, "SELECT data FROM atividades") == [(SEMANA_PASSADA,)]
    # Sem data própria, a evidência fica com a data do encontro, não a do envio.
    assert linhas(programa, "SELECT data FROM evidencias") == [(SEMANA_PASSADA,)]


def test_fila_reenviada_inteira_nao_duplica_nada(cliente, cabecalhos, programa, armazenamento):
    evidencias = [("aparelho-7/ev-1", JPEG, "mural.jpg"), ("aparelho-7/ev-2", PDF, "lista.pdf")]
    primeiro = sincronizar_fila(cliente, cabecalhos, {}, evidencias)

    # A resposta se perdeu e o aparelho reenvia tudo, do começo.
    reenvio = sincronizar_fila(cliente, cabecalhos, {}, evidencias)

    assert [r.status_code for r in primeiro] == [201, 201, 201]
    assert [r.status_code for r in reenvio] == [200, 200, 200]
    assert [r.json()["id"] for r in reenvio] == [r.json()["id"] for r in primeiro]
    assert (contar(programa, "atividades"), contar(programa, "chamadas"), contar(programa, "evidencias")) == (1, 3, 2)
    assert len(armazenamento.objetos) == 2, "o arquivo não sobe de novo no reenvio"


def test_reenvio_depois_de_parte_da_fila_ter_ido(cliente, cabecalhos, programa, armazenamento):
    # O encontro e a primeira foto foram; a conexão caiu antes da segunda.
    encontro = enviar_encontro(cliente, cabecalhos).json()
    enviar_evidencia(cliente, cabecalhos, encontro["id"], "aparelho-7/ev-1")

    reenvio = sincronizar_fila(cliente, cabecalhos, {}, [("aparelho-7/ev-1", JPEG, "mural.jpg"), ("aparelho-7/ev-2", PDF, "lista.pdf")])

    assert [r.status_code for r in reenvio] == [200, 200, 201]
    assert contar(programa, "evidencias") == 2


def test_dois_envios_simultaneos_do_mesmo_encontro_gravam_um_so(cliente, cabecalhos, programa):
    # Duas abas, ou o aparelho reenviando enquanto o primeiro envio ainda não respondeu.
    for rodada in range(3):
        largada = threading.Barrier(2)
        respostas = []

        def enviar():
            largada.wait()
            respostas.append(enviar_encontro(cliente, cabecalhos, registro_id=f"aparelho-7/simultaneo-{rodada}"))

        corredores = [threading.Thread(target=enviar) for _ in range(2)]
        for t in corredores:
            t.start()
        for t in corredores:
            t.join()

        assert sorted(r.status_code for r in respostas) == [200, 201]
        assert len({r.json()["id"] for r in respostas}) == 1
    assert (contar(programa, "atividades"), contar(programa, "chamadas")) == (3, 9)


def test_dois_envios_simultaneos_da_mesma_evidencia_gravam_uma_so(cliente, cabecalhos, programa, armazenamento):
    atividade_id = enviar_encontro(cliente, cabecalhos).json()["id"]
    largada = threading.Barrier(2)
    respostas = []

    def enviar():
        largada.wait()
        respostas.append(enviar_evidencia(cliente, cabecalhos, atividade_id, "aparelho-7/ev-simultanea"))

    corredores = [threading.Thread(target=enviar) for _ in range(2)]
    for t in corredores:
        t.start()
    for t in corredores:
        t.join()

    assert sorted(r.status_code for r in respostas) == [200, 201]
    assert len({r.json()["id"] for r in respostas}) == 1
    assert contar(programa, "evidencias") == 1


def test_aparelhos_diferentes_no_mesmo_encontro_sao_registros_diferentes(cliente, cabecalhos, programa):
    # Sem o mesmo registro_id não é reenvio: dois registros (a coordenação decide o que vale).
    enviar_encontro(cliente, cabecalhos, registro_id="aparelho-7/enc-1")
    enviar_encontro(cliente, cabecalhos, usuario="ana", registro_id="aparelho-9/enc-1", educador_id="jessica")

    assert contar(programa, "atividades") == 2


# --- 3. Evidência vinculada à atividade, ao programa, ao autor e à data --------------


def test_evidencia_gravada_com_atividade_programa_autor_e_data(cliente, cabecalhos, programa, armazenamento):
    atividade_id = enviar_encontro(cliente, cabecalhos, data=ONTEM).json()["id"]

    resposta = enviar_evidencia(cliente, cabecalhos, atividade_id, "aparelho-7/ev-1", usuario="ana", descricao="Mural da turma")

    assert resposta.status_code == 201
    [(atividade, programa_id, autor, data, descricao, chave, nome, tipo, tamanho)] = linhas(
        programa,
        "SELECT atividade_id, programa_id, autor_id, data, descricao, chave_arquivo, nome_arquivo, content_type, tamanho FROM evidencias",
    )
    # O autor é quem enviou (a coordenação), não o educador do encontro.
    assert (atividade, programa_id, autor, data) == (atividade_id, "p-1", "ana", ONTEM)
    assert (descricao, nome, tipo, tamanho) == ("Mural da turma", "mural.jpg", "image/jpeg", len(JPEG))
    # Só os metadados no banco; o arquivo está no armazenamento, na pasta da Gestão.
    assert chave.startswith("gestao/evidencias/")
    assert armazenamento.objetos[chave].conteudo == JPEG


def test_evidencia_com_data_propria(cliente, cabecalhos, programa, armazenamento):
    atividade_id = enviar_encontro(cliente, cabecalhos, data=SEMANA_PASSADA).json()["id"]

    enviar_evidencia(cliente, cabecalhos, atividade_id, "aparelho-7/ev-1", data=ONTEM.isoformat())

    assert linhas(programa, "SELECT data FROM evidencias") == [(ONTEM,)]


def test_evidencias_aparecem_no_encontro_e_o_arquivo_volta_igual(cliente, cabecalhos, programa, armazenamento):
    atividade_id = enviar_encontro(cliente, cabecalhos).json()["id"]
    foto = enviar_evidencia(cliente, cabecalhos, atividade_id, "aparelho-7/ev-1").json()
    lista = enviar_evidencia(cliente, cabecalhos, atividade_id, "aparelho-7/ev-2", conteudo=PDF, nome="lista.pdf").json()

    detalhe = cliente.get(f"{P1}/atividades/{atividade_id}", headers=como(cabecalhos, "ana")).json()
    baixado = cliente.get(f"{P1}/evidencias/{lista['id']}/arquivo", headers=como(cabecalhos, "ana"))

    assert [(e["id"], e["atividade_id"], e["programa_id"], e["autor_id"]) for e in detalhe["evidencias"]] == [
        (foto["id"], atividade_id, "p-1", "jessica"),
        (lista["id"], atividade_id, "p-1", "jessica"),
    ]
    assert (baixado.status_code, baixado.content, baixado.headers["content-type"]) == (200, PDF, "application/pdf")


def test_evidencia_nao_se_liga_a_encontro_de_outro_programa(cliente, cabecalhos, programa, armazenamento):
    atividade_id = enviar_encontro(cliente, cabecalhos).json()["id"]

    # Pelo endereço de outro programa, o encontro de p-1 não existe.
    resposta = cliente.post(
        f"/gestao/programas/p-2/atividades/{atividade_id}/evidencias",
        data={"registro_id": "aparelho-3/ev-1"},
        files={"arquivo": ("mural.jpg", JPEG, "image/jpeg")},
        headers=como(cabecalhos, "bruno"),
    )

    assert resposta.status_code == 404
    assert contar(programa, "evidencias") == 0
    assert armazenamento.objetos == {}


def test_o_banco_garante_o_vinculo_mesmo_fora_da_api(programa):
    # Defesa em profundidade: a evidência não pode apontar para atividade de outro programa.
    with programa.begin() as c:
        c.execute(
            sa.text(
                "INSERT INTO atividades (id, registro_id, programa_id, turma_id, data, educador_id, conteudo) "
                "VALUES ('a-1', 'r-1', 'p-1', 't-1', :hoje, 'jessica', 'x')"
            ),
            {"hoje": HOJE},
        )
    with pytest.raises(sa.exc.IntegrityError):
        with programa.begin() as c:
            c.execute(
                sa.text(
                    "INSERT INTO evidencias (id, registro_id, atividade_id, programa_id, autor_id, data, chave_arquivo, nome_arquivo, content_type, tamanho) "
                    "VALUES ('ev-1', 'r-ev', 'a-1', 'p-2', 'jessica', :hoje, 'gestao/evidencias/x.jpg', 'x.jpg', 'image/jpeg', 10)"
                ),
                {"hoje": HOJE},
            )
