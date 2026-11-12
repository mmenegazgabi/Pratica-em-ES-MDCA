"""Cadastro de pessoas atendidas: duplicidade, responsável legal, autorizações e acesso (T-48 · US-03)."""

from datetime import date, timedelta

import pytest
import sqlalchemy as sa

HOJE = date.today()
ONTEM = HOJE - timedelta(days=1)
AMANHA = HOJE + timedelta(days=1)
DAQUI_A_UM_ANO = HOJE + timedelta(days=365)

PESSOAS = "/gestao/pessoas"
DUPLICIDADES = "/gestao/pessoas/duplicidades"
USO_DE_IMAGEM = "/gestao/pessoas/uso-de-imagem"
NUCLEOS = "/gestao/nucleos-familiares"


@pytest.fixture
def cadastro(banco):
    """Programas p-1 (Semear) e p-2 (Oficina), equipe e duas pessoas já cadastradas.

    - admin: administração          - dora: direção
    - ana: coordenação em p-1        - patricia: assistente social em p-1
    - jessica: educadora em p-1      - bruno: assistente social em p-2
    - rafael: assistente social em p-1, saiu ontem
    - Lara Oliveira (pe-lara, 12/05/2013, p-1): núcleo Oliveira, responsável legal Marina Oliveira
    - Miguel Santos (pe-miguel, p-2): núcleo Santos, responsável legal Cláudia Santos
    """
    with banco.begin() as c:
        c.execute(sa.text("INSERT INTO projetos (id, nome) VALUES ('p-1', 'Semear'), ('p-2', 'Oficina')"))
        c.execute(
            sa.text("INSERT INTO usuarios (id, nome) VALUES (:id, :nome)"),
            [
                {"id": u, "nome": n}
                for u, n in [
                    ("admin", "Administração"), ("dora", "Dora Prates"), ("ana", "Ana Martins"),
                    ("patricia", "Patrícia Souza"), ("jessica", "Jéssica Almeida"),
                    ("bruno", "Bruno Lima"), ("rafael", "Rafael Nunes"),
                ]
            ],
        )
        c.execute(
            sa.text("INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('admin', 'administracao'), ('dora', 'direcao'), ('ana', 'coordenacao')")
        )
        c.execute(
            sa.text(
                "INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada, data_saida) "
                "VALUES (:id, :u, :p, :papel, '2025-01-01', :saida)"
            ),
            [
                {"id": "v2", "u": "patricia", "p": "p-1", "papel": "assistente_social", "saida": None},
                {"id": "v3", "u": "jessica", "p": "p-1", "papel": "educador", "saida": None},
                {"id": "v4", "u": "bruno", "p": "p-2", "papel": "assistente_social", "saida": None},
                {"id": "v5", "u": "rafael", "p": "p-1", "papel": "assistente_social", "saida": ONTEM},
            ],
        )
        c.execute(sa.text("INSERT INTO nucleos_familiares (id, nome) VALUES ('f-oliveira', 'Oliveira'), ('f-santos', 'Santos')"))
        c.execute(
            sa.text(
                "INSERT INTO pessoas (id, nome, nome_normalizado, data_nascimento, nucleo_familiar_id, programa_id) VALUES "
                "('pe-lara', 'Lara Oliveira', 'lara oliveira', '2013-05-12', 'f-oliveira', 'p-1'), "
                "('pe-miguel', 'Miguel Santos', 'miguel santos', '2012-08-03', 'f-santos', 'p-2')"
            )
        )
        c.execute(
            sa.text(
                "INSERT INTO responsaveis (id, nome, nome_normalizado) VALUES "
                "('r-marina', 'Marina Oliveira', 'marina oliveira'), ('r-claudia', 'Cláudia Santos', 'claudia santos')"
            )
        )
        c.execute(
            sa.text(
                "INSERT INTO pessoas_responsaveis (pessoa_id, responsavel_id, parentesco, responsavel_legal) VALUES "
                "('pe-lara', 'r-marina', 'Mãe', true), ('pe-miguel', 'r-claudia', 'Mãe', true)"
            )
        )
    return banco


def como(cabecalhos, usuario_id):
    return {**cabecalhos, "X-Usuario-Id": usuario_id}


def eventos(banco, acao=None):
    with banco.connect() as c:
        linhas = c.execute(
            sa.text("SELECT usuario_id, acao, alvo_tipo, alvo_id, detalhes FROM log_auditoria ORDER BY id")
        ).all()
    return [l._asdict() for l in linhas if acao is None or l.acao == acao]


def total(banco, tabela):
    with banco.connect() as c:
        return c.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar()


def nova_pessoa(**extra):
    """Criança nova no p-1, com núcleo e responsável legal novos."""
    dados = {
        "programa_id": "p-1",
        "nome": "Sofia Costa",
        "data_nascimento": "2015-01-23",
        "nucleo_familiar_nome": "Costa",
        "responsaveis": [{"nome": "Daniela Costa", "parentesco": "Mãe", "responsavel_legal": True}],
    }
    return {**dados, **extra}


def cadastrar(cliente, cabecalhos, usuario="ana", **extra):
    return cliente.post(PESSOAS, json=nova_pessoa(**extra), headers=como(cabecalhos, usuario))


# --- Cadastro ------------------------------------------------------------------------


@pytest.mark.parametrize("usuario", ["ana", "patricia", "admin"], ids=["coordenacao", "assistente-social", "administracao"])
def test_quem_pode_cadastra_pessoa_com_nucleo_e_responsavel_legal(cliente, cabecalhos, cadastro, usuario):
    resposta = cadastrar(cliente, cabecalhos, usuario)

    assert resposta.status_code == 201
    pessoa = resposta.json()
    assert pessoa["nome"] == "Sofia Costa"
    assert pessoa["programa"] == "Semear"
    assert pessoa["nucleo_familiar"]["nome"] == "Costa"
    assert [(r["nome"], r["parentesco"], r["responsavel_legal"]) for r in pessoa["responsaveis"]] == [
        ("Daniela Costa", "Mãe", True)
    ]
    assert pessoa["autorizacao_imagem"] == "sem_autorizacao"
    assert pessoa["situacao"] == "ativo"


def test_pessoa_reaproveita_nucleo_e_responsavel_ja_cadastrados(cliente, cabecalhos, cadastro):
    resposta = cadastrar(
        cliente, cabecalhos,
        nome="Davi Oliveira", data_nascimento="2016-02-01",
        nucleo_familiar_nome=None, nucleo_familiar_id="f-oliveira",
        responsaveis=[{"id": "r-marina", "parentesco": "Mãe", "responsavel_legal": True}],
    )

    assert resposta.status_code == 201
    assert resposta.json()["nucleo_familiar"] == {"id": "f-oliveira", "nome": "Oliveira"}
    assert total(cadastro, "responsaveis") == 2
    assert total(cadastro, "nucleos_familiares") == 2


def test_menor_sem_responsavel_legal_400_e_nada_e_gravado(cliente, cabecalhos, cadastro):
    for responsaveis in ([], [{"nome": "Tio Pedro", "parentesco": "Tio", "responsavel_legal": False}]):
        resposta = cadastrar(cliente, cabecalhos, responsaveis=responsaveis)

        assert resposta.status_code == 400
        assert resposta.json()["detail"] == "Informe ao menos um responsável legal para uma pessoa menor de idade."
    assert total(cadastro, "pessoas") == 2


def test_maior_de_idade_dispensa_responsavel(cliente, cabecalhos, cadastro):
    resposta = cadastrar(cliente, cabecalhos, nome="Joana Lima", data_nascimento="2000-03-10", responsaveis=[])

    assert resposta.status_code == 201
    assert resposta.json()["responsaveis"] == []


def test_quem_faz_18_anos_hoje_ja_e_maior(cliente, cabecalhos, cadastro):
    nascimento = HOJE.replace(year=HOJE.year - 18) if not (HOJE.month == 2 and HOJE.day == 29) else date(HOJE.year - 18, 3, 1)
    resposta = cadastrar(cliente, cabecalhos, nome="Caio Lima", data_nascimento=nascimento.isoformat(), responsaveis=[])

    assert resposta.status_code == 201


@pytest.mark.parametrize(
    "extra, mensagem",
    [
        ({"data_nascimento": AMANHA.isoformat()}, "A data de nascimento não pode estar no futuro."),
        ({"nucleo_familiar_nome": None}, "Informe o núcleo familiar."),
        ({"nucleo_familiar_nome": None, "nucleo_familiar_id": "f-x"}, "Núcleo familiar não encontrado."),
        ({"responsaveis": [{"id": "r-x", "responsavel_legal": True}]}, "Responsável não encontrado."),
        ({"responsaveis": [{"parentesco": "Mãe", "responsavel_legal": True}]}, "Informe o nome de cada responsável."),
    ],
    ids=["nascimento-futuro", "sem-nucleo", "nucleo-inexistente", "responsavel-inexistente", "responsavel-sem-nome"],
)
def test_cadastro_com_dados_invalidos_400(cliente, cabecalhos, cadastro, extra, mensagem):
    resposta = cadastrar(cliente, cabecalhos, **extra)

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == mensagem


def test_cadastro_sem_campos_obrigatorios_422(cliente, cabecalhos, cadastro):
    resposta = cliente.post(PESSOAS, json={"programa_id": "p-1"}, headers=como(cabecalhos, "ana"))

    assert resposta.status_code == 422


def test_cadastro_em_programa_inexistente_404(cliente, cabecalhos, cadastro):
    assert cadastrar(cliente, cabecalhos, programa_id="p-9").status_code == 404


# --- Duplicidade ---------------------------------------------------------------------


def test_mesmo_nome_e_nascimento_avisa_antes_de_concluir(cliente, cabecalhos, cadastro):
    # Maiúsculas, acentos e espaços diferentes contam como o mesmo nome.
    resposta = cadastrar(
        cliente, cabecalhos, nome="  LÁRA   oliveira ", data_nascimento="2013-05-12",
        nucleo_familiar_nome="Oliveira", responsaveis=[{"nome": "Outra Pessoa", "responsavel_legal": True}],
    )

    assert resposta.status_code == 409
    detalhe = resposta.json()["detail"]
    assert detalhe["codigo"] == "possivel_duplicidade"
    assert [(c["id"], c["programa"], c["responsaveis"], c["motivos"]) for c in detalhe["candidatos"]] == [
        ("pe-lara", "Semear", ["Marina Oliveira"], ["nascimento"])
    ]
    assert total(cadastro, "pessoas") == 2


def test_mesmo_nome_e_mesmo_responsavel_tambem_avisa(cliente, cabecalhos, cadastro):
    resposta = cadastrar(
        cliente, cabecalhos, nome="Lara Oliveira", data_nascimento="2014-01-01",
        responsaveis=[{"nome": "marina  OLIVEIRA", "responsavel_legal": True}],
    )

    assert resposta.status_code == 409
    assert resposta.json()["detail"]["candidatos"][0]["motivos"] == ["responsavel"]


def test_responsavel_existente_por_id_conta_na_duplicidade(cliente, cabecalhos, cadastro):
    resposta = cadastrar(
        cliente, cabecalhos, nome="Lara Oliveira", data_nascimento="2014-01-01",
        responsaveis=[{"id": "r-marina", "responsavel_legal": True}],
    )

    assert resposta.status_code == 409


def test_mesmo_nome_sem_nascimento_nem_responsavel_em_comum_nao_avisa(cliente, cabecalhos, cadastro):
    resposta = cadastrar(cliente, cabecalhos, nome="Lara Oliveira", data_nascimento="2014-01-01")

    assert resposta.status_code == 201


def test_duplicidade_confirmada_cadastra_e_fica_na_auditoria(cliente, cabecalhos, cadastro):
    resposta = cadastrar(
        cliente, cabecalhos, nome="Lara Oliveira", data_nascimento="2013-05-12", confirmar_duplicidade=True
    )

    assert resposta.status_code == 201
    [evento] = eventos(cadastro, "duplicidade_confirmada")
    assert evento["usuario_id"] == "ana"
    assert evento["alvo_id"] == resposta.json()["id"]
    assert evento["detalhes"] == {"semelhantes": ["pe-lara"]}


def test_revisao_consulta_duplicidades_sem_gravar(cliente, cabecalhos, cadastro):
    corpo = {"programa_id": "p-1", "nome": "lara oliveira", "data_nascimento": "2013-05-12", "responsaveis": []}

    resposta = cliente.post(DUPLICIDADES, json=corpo, headers=como(cabecalhos, "patricia"))

    assert resposta.status_code == 200
    assert [c["id"] for c in resposta.json()] == ["pe-lara"]
    sem_semelhante = {**corpo, "nome": "Pessoa Nova"}
    assert cliente.post(DUPLICIDADES, json=sem_semelhante, headers=como(cabecalhos, "patricia")).json() == []
    assert total(cadastro, "pessoas") == 2


# --- Acesso --------------------------------------------------------------------------


@pytest.mark.parametrize("usuario", ["jessica", "bruno", "dora", "rafael"], ids=["educadora", "outro-programa", "direcao", "desligado"])
def test_sem_permissao_para_cadastrar_403_e_registrado(cliente, cabecalhos, cadastro, usuario):
    resposta = cadastrar(cliente, cabecalhos, usuario)

    assert resposta.status_code == 403
    [negacao] = eventos(cadastro, "acesso_negado")
    assert (negacao["usuario_id"], negacao["alvo_tipo"], negacao["alvo_id"]) == (usuario, "programa", "p-1")
    assert negacao["detalhes"]["operacao"] == "cadastrar"
    assert total(cadastro, "pessoas") == 2


def test_educadora_consulta_mas_nao_cadastra(cliente, cabecalhos, cadastro):
    assert cliente.get(f"{PESSOAS}/pe-lara", headers=como(cabecalhos, "jessica")).status_code == 200
    resposta = cadastrar(cliente, cabecalhos, "jessica")
    assert resposta.json()["detail"] == "Seu perfil não pode cadastrar nem alterar pessoas deste programa."


@pytest.mark.parametrize("usuario", ["dora", "bruno", "rafael"], ids=["direcao", "outro-programa", "desligado"])
def test_cadastro_individual_restrito_ao_programa(cliente, cabecalhos, cadastro, usuario):
    resposta = cliente.get(f"{PESSOAS}/pe-lara", headers=como(cabecalhos, usuario))

    assert resposta.status_code == 403
    [negacao] = eventos(cadastro, "acesso_negado")
    assert (negacao["alvo_tipo"], negacao["alvo_id"]) == ("pessoa", "pe-lara")


def test_pessoa_inexistente_404_sem_registro(cliente, cabecalhos, cadastro):
    assert cliente.get(f"{PESSOAS}/pe-x", headers=como(cabecalhos, "admin")).status_code == 404
    assert eventos(cadastro) == []


def test_sem_identificacao_400(cliente, cabecalhos, cadastro):
    assert cliente.get(PESSOAS, headers=cabecalhos).status_code == 400


@pytest.mark.parametrize(
    "usuario, esperados",
    [("admin", ["pe-lara", "pe-miguel"]), ("jessica", ["pe-lara"]), ("bruno", ["pe-miguel"]), ("dora", []), ("rafael", [])],
)
def test_lista_so_pessoas_dos_programas_em_que_atua(cliente, cabecalhos, cadastro, usuario, esperados):
    resposta = cliente.get(PESSOAS, headers=como(cabecalhos, usuario))

    assert resposta.status_code == 200
    assert [p["id"] for p in resposta.json()] == esperados


def test_lista_de_um_programa_sem_acesso_403(cliente, cabecalhos, cadastro):
    assert cliente.get(PESSOAS, params={"programa_id": "p-2"}, headers=como(cabecalhos, "patricia")).status_code == 403


@pytest.mark.parametrize("busca", ["LARA", "olivei", "marina"], ids=["nome", "nucleo", "responsavel"])
def test_busca_por_nome_nucleo_ou_responsavel(cliente, cabecalhos, cadastro, busca):
    resposta = cliente.get(PESSOAS, params={"busca": busca}, headers=como(cabecalhos, "admin"))

    assert [p["id"] for p in resposta.json()] == ["pe-lara"]
    assert resposta.json()[0]["responsaveis"] == ["Marina Oliveira"]


def test_nucleos_visiveis_so_dos_programas_em_que_atua(cliente, cabecalhos, cadastro):
    nomes = lambda u: [n["nome"] for n in cliente.get(NUCLEOS, headers=como(cabecalhos, u)).json()]  # noqa: E731

    assert nomes("admin") == ["Oliveira", "Santos"]
    assert nomes("ana") == ["Oliveira", "Santos"]  # coordenação: todos os programas
    assert nomes("patricia") == ["Oliveira"]
    assert nomes("dora") == []


# --- Responsáveis e documentos -------------------------------------------------------


def test_inclui_responsavel_e_recusa_repetido(cliente, cabecalhos, cadastro):
    url = f"{PESSOAS}/pe-lara/responsaveis"
    resposta = cliente.post(url, json={"nome": "Antônio Oliveira", "parentesco": "Avô"}, headers=como(cabecalhos, "patricia"))

    assert resposta.status_code == 201
    assert [r["nome"] for r in resposta.json()["responsaveis"]] == ["Marina Oliveira", "Antônio Oliveira"]
    repetido = cliente.post(url, json={"id": "r-marina"}, headers=como(cabecalhos, "patricia"))
    assert repetido.status_code == 409


PDF = b"%PDF-1.4\n" + b"0" * 2039


def enviar_documento(cliente, cabecalhos, pessoa="pe-lara", usuario="ana", tipo="autorizacao_imagem", nome="termo.pdf", conteudo=PDF):
    return cliente.post(
        f"{PESSOAS}/{pessoa}/documentos",
        data={"tipo": tipo},
        files={"arquivo": (nome, conteudo, "application/pdf")},
        headers=como(cabecalhos, usuario),
    )


def test_documento_registra_metadados(cliente, cabecalhos, cadastro, armazenamento):
    resposta = enviar_documento(cliente, cabecalhos)

    assert resposta.status_code == 201
    pessoa = cliente.get(f"{PESSOAS}/pe-lara", headers=como(cabecalhos, "ana")).json()
    assert [(d["tipo"], d["nome_arquivo"], d["tamanho"], d["tem_arquivo"]) for d in pessoa["documentos"]] == [
        ("autorizacao_imagem", "termo.pdf", 2048, True)
    ]


# --- Autorizações --------------------------------------------------------------------


def autorizar(cliente, cabecalhos, pessoa="pe-lara", usuario="ana", **dados):
    corpo = {"tipo": "uso_de_imagem", "valida_ate": DAQUI_A_UM_ANO.isoformat(), **dados}
    return cliente.post(f"{PESSOAS}/{pessoa}/autorizacoes", json=corpo, headers=como(cabecalhos, usuario))


def test_autorizacao_vigente_vencida_e_revogada(cliente, cabecalhos, cadastro):
    vigente = autorizar(cliente, cabecalhos)
    vencida = autorizar(cliente, cabecalhos, valida_de="2025-01-01", valida_ate="2025-12-31")

    assert vigente.status_code == 201 and vigente.json()["situacao"] == "vigente"
    assert vigente.json()["valida_de"] == HOJE.isoformat()
    assert vencida.json()["situacao"] == "vencida"

    revogada = cliente.post(
        f"{PESSOAS}/pe-lara/autorizacoes/{vigente.json()['id']}/revogacao", headers=como(cabecalhos, "patricia")
    )
    assert revogada.status_code == 200
    assert revogada.json()["situacao"] == "revogada"
    [evento] = eventos(cadastro, "autorizacao_revogada")
    assert (evento["usuario_id"], evento["alvo_id"]) == ("patricia", "pe-lara")

    pessoa = cliente.get(f"{PESSOAS}/pe-lara", headers=como(cabecalhos, "ana")).json()
    assert sorted(a["situacao"] for a in pessoa["autorizacoes"]) == ["revogada", "vencida"]
    assert pessoa["autorizacao_imagem"] == "revogada"


def test_revogar_duas_vezes_409(cliente, cabecalhos, cadastro):
    aut = autorizar(cliente, cabecalhos).json()["id"]
    url = f"{PESSOAS}/pe-lara/autorizacoes/{aut}/revogacao"

    assert cliente.post(url, headers=como(cabecalhos, "ana")).status_code == 200
    assert cliente.post(url, headers=como(cabecalhos, "ana")).status_code == 409


def test_autorizacao_de_outra_pessoa_404(cliente, cabecalhos, cadastro):
    aut = autorizar(cliente, cabecalhos).json()["id"]

    resposta = cliente.post(f"{PESSOAS}/pe-miguel/autorizacoes/{aut}/revogacao", headers=como(cabecalhos, "admin"))

    assert resposta.status_code == 404


@pytest.mark.parametrize(
    "dados, status",
    [
        ({"valida_de": AMANHA.isoformat()}, 400),
        ({"valida_de": "2026-01-10", "valida_ate": "2026-01-01"}, 400),
        ({"tipo": "outro"}, 422),
        ({"documento_id": "d-de-ninguem"}, 400),
    ],
    ids=["inicio-futuro", "fim-antes-do-inicio", "tipo-invalido", "documento-inexistente"],
)
def test_autorizacao_invalida(cliente, cabecalhos, cadastro, dados, status):
    assert autorizar(cliente, cabecalhos, **dados).status_code == status


def test_autorizacao_aponta_documento_da_propria_pessoa(cliente, cabecalhos, cadastro, armazenamento):
    doc = enviar_documento(cliente, cabecalhos).json()["id"]

    assert autorizar(cliente, cabecalhos, documento_id=doc).json()["documento_id"] == doc
    assert autorizar(cliente, cabecalhos, pessoa="pe-miguel", usuario="admin", documento_id=doc).status_code == 400


def test_educadora_nao_registra_autorizacao(cliente, cabecalhos, cadastro):
    assert autorizar(cliente, cabecalhos, usuario="jessica").status_code == 403


# --- Uso de imagem -------------------------------------------------------------------


def usar_imagem(cliente, cabecalhos, pessoa_ids, uso="externo", usuario="jessica"):
    return cliente.post(USO_DE_IMAGEM, json={"pessoa_ids": pessoa_ids, "uso": uso}, headers=como(cabecalhos, usuario))


def test_uso_externo_liberado_com_autorizacao_vigente(cliente, cabecalhos, cadastro):
    autorizar(cliente, cabecalhos)

    resposta = usar_imagem(cliente, cabecalhos, ["pe-lara"])

    assert resposta.status_code == 200
    assert resposta.json() == {"liberado": True, "bloqueios": []}


@pytest.mark.parametrize("situacao", ["vencida", "revogada", "sem_autorizacao"])
def test_uso_externo_bloqueado_sem_autorizacao_vigente(cliente, cabecalhos, cadastro, situacao):
    if situacao == "vencida":
        autorizar(cliente, cabecalhos, valida_de="2025-01-01", valida_ate=ONTEM.isoformat())
    if situacao == "revogada":
        aut = autorizar(cliente, cabecalhos).json()["id"]
        cliente.post(f"{PESSOAS}/pe-lara/autorizacoes/{aut}/revogacao", headers=como(cabecalhos, "ana"))

    resposta = usar_imagem(cliente, cabecalhos, ["pe-lara"])

    assert resposta.status_code == 409
    detalhe = resposta.json()["detail"]
    assert detalhe["codigo"] == "uso_de_imagem_bloqueado"
    assert detalhe["bloqueios"] == [{"pessoa_id": "pe-lara", "nome": "Lara Oliveira", "motivo": situacao}]


def test_bloqueio_aponta_so_quem_nao_tem_autorizacao_vigente(cliente, cabecalhos, cadastro):
    autorizar(cliente, cabecalhos)
    sofia = cadastrar(cliente, cabecalhos).json()["id"]

    resposta = usar_imagem(cliente, cabecalhos, ["pe-lara", sofia])

    assert [b["pessoa_id"] for b in resposta.json()["detail"]["bloqueios"]] == [sofia]


def test_nova_autorizacao_vigente_libera_depois_de_revogada(cliente, cabecalhos, cadastro):
    antiga = autorizar(cliente, cabecalhos).json()["id"]
    cliente.post(f"{PESSOAS}/pe-lara/autorizacoes/{antiga}/revogacao", headers=como(cabecalhos, "ana"))
    autorizar(cliente, cabecalhos)

    assert usar_imagem(cliente, cabecalhos, ["pe-lara"]).status_code == 200


def test_uso_interno_nao_depende_de_autorizacao(cliente, cabecalhos, cadastro):
    assert usar_imagem(cliente, cabecalhos, ["pe-lara"], uso="interno").json()["liberado"] is True


def test_uso_de_imagem_de_pessoa_inexistente_404_e_de_outro_programa_403(cliente, cabecalhos, cadastro):
    assert usar_imagem(cliente, cabecalhos, ["pe-x"]).status_code == 404
    assert usar_imagem(cliente, cabecalhos, ["pe-miguel"]).status_code == 403


# --- Arquivo dos documentos no R2 (T-88) -----------------------------------------------

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def baixar_documento(cliente, cabecalhos, documento_id, pessoa="pe-lara", usuario="ana"):
    return cliente.get(f"{PESSOAS}/{pessoa}/documentos/{documento_id}/arquivo", headers=como(cabecalhos, usuario))


def contar_auditoria(banco, acao, usuario=None):
    with banco.connect() as c:
        return c.execute(
            sa.text("SELECT count(*) FROM log_auditoria WHERE acao = :a AND (CAST(:u AS text) IS NULL OR usuario_id = :u)"),
            {"a": acao, "u": usuario},
        ).scalar_one()


def test_documento_enviado_fica_no_armazenamento_e_o_banco_guarda_so_a_chave(cliente, cabecalhos, cadastro, armazenamento):
    resposta = enviar_documento(cliente, cabecalhos, tipo="Certidão de nascimento", nome="certidão lara.pdf")

    assert resposta.status_code == 201
    documento = resposta.json()
    assert (documento["tipo"], documento["tamanho"], documento["tem_arquivo"]) == ("Certidão de nascimento", len(PDF), True)
    [chave] = armazenamento.objetos
    assert chave.startswith("gestao/documentos/") and chave.endswith(".pdf")
    assert armazenamento.objetos[chave].conteudo == PDF
    with cadastro.connect() as c:
        guardado = c.execute(sa.text("SELECT chave_arquivo FROM documentos_pessoa WHERE id = :id"), {"id": documento["id"]}).scalar_one()
    assert guardado == chave


def test_download_autorizado_devolve_o_arquivo_e_fica_na_auditoria(cliente, cabecalhos, cadastro, armazenamento):
    documento_id = enviar_documento(cliente, cabecalhos, tipo="Foto 3x4", nome="foto.png", conteudo=PNG).json()["id"]

    resposta = baixar_documento(cliente, cabecalhos, documento_id, usuario="jessica")

    assert resposta.status_code == 200
    assert resposta.content == PNG
    assert resposta.headers["content-type"] == "image/png"
    assert resposta.headers["cache-control"] == "private, no-store"
    with cadastro.connect() as c:
        registro = c.execute(
            sa.text("SELECT usuario_id, alvo_tipo, alvo_id, detalhes->>'pessoa_id' FROM log_auditoria WHERE acao = 'download_documento'")
        ).one()
    assert tuple(registro) == ("jessica", "documento_pessoa", documento_id, "pe-lara")


@pytest.mark.parametrize("usuario", ["dora", "bruno", "rafael"], ids=["direcao", "outro-programa", "desligado"])
def test_sem_acesso_as_pessoas_do_programa_nao_baixa_e_a_tentativa_e_registrada(cliente, cabecalhos, cadastro, armazenamento, usuario):
    documento_id = enviar_documento(cliente, cabecalhos).json()["id"]

    assert baixar_documento(cliente, cabecalhos, documento_id, usuario=usuario).status_code == 403
    assert contar_auditoria(cadastro, "acesso_negado", usuario) == 1
    assert contar_auditoria(cadastro, "download_documento") == 0


@pytest.mark.parametrize(
    "conteudo, nome",
    [(b"MZ\x90\x00 executavel", "programa.exe"), (b"%PDF-1.4\n" + b"0" * (5 * 1024 * 1024), "grande.pdf"), (b"", "vazio.pdf")],
    ids=["tipo-nao-permitido", "acima-de-5mb", "vazio"],
)
def test_arquivo_de_tipo_nao_permitido_ou_acima_do_limite_400(cliente, cabecalhos, cadastro, armazenamento, conteudo, nome):
    resposta = enviar_documento(cliente, cabecalhos, nome=nome, conteudo=conteudo)

    assert resposta.status_code == 400
    assert armazenamento.objetos == {}
    assert cliente.get(f"{PESSOAS}/pe-lara", headers=como(cabecalhos, "ana")).json()["documentos"] == []


def test_documento_sem_tipo_400_sem_enviar_o_arquivo(cliente, cabecalhos, cadastro, armazenamento):
    resposta = enviar_documento(cliente, cabecalhos, tipo="  ")

    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Informe o tipo do documento."
    assert armazenamento.objetos == {}


def test_quem_so_consulta_nao_envia_documento(cliente, cabecalhos, cadastro, armazenamento):
    assert enviar_documento(cliente, cabecalhos, usuario="dora").status_code == 403
    assert armazenamento.objetos == {}


def test_documento_antigo_sem_arquivo_ou_de_outra_pessoa_404(cliente, cabecalhos, cadastro, armazenamento):
    with cadastro.begin() as c:
        c.execute(sa.text("INSERT INTO documentos_pessoa (id, pessoa_id, tipo, nome_arquivo) VALUES ('d-antigo', 'pe-lara', 'RG', 'rg.pdf')"))
    documento_id = enviar_documento(cliente, cabecalhos).json()["id"]

    antigo = baixar_documento(cliente, cabecalhos, "d-antigo")
    assert antigo.status_code == 404
    assert antigo.json()["detail"] == "Este documento foi registrado sem o arquivo."
    assert [d["tem_arquivo"] for d in cliente.get(f"{PESSOAS}/pe-lara", headers=como(cabecalhos, "ana")).json()["documentos"]] == [False, True]
    # O id de um documento da Lara não abre pelo cadastro do Miguel.
    assert baixar_documento(cliente, cabecalhos, documento_id, pessoa="pe-miguel", usuario="admin").status_code == 404


def test_sem_r2_configurado_503(cliente, cabecalhos, cadastro, monkeypatch):
    for nome in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"):
        monkeypatch.delenv(nome, raising=False)

    assert enviar_documento(cliente, cabecalhos).status_code == 503
