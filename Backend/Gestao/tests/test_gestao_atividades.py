"""Agenda, encontro com chamada e evidências (T-56 · US-05).

Os critérios da T-56 estão nas seções 1 a 3; as demais cobrem a agenda e o acesso.
O R2 é substituído pelo armazenamento em memória do Financeiro.
"""

from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.routers.comprovantes import obter_armazenamento

HOJE = date.today()
AMANHA = HOJE + timedelta(days=1)

# Segundas e quartas (a turma t-1 se encontra seg e qua).
SEG_07_09 = "2026-09-07"
SEG_28_09 = "2026-09-28"
QUA_30_09 = "2026-09-30"
SEG_05_10 = "2026-10-05"
TER_06_10 = "2026-10-06"
QUA_07_10 = "2026-10-07"

P1 = "/gestao/programas/p-1"
AGENDA = f"{P1}/agenda"
ATIVIDADES_T1 = f"{P1}/turmas/t-1/atividades"

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200
PDF = b"%PDF-1.4\n" + b"0" * 200


@pytest.fixture
def programa(banco):
    """Programa p-1 com a turma t-1 (seg e qua, 14h às 16h) e p-2 com a turma t-9.

    - ana: coordenação (na conta)           - jessica: educadora em p-1 (responsável da t-1)
    - patricia: assistente social em p-1    - rafael: educador em p-1 até 15/09/2026
    - bruno: educador só em p-2             - dora: direção    - admin: administração
    - t-1: lara e davi ativos desde 01/09; caio na lista de espera;
      bia matriculada de 01/09 a 01/10 (saiu)
    """
    with banco.begin() as c:
        c.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear'), ('p-2', 'Oficina')"))
        c.execute(
            sa.text("INSERT INTO usuarios (id, nome) VALUES (:id, :nome)"),
            [
                {"id": u, "nome": n}
                for u, n in [
                    ("ana", "Ana Martins"), ("jessica", "Jéssica Almeida"), ("patricia", "Patrícia Souza"),
                    ("rafael", "Rafael Nunes"), ("bruno", "Bruno Lima"), ("dora", "Dora Prates"),
                    ("admin", "Administração"),
                ]
            ],
        )
        c.execute(
            sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('ana', 'coordenacao'), ('dora', 'direcao'), ('admin', 'administracao')")
        )
        c.execute(
            sa.text(
                "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada, data_saida) "
                "VALUES (:id, :u, :p, :papel, '2026-01-01', :saida)"
            ),
            [
                {"id": "v2", "u": "jessica", "p": "p-1", "papel": "educador", "saida": None},
                {"id": "v3", "u": "patricia", "p": "p-1", "papel": "assistente_social", "saida": None},
                {"id": "v4", "u": "rafael", "p": "p-1", "papel": "educador", "saida": "2026-09-15"},
                {"id": "v5", "u": "bruno", "p": "p-2", "papel": "educador", "saida": None},
            ],
        )
        c.execute(sa.text("INSERT INTO espacos (id, programa_id, nome) VALUES ('e-1', 'p-1', 'Ateliê'), ('e-9', 'p-2', 'Sala')"))
        c.execute(
            sa.text(
                """
                INSERT INTO turmas (id, programa_id, nome, espaco_id, responsavel_id, capacidade, dias_semana, hora_inicio, hora_fim) VALUES
                    ('t-1', 'p-1', 'Oficina de arte', 'e-1', 'jessica', 20, '{1,3}', '14:00', '16:00'),
                    ('t-9', 'p-2', 'Reforço', 'e-9', 'bruno', 10, '{2}', '08:00', '10:00')
                """
            )
        )
        c.execute(sa.text("INSERT INTO nucleos_familiares (id, nome) VALUES ('f-1', 'Oliveira')"))
        c.execute(
            sa.text(
                "INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id) "
                "VALUES (:id, :nome, lower(:nome), '2014-01-01', 'f-1', :p)"
            ),
            [
                {"id": "pe-lara", "nome": "Lara Oliveira", "p": "p-1"},
                {"id": "pe-davi", "nome": "Davi Oliveira", "p": "p-1"},
                {"id": "pe-caio", "nome": "Caio Oliveira", "p": "p-1"},
                {"id": "pe-bia", "nome": "Bia Oliveira", "p": "p-1"},
                {"id": "pe-sem", "nome": "Sem Turma", "p": "p-1"},
            ],
        )
        c.execute(
            sa.text(
                "INSERT INTO matriculas (id, turma_id, pessoa_id, situacao, data_entrada, data_saida, motivo_saida) "
                "VALUES (:id, 't-1', :pessoa, :situacao, :entrada, :saida, :motivo)"
            ),
            [
                {"id": "m-lara", "pessoa": "pe-lara", "situacao": "ativa", "entrada": "2026-09-01", "saida": None, "motivo": None},
                {"id": "m-davi", "pessoa": "pe-davi", "situacao": "ativa", "entrada": "2026-09-01", "saida": None, "motivo": None},
                {"id": "m-caio", "pessoa": "pe-caio", "situacao": "espera", "entrada": None, "saida": None, "motivo": None},
                {"id": "m-bia", "pessoa": "pe-bia", "situacao": "desligada", "entrada": "2026-09-01", "saida": "2026-10-01", "motivo": "Mudou de turno"},
            ],
        )
    return banco


@pytest.fixture
def armazenamento(app):
    memoria = ArmazenamentoEmMemoria()
    app.dependency_overrides[obter_armazenamento] = lambda: memoria
    yield memoria
    app.dependency_overrides.pop(obter_armazenamento, None)


def como(cabecalhos, usuario_id):
    return {**cabecalhos, "X-Usuario-Id": usuario_id}


def chamada(**extra):
    dados = {
        "registro_id": "aparelho-1/enc-1",
        "data": SEG_05_10,
        "conteudo": "Pintura com guache",
        "presencas": [
            {"pessoa_id": "pe-lara", "presente": True},
            {"pessoa_id": "pe-davi", "presente": False, "justificativa": "Consulta médica"},
        ],
    }
    return {**dados, **extra}


def encerrar(cliente, cabecalhos, usuario="jessica", turma="t-1", **extra):
    return cliente.post(f"{P1}/turmas/{turma}/atividades", json=chamada(**extra), headers=como(cabecalhos, usuario))


def enviar_evidencia(cliente, cabecalhos, atividade_id, usuario="jessica", conteudo=JPEG, nome="foto.jpg", **campos):
    dados = {"registro_id": "aparelho-1/ev-1", **campos}
    return cliente.post(
        f"{P1}/atividades/{atividade_id}/evidencias",
        data=dados,
        files={"arquivo": (nome, conteudo, "application/octet-stream")},
        headers=como(cabecalhos, usuario),
    )


def contar(banco, tabela):
    with banco.connect() as c:
        return c.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar_one()


def eventos(banco, acao):
    with banco.connect() as c:
        linhas = c.execute(
            sa.text("SELECT usuario_id, alvo_tipo, alvo_id, detalhes FROM log_auditoria WHERE acao = :acao ORDER BY id"),
            {"acao": acao},
        ).all()
    return [l._asdict() for l in linhas]


# --- 1. Encerrar a chamada grava data, turma, educador, presentes, ausentes e conteúdo --


def test_chamada_encerrada_grava_todos_os_dados_do_encontro(cliente, cabecalhos, programa):
    resposta = encerrar(cliente, cabecalhos)

    assert resposta.status_code == 201
    atividade = resposta.json()
    assert {k: atividade[k] for k in ("data", "turma_id", "turma", "educador_id", "educador", "conteudo", "presentes", "ausentes")} == {
        "data": SEG_05_10,
        "turma_id": "t-1",
        "turma": "Oficina de arte",
        "educador_id": "jessica",
        "educador": "Jéssica Almeida",
        "conteudo": "Pintura com guache",
        "presentes": 1,
        "ausentes": 1,
    }
    assert atividade["chamada"] == [
        {"pessoa_id": "pe-davi", "pessoa": "Davi Oliveira", "presente": False, "justificativa": "Consulta médica"},
        {"pessoa_id": "pe-lara", "pessoa": "Lara Oliveira", "presente": True, "justificativa": None},
    ]
    with programa.connect() as c:
        gravado = c.execute(
            sa.text("SELECT programa_id, turma_id, data, educador_id, conteudo, criado_por FROM atividades")
        ).one()
        linhas = c.execute(sa.text("SELECT pessoa_id, presente FROM chamadas ORDER BY pessoa_id")).all()
    assert tuple(gravado) == ("p-1", "t-1", date(2026, 10, 5), "jessica", "Pintura com guache", "jessica")
    assert [tuple(l) for l in linhas] == [("pe-davi", False), ("pe-lara", True)]


def test_coordenacao_registra_o_encontro_de_outro_educador(cliente, cabecalhos, programa):
    resposta = encerrar(cliente, cabecalhos, usuario="ana", educador_id="jessica")

    assert resposta.status_code == 201
    assert resposta.json()["educador_id"] == "jessica"
    with programa.connect() as c:
        assert c.execute(sa.text("SELECT criado_por FROM atividades")).scalar_one() == "ana"


def test_educador_precisa_de_vinculo_ativo_na_data_do_encontro(cliente, cabecalhos, programa):
    depois_da_saida = encerrar(cliente, cabecalhos, usuario="ana", educador_id="rafael")
    antes_da_saida = encerrar(cliente, cabecalhos, usuario="ana", educador_id="rafael", data=SEG_07_09, registro_id="r-2")

    assert depois_da_saida.status_code == 400
    assert depois_da_saida.json()["detail"]["codigo"] == "educador_sem_vinculo"
    assert antes_da_saida.status_code == 201


def test_so_entra_na_chamada_quem_estava_matriculado_na_data(cliente, cabecalhos, programa):
    presencas = [{"pessoa_id": p, "presente": True} for p in ("pe-lara", "pe-caio", "pe-bia", "pe-sem")]

    resposta = encerrar(cliente, cabecalhos, presencas=presencas)

    assert resposta.status_code == 400
    assert resposta.json()["detail"]["codigo"] == "fora_da_turma"
    # caio está na lista de espera, bia saiu em 01/10 e "sem" nunca foi matriculado.
    assert resposta.json()["detail"]["pessoas"] == ["pe-caio", "pe-bia", "pe-sem"]
    assert contar(programa, "atividades") == 0


def test_quem_saiu_da_turma_depois_entra_na_chamada_de_antes(cliente, cabecalhos, programa):
    presencas = [{"pessoa_id": "pe-lara", "presente": True}, {"pessoa_id": "pe-bia", "presente": True}]

    resposta = encerrar(cliente, cabecalhos, data=SEG_28_09, presencas=presencas)

    assert resposta.status_code == 201
    assert resposta.json()["presentes"] == 2


@pytest.mark.parametrize(
    "extra, codigo",
    [
        ({"presencas": []}, "chamada_vazia"),
        ({"presencas": [{"pessoa_id": "pe-lara", "presente": True}, {"pessoa_id": "pe-lara", "presente": False}]}, "pessoa_repetida"),
        ({"conteudo": "   "}, "conteudo_obrigatorio"),
        ({"data": AMANHA.isoformat()}, "data_no_futuro"),
        ({"presencas": [{"pessoa_id": "pe-lara", "presente": True, "justificativa": "Atrasou"}]}, "justificativa_em_presenca"),
        ({"registro_id": "  "}, "registro_id_obrigatorio"),
    ],
    ids=["chamada-vazia", "pessoa-repetida", "sem-conteudo", "data-futura", "justificativa-em-presenca", "registro-em-branco"],
)
def test_chamada_com_dados_invalidos_400_e_nada_e_gravado(cliente, cabecalhos, programa, extra, codigo):
    resposta = encerrar(cliente, cabecalhos, **extra)

    assert resposta.status_code == 400
    assert resposta.json()["detail"]["codigo"] == codigo
    assert contar(programa, "atividades") == 0
    assert contar(programa, "chamadas") == 0


def test_chamada_sem_campos_obrigatorios_422(cliente, cabecalhos, programa):
    resposta = cliente.post(ATIVIDADES_T1, json={"registro_id": "r"}, headers=como(cabecalhos, "jessica"))

    assert resposta.status_code == 422


@pytest.mark.parametrize("turma", ["t-404", "t-9"], ids=["inexistente", "de-outro-programa"])
def test_turma_inexistente_ou_de_outro_programa_404(cliente, cabecalhos, programa, turma):
    assert encerrar(cliente, cabecalhos, turma=turma).status_code == 404


# --- 2. Reenvio da fila offline não duplica -------------------------------------------


def test_reenvio_do_mesmo_encontro_nao_duplica(cliente, cabecalhos, programa):
    primeiro = encerrar(cliente, cabecalhos)
    reenvio = encerrar(cliente, cabecalhos)

    assert (primeiro.status_code, reenvio.status_code) == (201, 200)
    assert reenvio.json() == primeiro.json()
    assert contar(programa, "atividades") == 1
    assert contar(programa, "chamadas") == 2


def test_reenvio_vale_a_primeira_versao_recebida(cliente, cabecalhos, programa):
    primeiro = encerrar(cliente, cabecalhos)
    alterado = encerrar(cliente, cabecalhos, conteudo="Outro conteúdo", presencas=[{"pessoa_id": "pe-lara", "presente": False}])

    assert alterado.status_code == 200
    assert alterado.json()["conteudo"] == "Pintura com guache"
    assert alterado.json()["chamada"] == primeiro.json()["chamada"]


def test_reenvio_nao_reavalia_regras_que_mudaram_depois(cliente, cabecalhos, programa):
    encerrar(cliente, cabecalhos)
    with programa.begin() as c:
        c.execute(sa.text("UPDATE matriculas SET situacao = 'desligada', data_saida = '2026-09-02', motivo_saida = 'Erro' WHERE id = 'm-davi'"))

    assert encerrar(cliente, cabecalhos).status_code == 200


def test_identificador_usado_em_outra_turma_409(cliente, cabecalhos, programa):
    encerrar(cliente, cabecalhos)
    with programa.begin() as c:
        c.execute(
            sa.text(
                "INSERT INTO turmas (id, programa_id, nome, espaco_id, responsavel_id, capacidade, dias_semana, hora_inicio, hora_fim) "
                "VALUES ('t-2', 'p-1', 'Leitura', 'e-1', 'jessica', 10, '{2}', '09:00', '10:00')"
            )
        )

    resposta = encerrar(cliente, cabecalhos, turma="t-2")

    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == "registro_id_em_uso"


def test_encontros_diferentes_no_mesmo_dia_sao_gravados(cliente, cabecalhos, programa):
    encerrar(cliente, cabecalhos)

    assert encerrar(cliente, cabecalhos, registro_id="aparelho-1/enc-2").status_code == 201
    assert contar(programa, "atividades") == 2


def test_reenvio_da_evidencia_nao_duplica_nem_sobe_o_arquivo_de_novo(cliente, cabecalhos, programa, armazenamento):
    atividade = encerrar(cliente, cabecalhos).json()

    primeiro = enviar_evidencia(cliente, cabecalhos, atividade["id"])
    reenvio = enviar_evidencia(cliente, cabecalhos, atividade["id"])

    assert (primeiro.status_code, reenvio.status_code) == (201, 200)
    assert reenvio.json() == primeiro.json()
    assert contar(programa, "evidencias") == 1
    assert len(armazenamento.objetos) == 1


def test_identificador_de_evidencia_usado_em_outro_encontro_409(cliente, cabecalhos, programa, armazenamento):
    a1 = encerrar(cliente, cabecalhos).json()
    a2 = encerrar(cliente, cabecalhos, registro_id="aparelho-1/enc-2", data=QUA_07_10).json()
    enviar_evidencia(cliente, cabecalhos, a1["id"])

    resposta = enviar_evidencia(cliente, cabecalhos, a2["id"])

    assert resposta.status_code == 409
    assert len(armazenamento.objetos) == 1


# --- 3. Evidência fica vinculada à atividade, ao programa, ao autor e à data ----------


def test_evidencia_salva_vinculada_a_atividade_programa_autor_e_data(cliente, cabecalhos, programa, armazenamento):
    atividade = encerrar(cliente, cabecalhos).json()

    resposta = enviar_evidencia(cliente, cabecalhos, atividade["id"], descricao="Painel da turma")

    assert resposta.status_code == 201
    evidencia = resposta.json()
    assert {k: evidencia[k] for k in ("atividade_id", "programa_id", "autor_id", "autor", "data", "descricao", "content_type", "tamanho")} == {
        "atividade_id": atividade["id"],
        "programa_id": "p-1",
        "autor_id": "jessica",
        "autor": "Jéssica Almeida",
        "data": SEG_05_10,
        "descricao": "Painel da turma",
        "content_type": "image/jpeg",
        "tamanho": len(JPEG),
    }
    [(chave, objeto)] = armazenamento.objetos.items()
    assert chave.startswith("gestao/evidencias/")
    assert objeto.conteudo == JPEG
    with programa.connect() as c:
        assert c.execute(sa.text("SELECT chave_arquivo FROM evidencias")).scalar_one() == chave
    detalhe = cliente.get(f"{P1}/atividades/{atividade['id']}", headers=como(cabecalhos, "ana")).json()
    assert [e["id"] for e in detalhe["evidencias"]] == [evidencia["id"]]


def test_evidencia_com_data_propria_e_autor_de_quem_envia(cliente, cabecalhos, programa, armazenamento):
    atividade = encerrar(cliente, cabecalhos).json()

    evidencia = enviar_evidencia(cliente, cabecalhos, atividade["id"], usuario="ana", conteudo=PDF, nome="lista.pdf", data=TER_06_10).json()

    assert (evidencia["data"], evidencia["autor_id"], evidencia["content_type"]) == (TER_06_10, "ana", "application/pdf")


@pytest.mark.parametrize(
    "conteudo, status",
    [(b"", 400), (b"texto qualquer", 400), (b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024), 413)],
    ids=["vazio", "tipo-nao-aceito", "maior-que-5mb"],
)
def test_arquivo_invalido_e_recusado_sem_gravar(cliente, cabecalhos, programa, armazenamento, conteudo, status):
    atividade = encerrar(cliente, cabecalhos).json()

    resposta = enviar_evidencia(cliente, cabecalhos, atividade["id"], conteudo=conteudo)

    assert resposta.status_code == status
    assert contar(programa, "evidencias") == 0
    assert armazenamento.objetos == {}


def test_evidencia_com_data_no_futuro_400(cliente, cabecalhos, programa, armazenamento):
    atividade = encerrar(cliente, cabecalhos).json()

    resposta = enviar_evidencia(cliente, cabecalhos, atividade["id"], data=AMANHA.isoformat())

    assert resposta.status_code == 400
    assert armazenamento.objetos == {}


def test_evidencia_de_atividade_inexistente_404(cliente, cabecalhos, programa, armazenamento):
    assert enviar_evidencia(cliente, cabecalhos, "nao-existe").status_code == 404


def test_sem_armazenamento_configurado_503(cliente, cabecalhos, programa, monkeypatch):
    atividade = encerrar(cliente, cabecalhos).json()
    for nome in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"):
        monkeypatch.delenv(nome, raising=False)

    assert enviar_evidencia(cliente, cabecalhos, atividade["id"]).status_code == 503


def test_download_devolve_o_arquivo_e_fica_na_auditoria(cliente, cabecalhos, programa, armazenamento):
    atividade = encerrar(cliente, cabecalhos).json()
    evidencia = enviar_evidencia(cliente, cabecalhos, atividade["id"]).json()

    resposta = cliente.get(f"{P1}/evidencias/{evidencia['id']}/arquivo", headers=como(cabecalhos, "ana"))

    assert resposta.status_code == 200
    assert resposta.content == JPEG
    assert resposta.headers["content-type"] == "image/jpeg"
    assert resposta.headers["cache-control"] == "private, no-store"
    [registro] = eventos(programa, "download_evidencia")
    assert (registro["usuario_id"], registro["alvo_tipo"], registro["alvo_id"]) == ("ana", "evidencia", evidencia["id"])


# --- Agenda --------------------------------------------------------------------


def test_agenda_traz_os_encontros_previstos_e_os_registrados(cliente, cabecalhos, programa):
    atividade = encerrar(cliente, cabecalhos).json()

    resposta = cliente.get(AGENDA, params={"inicio": SEG_05_10, "fim": QUA_07_10}, headers=como(cabecalhos, "jessica"))

    assert resposta.status_code == 200
    assert [(e["data"], e["turma_id"], e["previsto"], e["atividades"]) for e in resposta.json()] == [
        (SEG_05_10, "t-1", True, [atividade["id"]]),
        (QUA_07_10, "t-1", True, []),
    ]
    primeiro = resposta.json()[0]
    assert (primeiro["hora_inicio"], primeiro["hora_fim"], primeiro["espaco"], primeiro["responsavel"]) == (
        "14:00", "16:00", "Ateliê", "Jéssica Almeida",
    )


def test_encontro_fora_do_dia_da_turma_aparece_como_nao_previsto(cliente, cabecalhos, programa):
    atividade = encerrar(cliente, cabecalhos, data=TER_06_10).json()

    encontros = cliente.get(AGENDA, params={"inicio": TER_06_10}, headers=como(cabecalhos, "jessica")).json()

    assert [(e["data"], e["previsto"], e["atividades"]) for e in encontros] == [(TER_06_10, False, [atividade["id"]])]


@pytest.mark.parametrize(
    "params",
    [{"inicio": QUA_07_10, "fim": SEG_05_10}, {"inicio": "2026-01-01", "fim": "2026-12-31"}],
    ids=["fim-antes-do-inicio", "periodo-longo"],
)
def test_agenda_com_periodo_invalido_400(cliente, cabecalhos, programa, params):
    assert cliente.get(AGENDA, params=params, headers=como(cabecalhos, "jessica")).status_code == 400


def test_agenda_nao_traz_nomes_de_pessoas_e_a_direcao_consulta(cliente, cabecalhos, programa):
    encerrar(cliente, cabecalhos)

    resposta = cliente.get(AGENDA, params={"inicio": SEG_05_10}, headers=como(cabecalhos, "dora"))

    assert resposta.status_code == 200
    assert "Lara" not in resposta.text


# --- Acesso --------------------------------------------------------------------


@pytest.mark.parametrize("usuario", ["jessica", "ana", "admin"], ids=["educador", "coordenacao", "administracao"])
def test_quem_registra_atividades(cliente, cabecalhos, programa, armazenamento, usuario):
    resposta = encerrar(cliente, cabecalhos, usuario=usuario, educador_id="jessica")

    assert resposta.status_code == 201
    assert enviar_evidencia(cliente, cabecalhos, resposta.json()["id"], usuario=usuario).status_code == 201


@pytest.mark.parametrize(
    "usuario, mensagem",
    [
        ("patricia", "não pode registrar atividades"),
        ("dora", "não pode registrar atividades"),
        ("rafael", "não tem acesso a este programa"),
        ("bruno", "não tem acesso a este programa"),
    ],
    ids=["assistente-social", "direcao", "educador-desligado", "outro-programa"],
)
def test_sem_permissao_para_registrar_403_e_registrado(cliente, cabecalhos, programa, usuario, mensagem):
    resposta = encerrar(cliente, cabecalhos, usuario=usuario)

    assert resposta.status_code == 403
    assert mensagem in resposta.json()["detail"]
    [negacao] = eventos(programa, "acesso_negado")
    assert (negacao["usuario_id"], negacao["alvo_id"], negacao["detalhes"]["operacao"]) == (usuario, "p-1", "registrar_atividade")
    assert contar(programa, "atividades") == 0


def test_assistente_social_nao_envia_evidencia(cliente, cabecalhos, programa, armazenamento):
    atividade = encerrar(cliente, cabecalhos).json()

    assert enviar_evidencia(cliente, cabecalhos, atividade["id"], usuario="patricia").status_code == 403
    assert armazenamento.objetos == {}


def test_chamada_com_nomes_segue_a_regra_de_pessoas(cliente, cabecalhos, programa, armazenamento):
    atividade = encerrar(cliente, cabecalhos).json()
    evidencia = enviar_evidencia(cliente, cabecalhos, atividade["id"]).json()

    assert cliente.get(f"{P1}/atividades/{atividade['id']}", headers=como(cabecalhos, "patricia")).status_code == 200
    assert cliente.get(f"{P1}/atividades/{atividade['id']}", headers=como(cabecalhos, "dora")).status_code == 403
    assert cliente.get(f"{P1}/evidencias/{evidencia['id']}/arquivo", headers=como(cabecalhos, "dora")).status_code == 403
    assert [(n["usuario_id"], n["alvo_tipo"]) for n in eventos(programa, "acesso_negado")] == [
        ("dora", "atividade"),
        ("dora", "evidencia"),
    ]
    assert eventos(programa, "download_evidencia") == []


def test_atividade_de_outro_programa_404(cliente, cabecalhos, programa):
    atividade = encerrar(cliente, cabecalhos).json()

    resposta = cliente.get(f"/gestao/programas/p-2/atividades/{atividade['id']}", headers=como(cabecalhos, "admin"))

    assert resposta.status_code == 404
