"""Alertas de infrequência e busca ativa (T-59 · US-06).

Os critérios do card estão nas seções 1 a 3; a última cobre o acesso. As chamadas são
registradas pela própria API (T-56), como no uso real: o alerta nasce delas.
"""

from datetime import date, timedelta

import pytest
import sqlalchemy as sa

HOJE = date.today()
INICIO = HOJE - timedelta(days=60)
P1 = "/gestao/programas/p-1"
ALERTAS = "/gestao/alertas"


def dia(n):
    """O n-ésimo encontro (1 = o mais antigo), um por dia até ontem."""
    return HOJE - timedelta(days=20 - n)


@pytest.fixture
def programa(banco):
    """p-1 (limite padrão de 3 faltas) com a turma t-1 (todos os dias) e p-2 com t-9.

    - jessica: educadora em p-1       - ana: coordenação em p-1
    - patricia: assistente social em p-1   - bruno: assistente social em p-2
    - dora: direção    - admin: administração
    - t-1: Lara, Davi e Nina matriculados; t-2 (p-1): só Lara
    """
    with banco.begin() as c:
        c.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear'), ('p-2', 'Oficina')"))
        c.execute(
            sa.text("INSERT INTO usuarios (id, nome) VALUES (:id, :nome)"),
            [
                {"id": u, "nome": n}
                for u, n in [
                    ("jessica", "Jéssica Almeida"), ("ana", "Ana Martins"), ("patricia", "Patrícia Souza"),
                    ("bruno", "Bruno Lima"), ("dora", "Dora Prates"), ("admin", "Administração"),
                ]
            ],
        )
        c.execute(sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('dora', 'direcao'), ('admin', 'administracao')"))
        c.execute(
            sa.text("INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) VALUES (:id, :u, :p, :papel, :inicio)"),
            [
                {"id": "v1", "u": "jessica", "p": "p-1", "papel": "educador", "inicio": INICIO},
                {"id": "v2", "u": "ana", "p": "p-1", "papel": "coordenacao", "inicio": INICIO},
                {"id": "v3", "u": "patricia", "p": "p-1", "papel": "assistente_social", "inicio": INICIO},
                {"id": "v4", "u": "bruno", "p": "p-2", "papel": "assistente_social", "inicio": INICIO},
            ],
        )
        c.execute(sa.text("INSERT INTO espacos (id, programa_id, nome) VALUES ('e-1', 'p-1', 'Ateliê'), ('e-9', 'p-2', 'Sala')"))
        c.execute(
            sa.text(
                """
                INSERT INTO turmas (id, programa_id, nome, espaco_id, responsavel_id, capacidade, dias_semana, hora_inicio, hora_fim) VALUES
                    ('t-1', 'p-1', 'Oficina de arte', 'e-1', 'jessica', 20, '{1,2,3,4,5,6,7}', '14:00', '16:00'),
                    ('t-2', 'p-1', 'Leitura', 'e-1', 'jessica', 20, '{1,2,3,4,5,6,7}', '09:00', '10:00')
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
            sa.text("INSERT INTO matriculas (id, turma_id, pessoa_id, situacao, data_entrada) VALUES (:id, :t, :p, 'ativa', :inicio)"),
            [
                {"id": "m1", "t": "t-1", "p": "pe-lara", "inicio": INICIO},
                {"id": "m2", "t": "t-1", "p": "pe-davi", "inicio": INICIO},
                {"id": "m3", "t": "t-1", "p": "pe-nina", "inicio": INICIO},
                {"id": "m4", "t": "t-2", "p": "pe-lara", "inicio": INICIO},
            ],
        )
    return banco


def como(cabecalhos, usuario="patricia"):
    return {**cabecalhos, "X-Usuario-Id": usuario}


_contador = iter(range(10**6))


def encontro(cliente, cabecalhos, n, faltas=(), justificadas=(), fora=(), turma="t-1", registro_id=None):
    """Registra a chamada do n-ésimo encontro: quem não está em faltas/justificadas/fora esteve presente."""
    pessoas = ["pe-lara"] if turma == "t-2" else ["pe-lara", "pe-davi", "pe-nina"]
    presencas = [
        {
            "pessoa_id": p,
            "presente": p not in faltas and p not in justificadas,
            "justificativa": "Consulta médica" if p in justificadas else None,
        }
        for p in pessoas
        if p not in fora
    ]
    resposta = cliente.post(
        f"{P1}/turmas/{turma}/atividades",
        json={"registro_id": registro_id or f"r-{next(_contador)}", "data": dia(n).isoformat(), "conteudo": "Encontro", "presencas": presencas},
        headers=como(cabecalhos, "jessica"),
    )
    assert resposta.status_code in (200, 201), resposta.text
    return resposta


def alertas(cliente, cabecalhos, usuario="patricia", **params):
    resposta = cliente.get(ALERTAS, params=params, headers=como(cabecalhos, usuario))
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def eventos(banco, acao):
    with banco.connect() as c:
        return [tuple(l) for l in c.execute(sa.text("SELECT usuario_id, alvo_tipo, alvo_id FROM log_auditoria WHERE acao = :a ORDER BY id"), {"a": acao})]


def faltas_seguidas(cliente, cabecalhos, pessoa="pe-lara", vezes=3, desde=1):
    for n in range(desde, desde + vezes):
        encontro(cliente, cabecalhos, n, faltas=[pessoa])


def limite(banco, valor):
    with banco.begin() as c:
        c.execute(sa.text("UPDATE projetos SET limite_faltas = :v WHERE id = 'p-1'"), {"v": valor})


# --- 1. Limite atingido: alerta para a equipe responsável --------------------------


def test_ao_atingir_o_limite_o_sistema_cria_o_alerta_para_a_equipe(cliente, cabecalhos, programa):
    faltas_seguidas(cliente, cabecalhos)

    [alerta] = alertas(cliente, cabecalhos)
    assert {k: alerta[k] for k in ("tipo", "titulo", "descricao", "pessoa", "turma", "responsavel_id", "situacao", "faltas_consecutivas", "limite")} == {
        "tipo": "infrequencia",
        "titulo": "Lara precisa de um contato",
        "descricao": "3 ausências consecutivas na turma Oficina de arte. Limite configurado no programa: 3.",
        "pessoa": "Lara Oliveira",
        "turma": "Oficina de arte",
        "responsavel_id": "patricia",
        "situacao": "aberto",
        "faltas_consecutivas": 3,
        "limite": 3,
    }
    assert (alerta["primeira_falta"], alerta["ultima_falta"]) == (dia(1).isoformat(), dia(3).isoformat())
    # Alerta automático, sem usuário, na trilha de auditoria.
    assert eventos(programa, "alerta_infrequencia") == [(None, "alerta", alerta["id"])]


def test_abaixo_do_limite_nao_ha_alerta(cliente, cabecalhos, programa):
    faltas_seguidas(cliente, cabecalhos, vezes=2)

    assert alertas(cliente, cabecalhos) == []


@pytest.mark.parametrize(
    "interrupcao",
    [{}, {"justificadas": ["pe-lara"]}, {"fora": ["pe-lara"]}],
    ids=["presenca", "falta-justificada", "fora-da-chamada"],
)
def test_a_sequencia_recomeca_depois_de_presenca_falta_justificada_ou_ausencia_da_chamada(cliente, cabecalhos, programa, interrupcao):
    encontro(cliente, cabecalhos, 1, faltas=["pe-lara"])
    encontro(cliente, cabecalhos, 2, faltas=["pe-lara"])
    encontro(cliente, cabecalhos, 3, **interrupcao)
    encontro(cliente, cabecalhos, 4, faltas=["pe-lara"])
    encontro(cliente, cabecalhos, 5, faltas=["pe-lara"])

    assert alertas(cliente, cabecalhos) == []


@pytest.mark.parametrize("valor", [1, 2])
def test_o_limite_e_o_configurado_no_programa(cliente, cabecalhos, programa, valor):
    limite(programa, valor)

    faltas_seguidas(cliente, cabecalhos, vezes=valor)

    [alerta] = alertas(cliente, cabecalhos)
    assert (alerta["limite"], alerta["faltas_consecutivas"]) == (valor, valor)
    if valor == 1:
        assert alerta["descricao"].startswith("1 ausência na turma")


def test_cada_pessoa_e_cada_turma_tem_o_proprio_alerta(cliente, cabecalhos, programa):
    for n in (1, 2, 3):
        encontro(cliente, cabecalhos, n, faltas=["pe-lara", "pe-davi"])
        encontro(cliente, cabecalhos, n, turma="t-2", faltas=["pe-lara"])

    assert sorted((a["pessoa_id"], a["turma_id"]) for a in alertas(cliente, cabecalhos)) == [
        ("pe-davi", "t-1"),
        ("pe-lara", "t-1"),
        ("pe-lara", "t-2"),
    ]


def test_mais_faltas_atualizam_o_alerta_aberto_sem_criar_outro(cliente, cabecalhos, programa):
    faltas_seguidas(cliente, cabecalhos, vezes=5)

    [alerta] = alertas(cliente, cabecalhos)
    assert (alerta["faltas_consecutivas"], alerta["ultima_falta"]) == (5, dia(5).isoformat())


def test_sem_assistente_social_o_alerta_vai_para_a_coordenacao(cliente, cabecalhos, programa):
    with programa.begin() as c:
        c.execute(sa.text("UPDATE vinculos_equipe SET data_saida = :ontem WHERE id = 'v3'"), {"ontem": HOJE - timedelta(days=1)})

    faltas_seguidas(cliente, cabecalhos)

    assert alertas(cliente, cabecalhos, "ana")[0]["responsavel_id"] == "ana"


def test_chamada_enviada_fora_de_ordem_conta_pela_data_do_encontro(cliente, cabecalhos, programa):
    # O aparelho sincronizou o encontro 2 por último.
    encontro(cliente, cabecalhos, 1, faltas=["pe-lara"])
    encontro(cliente, cabecalhos, 3, faltas=["pe-lara"])
    assert alertas(cliente, cabecalhos) == []

    encontro(cliente, cabecalhos, 2, faltas=["pe-lara"])

    [alerta] = alertas(cliente, cabecalhos)
    assert (alerta["primeira_falta"], alerta["ultima_falta"]) == (dia(1).isoformat(), dia(3).isoformat())


def test_reenvio_da_chamada_nao_cria_alerta_de_novo(cliente, cabecalhos, programa):
    encontro(cliente, cabecalhos, 1, faltas=["pe-lara"])
    encontro(cliente, cabecalhos, 2, faltas=["pe-lara"])
    encontro(cliente, cabecalhos, 3, faltas=["pe-lara"], registro_id="r-terceiro")

    encontro(cliente, cabecalhos, 3, faltas=["pe-lara"], registro_id="r-terceiro")

    assert len(alertas(cliente, cabecalhos)) == 1
    assert len(eventos(programa, "alerta_infrequencia")) == 1


# --- 2. Busca ativa: resultado, responsável e data na linha do tempo ----------------


def alerta_aberto(cliente, cabecalhos):
    faltas_seguidas(cliente, cabecalhos)
    return alertas(cliente, cabecalhos)[0]["id"]


def registrar_acao(cliente, cabecalhos, alerta_id, usuario="patricia", **dados):
    corpo = {"tipo": "busca_ativa", "data": HOJE.isoformat(), "resultado": "Visita à família; a mãe relatou mudança de horário do trabalho.", **dados}
    return cliente.post(f"{ALERTAS}/{alerta_id}/acoes", json=corpo, headers=como(cabecalhos, usuario))


def test_busca_ativa_registrada_entra_na_linha_do_tempo(cliente, cabecalhos, programa):
    alerta_id = alerta_aberto(cliente, cabecalhos)

    resposta = registrar_acao(cliente, cabecalhos, alerta_id)

    assert resposta.status_code == 201
    [acao] = resposta.json()["acoes"]
    assert {k: acao[k] for k in ("tipo", "tipo_nome", "data", "resultado", "responsavel_id", "responsavel")} == {
        "tipo": "busca_ativa",
        "tipo_nome": "Busca ativa",
        "data": HOJE.isoformat(),
        "resultado": "Visita à família; a mãe relatou mudança de horário do trabalho.",
        "responsavel_id": "patricia",
        "responsavel": "Patrícia Souza",
    }
    assert eventos(programa, "acao_busca_ativa") == [("patricia", "alerta", alerta_id)]


def test_linha_do_tempo_da_mais_recente_para_a_mais_antiga(cliente, cabecalhos, programa):
    alerta_id = alerta_aberto(cliente, cabecalhos)
    registrar_acao(cliente, cabecalhos, alerta_id, tipo="contato_familia", data=(HOJE - timedelta(days=2)).isoformat(), resultado="Telefone sem resposta.")
    registrar_acao(cliente, cabecalhos, alerta_id, usuario="ana", tipo="articulacao_rede", data=HOJE.isoformat(), resultado="Contato com a escola.")
    registrar_acao(cliente, cabecalhos, alerta_id, tipo="busca_ativa", data=(HOJE - timedelta(days=1)).isoformat(), resultado="Visita: família localizada.")

    detalhe = cliente.get(f"{ALERTAS}/{alerta_id}", headers=como(cabecalhos)).json()

    assert [(a["tipo_nome"], a["responsavel"]) for a in detalhe["acoes"]] == [
        ("Articulação com a rede", "Ana Martins"),
        ("Busca ativa", "Patrícia Souza"),
        ("Contato com a família", "Patrícia Souza"),
    ]


@pytest.mark.parametrize(
    "dados, status, codigo",
    [
        ({"resultado": "   "}, 400, "resultado_obrigatorio"),
        ({"data": (HOJE + timedelta(days=1)).isoformat()}, 400, "data_no_futuro"),
        ({"tipo": "visita"}, 422, None),
    ],
    ids=["sem-resultado", "data-futura", "tipo-invalido"],
)
def test_acao_com_dados_invalidos(cliente, cabecalhos, programa, dados, status, codigo):
    alerta_id = alerta_aberto(cliente, cabecalhos)

    resposta = registrar_acao(cliente, cabecalhos, alerta_id, **dados)

    assert resposta.status_code == status
    if codigo:
        assert resposta.json()["detail"]["codigo"] == codigo
    assert cliente.get(f"{ALERTAS}/{alerta_id}", headers=como(cabecalhos)).json()["acoes"] == []


# --- 3. Encerramento só com justificativa ------------------------------------------


def encerrar(cliente, cabecalhos, alerta_id, justificativa, usuario="patricia"):
    return cliente.post(f"{ALERTAS}/{alerta_id}/encerramento", json={"justificativa": justificativa}, headers=como(cabecalhos, usuario))


@pytest.mark.parametrize("justificativa", [None, "", "   "], ids=["ausente", "vazia", "em-branco"])
def test_sem_justificativa_o_alerta_nao_e_encerrado(cliente, cabecalhos, programa, justificativa):
    alerta_id = alerta_aberto(cliente, cabecalhos)

    resposta = encerrar(cliente, cabecalhos, alerta_id, justificativa)

    assert resposta.status_code == 400
    assert resposta.json()["detail"]["codigo"] == "justificativa_obrigatoria"
    assert cliente.get(f"{ALERTAS}/{alerta_id}", headers=como(cabecalhos)).json()["situacao"] == "aberto"


def test_retorno_a_frequencia_confirmado_encerra_com_justificativa(cliente, cabecalhos, programa):
    alerta_id = alerta_aberto(cliente, cabecalhos)
    registrar_acao(cliente, cabecalhos, alerta_id)
    encontro(cliente, cabecalhos, 4)
    encontro(cliente, cabecalhos, 5)

    resposta = encerrar(cliente, cabecalhos, alerta_id, "Voltou a frequentar: presente nos dois últimos encontros.")

    assert resposta.status_code == 200
    alerta = resposta.json()
    assert (alerta["situacao"], alerta["encerrado_por"], alerta["justificativa_encerramento"]) == (
        "encerrado",
        "patricia",
        "Voltou a frequentar: presente nos dois últimos encontros.",
    )
    assert alerta["encerrado_em"]
    # O histórico continua, e o encerramento fica na auditoria.
    assert len(alerta["acoes"]) == 1
    assert eventos(programa, "alerta_encerrado") == [("patricia", "alerta", alerta_id)]


def test_encerrado_nao_reabre_nem_recebe_acoes(cliente, cabecalhos, programa):
    alerta_id = alerta_aberto(cliente, cabecalhos)
    encerrar(cliente, cabecalhos, alerta_id, "Voltou a frequentar.")

    assert encerrar(cliente, cabecalhos, alerta_id, "De novo").status_code == 409
    assert registrar_acao(cliente, cabecalhos, alerta_id).status_code == 409


def test_depois_de_encerrado_so_uma_falta_nova_gera_outro_alerta(cliente, cabecalhos, programa):
    alerta_id = alerta_aberto(cliente, cabecalhos)
    encerrar(cliente, cabecalhos, alerta_id, "Família informou viagem; retorno combinado.")

    # Uma chamada antiga, sincronizada agora, não reabre o caso.
    encontro(cliente, cabecalhos, 0, faltas=["pe-lara"])
    assert [a["situacao"] for a in alertas(cliente, cabecalhos)] == ["encerrado"]

    # Uma falta nova, sim.
    encontro(cliente, cabecalhos, 4, faltas=["pe-lara"])
    assert sorted(a["situacao"] for a in alertas(cliente, cabecalhos)) == ["aberto", "encerrado"]


def test_filtro_por_situacao(cliente, cabecalhos, programa):
    faltas_seguidas(cliente, cabecalhos, "pe-lara")
    faltas_seguidas(cliente, cabecalhos, "pe-davi", desde=4)
    lara = next(a for a in alertas(cliente, cabecalhos) if a["pessoa_id"] == "pe-lara")
    encerrar(cliente, cabecalhos, lara["id"], "Voltou a frequentar.")

    assert [a["pessoa_id"] for a in alertas(cliente, cabecalhos, situacao="aberto")] == ["pe-davi"]
    assert [a["pessoa_id"] for a in alertas(cliente, cabecalhos, situacao="encerrado")] == ["pe-lara"]


# --- Acesso ----------------------------------------------------------------------------


@pytest.mark.parametrize("usuario", ["patricia", "ana", "admin"], ids=["assistente-social", "coordenacao", "administracao"])
def test_coordenacao_assistencia_social_e_administracao_acompanham(cliente, cabecalhos, programa, usuario):
    alerta_id = alerta_aberto(cliente, cabecalhos)

    assert [a["id"] for a in alertas(cliente, cabecalhos, usuario)] == [alerta_id]
    assert registrar_acao(cliente, cabecalhos, alerta_id, usuario=usuario).status_code == 201


@pytest.mark.parametrize("usuario", ["jessica", "dora", "bruno"], ids=["educadora", "direcao", "outro-programa"])
def test_quem_nao_acompanha_nao_ve_nem_age_e_a_tentativa_e_registrada(cliente, cabecalhos, programa, usuario):
    alerta_id = alerta_aberto(cliente, cabecalhos)

    assert alertas(cliente, cabecalhos, usuario) == []
    assert cliente.get(f"{ALERTAS}/{alerta_id}", headers=como(cabecalhos, usuario)).status_code == 403
    assert registrar_acao(cliente, cabecalhos, alerta_id, usuario=usuario).status_code == 403
    assert encerrar(cliente, cabecalhos, alerta_id, "x", usuario=usuario).status_code == 403
    assert cliente.get(ALERTAS, params={"programa_id": "p-1"}, headers=como(cabecalhos, usuario)).status_code == 403
    with programa.connect() as c:
        negacoes = c.execute(
            sa.text("SELECT count(*) FROM log_auditoria WHERE acao = 'acesso_negado' AND usuario_id = :u AND detalhes->>'operacao' = 'acompanhar_alertas'"),
            {"u": usuario},
        ).scalar_one()
    assert negacoes == 4


def test_alerta_inexistente_404(cliente, cabecalhos, programa):
    assert cliente.get(f"{ALERTAS}/nao-existe", headers=como(cabecalhos)).status_code == 404


# --- Trajetória da pessoa (T-60) -------------------------------------------------------


def trajetoria(cliente, cabecalhos, usuario="patricia", pessoa="pe-lara"):
    resposta = cliente.get(f"/gestao/pessoas/{pessoa}/trajetoria", headers=como(cabecalhos, usuario))
    assert resposta.status_code == 200, resposta.text
    return [e for e in resposta.json() if e["tipo"] in ("alerta", "busca_ativa")]


def test_alerta_e_busca_ativa_entram_na_trajetoria_da_pessoa(cliente, cabecalhos, programa):
    alerta_id = alerta_aberto(cliente, cabecalhos)
    registrar_acao(cliente, cabecalhos, alerta_id)

    [acao, alerta] = trajetoria(cliente, cabecalhos)

    assert acao["tipo"] == "busca_ativa"
    assert acao["titulo"] == "Busca ativa: busca ativa"
    assert acao["descricao"] == "Visita à família; a mãe relatou mudança de horário do trabalho. (por Patrícia Souza)"
    assert acao["data"][:10] == HOJE.isoformat()
    assert alerta["tipo"] == "alerta"
    assert alerta["titulo"] == "Alerta de infrequência na turma Oficina de arte"
    assert alerta["descricao"] == f"3 faltas seguidas (limite do programa: 3), de {dia(1):%d/%m/%Y} a {dia(3):%d/%m/%Y}."
    # O alerta de outra pessoa não aparece aqui.
    assert trajetoria(cliente, cabecalhos, pessoa="pe-davi") == []


def test_acao_com_data_anterior_entra_na_data_informada(cliente, cabecalhos, programa):
    alerta_id = alerta_aberto(cliente, cabecalhos)
    ontem = HOJE - timedelta(days=1)
    registrar_acao(cliente, cabecalhos, alerta_id, tipo="contato_familia", data=ontem.isoformat(), resultado="Telefone sem resposta.")

    acao = next(e for e in trajetoria(cliente, cabecalhos) if e["tipo"] == "busca_ativa")

    assert acao["titulo"] == "Busca ativa: contato com a família"
    assert acao["data"][:10] == ontem.isoformat()


def test_encerramento_entra_na_trajetoria_com_a_justificativa(cliente, cabecalhos, programa):
    alerta_id = alerta_aberto(cliente, cabecalhos)
    encerrar(cliente, cabecalhos, alerta_id, "Voltou a frequentar.")

    encerramento = trajetoria(cliente, cabecalhos)[0]

    assert encerramento["titulo"] == "Alerta de infrequência encerrado (turma Oficina de arte)"
    assert encerramento["descricao"] == "Voltou a frequentar."


def test_quem_nao_acompanha_os_alertas_ve_so_que_houve_o_contato(cliente, cabecalhos, programa):
    # A educadora vê a trajetória da pessoa, mas não o resultado da busca ativa nem a justificativa.
    alerta_id = alerta_aberto(cliente, cabecalhos)
    registrar_acao(cliente, cabecalhos, alerta_id)
    encerrar(cliente, cabecalhos, alerta_id, "Voltou a frequentar.")

    eventos_da_educadora = trajetoria(cliente, cabecalhos, usuario="jessica")

    assert [e["descricao"] for e in eventos_da_educadora[:2]] == [
        "Acompanhamento encerrado pela equipe técnica.",
        "Contato de acompanhamento registrado pela equipe técnica.",
    ]
    assert "Visita" not in str(eventos_da_educadora)
    # Quem acompanha (coordenação) vê o conteúdo.
    assert "Visita à família" in str(trajetoria(cliente, cabecalhos, usuario="ana"))


# --- Encontros das faltas (T-89) --------------------------------------------------------


def test_o_detalhe_do_alerta_lista_os_encontros_da_sequencia(cliente, cabecalhos, programa):
    encontro(cliente, cabecalhos, 1, faltas=["pe-lara"])
    encontro(cliente, cabecalhos, 2, justificadas=["pe-lara"])  # interrompe: não entra
    ids = [encontro(cliente, cabecalhos, n, faltas=["pe-lara"]).json()["id"] for n in (3, 4, 5)]
    alerta_id = alertas(cliente, cabecalhos)[0]["id"]

    detalhe = cliente.get(f"{ALERTAS}/{alerta_id}", headers=como(cabecalhos)).json()

    assert detalhe["faltas"] == [{"atividade_id": i, "data": dia(n).isoformat()} for i, n in zip(ids, (3, 4, 5))]
    # Uma falta a mais entra no mesmo alerta.
    novo = encontro(cliente, cabecalhos, 6, faltas=["pe-lara"]).json()["id"]
    assert cliente.get(f"{ALERTAS}/{alerta_id}", headers=como(cabecalhos)).json()["faltas"][-1]["atividade_id"] == novo


def test_faltas_entram_na_trajetoria_ligadas_ao_encontro_e_presencas_nao(cliente, cabecalhos, programa):
    falta = encontro(cliente, cabecalhos, 1, faltas=["pe-lara"]).json()["id"]
    justificada = encontro(cliente, cabecalhos, 2, justificadas=["pe-lara"]).json()["id"]
    encontro(cliente, cabecalhos, 3)  # presente

    resposta = cliente.get("/gestao/pessoas/pe-lara/trajetoria", headers=como(cabecalhos, "jessica"))

    assert resposta.status_code == 200
    faltas = [e for e in resposta.json() if e["tipo"] == "frequencia"]
    assert [(e["titulo"], e["descricao"], e["data"][:10], e["programa_id"], e["atividade_id"]) for e in faltas] == [
        ("Falta justificada na turma Oficina de arte", "Motivo: Consulta médica", dia(2).isoformat(), "p-1", justificada),
        ("Falta na turma Oficina de arte", "Ausente no encontro.", dia(1).isoformat(), "p-1", falta),
    ]
    # Os demais eventos seguem sem encontro ligado.
    assert all(e["atividade_id"] is None for e in resposta.json() if e["tipo"] != "frequencia")
