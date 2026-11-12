"""Paridade: a API do Financeiro responde igual com os dados em memória e no PostgreSQL.

Cada semente gera uma sequência aleatória (e reproduzível) de chamadas à API, do jeito
que as telas fazem: projetos, orçamentos, lançamentos com comprovante, aprovação,
rejeição, reenvio, importação do extrato, conciliação (com referência livre ou com item do
extrato), edição de orçamento, rascunhos, notificações, listas,
dashboard e relatório. Entram também as chamadas erradas: papel sem permissão, dado
inválido, lançamento de outra pessoa, decisões repetidas.

A mesma sequência roda duas vezes, uma com ``FINANCEIRO_ARMAZENAMENTO=memoria`` e outra
contra o banco, e as respostas (código HTTP e corpo) têm de ser idênticas. Ids e horários
mudam de uma rodada para outra, então são trocados por rótulos estáveis antes de comparar.

No banco, a rodada termina com um "reinício" (a memória do processo é esvaziada) e todas
as leituras têm de devolver exatamente o mesmo de antes.

``MDCA_SEMENTES_PARIDADE`` muda quantas sementes rodam (padrão: 8).
"""

import io
import os
import random
import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from Financeiro.comprovantes import ArmazenamentoEmMemoria
from Financeiro.extrato import caixa_do_extrato
from Financeiro.main import app
from Financeiro.notificacoes import caixa_de_notificacoes
from Financeiro.persistencia import VARIAVEL_ARMAZENAMENTO
from Financeiro.projetos import _projetos
from Financeiro.persistencia import AUDITORIA_EM_MEMORIA
from Financeiro.rascunhos import caixa_de_rascunhos
from Financeiro.routers.comprovantes import obter_armazenamento
from Financeiro.routers.orcamentos import _orcamentos

TOKEN = "token-de-teste-banco"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
SEMENTES = int(os.environ.get("MDCA_SEMENTES_PARIDADE", "8"))
OPERACOES = 80

client = TestClient(app)

# Ids com hífen (UUID) e sem hífen (o nome do arquivo do comprovante no R2).
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\b[0-9a-f]{32}\b")
EDUCADORES = ["marcos", "ana"]
CATEGORIAS = ["materiais", "transporte", "alimentação", "Oficinas e Eventos"]


def como(papel, usuario=None):
    headers = {"Authorization": f"Bearer {TOKEN}", "X-Papel-Usuario": papel}
    if usuario:
        headers["X-Usuario-Id"] = usuario
    return headers


class Normalizador:
    """Troca ids (UUID) por rótulos na ordem em que aparecem e horários por "<ts>"."""

    def __init__(self):
        self.rotulos = {}

    def _rotulo(self, achado):
        uid = achado.group(0)
        if uid not in self.rotulos:
            self.rotulos[uid] = f"#{len(self.rotulos)}"
        return self.rotulos[uid]

    def __call__(self, valor, chave=None):
        # Número do registro na trilha: sequência do banco x contador da memória.
        if chave == "id" and isinstance(valor, int):
            return "<id>"
        if chave == "quando":
            return "<ts>"
        if isinstance(valor, dict):
            return {k: self(v, k) for k, v in valor.items()}
        if isinstance(valor, list):
            return [self(v) for v in valor]
        if isinstance(valor, str):
            if chave and chave.endswith("_em"):
                return "<ts>"
            return UUID.sub(self._rotulo, valor)
        if chave and chave.endswith("_em") and valor is not None:
            return "<ts>"
        return valor


def _corpo(resposta):
    tipo = resposta.headers.get("content-type", "")
    if "spreadsheetml" in tipo:
        from openpyxl import load_workbook

        planilha = load_workbook(io.BytesIO(resposta.content), read_only=True)
        celulas = []
        for aba in planilha.worksheets:
            for linha in aba.iter_rows(values_only=True):
                celulas.append([str(c) if c is not None else None for c in linha])
        # O relatório traz a data e hora em que foi gerado.
        return [
            [re.sub(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}(:\d{2})?", "<agora>", c) if c else c for c in linha]
            for linha in celulas
        ]
    if "application/json" in tipo:
        return resposta.json()
    return resposta.text


class Rodada:
    """Executa um cenário e guarda (operação, status, corpo normalizado) de cada chamada."""

    def __init__(self):
        self.normalizar = Normalizador()
        self.registro = []
        self.projetos, self.orcamentos, self.lancamentos = [], [], []
        self.rascunhos = {u: [] for u in EDUCADORES}
        self.notificacoes = {u: [] for u in EDUCADORES}
        self.categorias = {}
        self.vigencias = {}
        # Lançamento -> (orçamento, autor), e os que foram rejeitados (para o reenvio).
        self.dono = {}
        self.rejeitados = []
        self.itens_extrato = []

    def chamar(self, nome, metodo, url, sem_ordem=False, **kwargs):
        resposta = getattr(client, metodo)(url, **kwargs)
        corpo = self.normalizar(_corpo(resposta))
        if sem_ordem and isinstance(corpo, list):
            corpo = sorted(corpo, key=repr)
        self.registro.append((nome, resposta.status_code, corpo))
        return resposta

    # --- Leituras: o retrato de tudo o que a API mostra ------------------------

    def retrato(self, etiqueta):
        coord, direcao = como("coordenacao", "luana"), como("direcao", "jane")
        self.chamar(f"{etiqueta}:projetos", "get", "/projetos", headers=coord)
        # Ordenado pelo id do projeto, que muda de uma rodada para outra.
        self.chamar(f"{etiqueta}:orcamentos", "get", "/orcamentos", sem_ordem=True, headers=coord)
        for orcamento_id in self.orcamentos:
            self.chamar(f"{etiqueta}:orcamento", "get", f"/orcamentos/{orcamento_id}", headers=coord)
        for projeto_id in self.projetos:
            self.chamar(
                f"{etiqueta}:orcamentos-do-projeto", "get", f"/orcamentos/projeto/{projeto_id}",
                params={"tamanho": 100}, headers=coord,
            )
        self.chamar(f"{etiqueta}:fila", "get", "/lancamentos", headers=coord)
        for filtro in ({"status": "pendente"}, {"status": "aprovado", "conciliado": "false"}, {"conciliado": "true"}):
            self.chamar(f"{etiqueta}:lancamentos{filtro}", "get", "/lancamentos", params=filtro, headers=coord)
        for usuario in EDUCADORES:
            self.chamar(f"{etiqueta}:meus", "get", "/lancamentos", headers=como("educador", usuario))
            self.chamar(f"{etiqueta}:notificacoes", "get", "/notificacoes", headers=como("educador", usuario))
            self.chamar(f"{etiqueta}:rascunhos", "get", "/rascunhos", headers=como("educador", usuario))
        for lancamento_id in self.lancamentos:
            self.chamar(f"{etiqueta}:lancamento", "get", f"/lancamentos/{lancamento_id}", headers=coord)
        for filtro in ({}, {"status": "ativo"}, {"data_inicio": "2026-03-01", "data_fim": "2026-06-30"}):
            self.chamar(f"{etiqueta}:dashboard{filtro}", "get", "/dashboard/projetos", params=filtro, headers=direcao)
        for filtro in ({}, {"em_aberto": "true"}, {"em_aberto": "false"}):
            self.chamar(f"{etiqueta}:extrato{filtro}", "get", "/extrato", params=filtro, headers=coord)
        # T-34: a trilha do Financeiro registra o mesmo nas duas formas de armazenamento.
        self.chamar(f"{etiqueta}:auditoria", "get", "/auditoria", params={"tamanho": 200}, headers=coord)
        for projeto_id in self.projetos:
            self.chamar(
                f"{etiqueta}:relatorio", "get", "/relatorios/prestacao-contas",
                params={"projeto_id": projeto_id, "data_inicio": "2026-01-01", "data_fim": "2026-12-31", "formato": "xlsx"},
                headers=coord,
            )

    # --- Cenário aleatório ----------------------------------------------------

    def cenario(self, semente):
        rng = random.Random(semente)
        coord = como("coordenacao", "luana")

        for i in range(rng.randint(1, 3)):
            r = self.chamar("criar-projeto", "post", "/projetos", json={"nome": f"Programa {semente}-{i}"}, headers=coord)
            self.projetos.append(r.json()["id"])
        # Nome repetido (sem diferenciar maiúsculas e acentos) e papel sem permissão.
        self.chamar("projeto-repetido", "post", "/projetos", json={"nome": f"PROGRAMA {semente}-0"}, headers=coord)
        self.chamar("projeto-educador", "post", "/projetos", json={"nome": "X"}, headers=como("educador", "marcos"))

        for i in range(rng.randint(1, 4)):
            self._criar_orcamento(rng, coord, i)

        acoes = [
            (self._lancar, 6), (self._aprovar, 4), (self._rejeitar, 3), (self._reenviar, 2),
            (self._conciliar, 2), (self._editar_orcamento, 2), (self._status_projeto, 1),
            (self._rascunho, 1), (self._completar_rascunho, 1), (self._ler_notificacao, 2),
            (self._criar_orcamento_extra, 1), (self._leitura_avulsa, 2), (self._importar_extrato, 1),
        ]
        funcoes = [f for f, peso in acoes for _ in range(peso)]
        for _ in range(OPERACOES):
            rng.choice(funcoes)(rng)

    def _criar_orcamento(self, rng, coord, i):
        projeto_id = rng.choice(self.projetos)
        inicio = date(2026, 1, 1) + timedelta(days=i * 7 + rng.randint(0, 6))
        fim = inicio + timedelta(days=rng.randint(60, 330))
        nomes = rng.sample(CATEGORIAS, rng.randint(1, len(CATEGORIAS)))
        total = rng.randint(500, 20000)
        if rng.random() < 0.5:
            corpo = {"categorias": [{"nome": n, "valor_orcado": round(total * rng.random() / len(nomes), 2)} for n in nomes]}
        else:
            corpo = {"categorias_despesa": nomes}
        r = self.chamar(
            "criar-orcamento", "post", "/orcamentos", headers=coord,
            json={"projeto_id": projeto_id, "valor_total": total, "data_inicio": inicio.isoformat(), "data_fim": fim.isoformat(), **corpo},
        )
        if r.status_code == 201:
            orcamento_id = r.json()["id"]
            self.orcamentos.append(orcamento_id)
            self.categorias[orcamento_id] = list(nomes)
            self.vigencias[orcamento_id] = (inicio, fim)

    def _criar_orcamento_extra(self, rng):
        self._criar_orcamento(rng, como("coordenacao", "luana"), len(self.orcamentos))
        # Inválidos: projeto inexistente, fim antes do início, soma das categorias acima do total.
        variante = rng.randint(0, 2)
        corpo = {"projeto_id": rng.choice(self.projetos), "valor_total": 100, "data_inicio": "2026-01-01",
                 "data_fim": "2026-12-31", "categorias_despesa": ["materiais"]}
        if variante == 0:
            corpo["projeto_id"] = "nao-existe"
        elif variante == 1:
            corpo["data_fim"] = "2025-12-31"
        else:
            corpo = {**corpo, "categorias_despesa": None, "categorias": [{"nome": "materiais", "valor_orcado": 101}]}
            del corpo["categorias_despesa"]
        self.chamar("orcamento-invalido", "post", "/orcamentos", json=corpo, headers=como("coordenacao", "luana"))

    def _dados_despesa(self, rng, orcamento_id):
        inicio, fim = self.vigencias[orcamento_id]
        dia = inicio + timedelta(days=rng.randint(0, (fim - inicio).days))
        if rng.random() < 0.1:
            dia = fim + timedelta(days=rng.randint(1, 30))  # fora da vigência: 400
        categoria = rng.choice(self.categorias[orcamento_id])
        if rng.random() < 0.05:
            categoria = "categoria-que-nao-existe"
        valor = f"{rng.randint(1, 300000) / 100:.2f}"
        if rng.random() < 0.05:
            valor = rng.choice(["0", "-5.00"])
        return {"valor": valor, "descricao": f"Despesa {rng.randint(1, 999)}", "categoria": categoria, "data_despesa": dia.isoformat()}

    def _lancar(self, rng):
        if not self.orcamentos:
            return
        orcamento_id = rng.choice(self.orcamentos + (["nao-existe"] if rng.random() < 0.05 else []))
        autor = rng.choice(EDUCADORES)
        dados = {"orcamento_id": orcamento_id}
        if orcamento_id in self.vigencias:
            dados.update(self._dados_despesa(rng, orcamento_id))
        else:
            dados.update({"valor": "10.00", "descricao": "x", "categoria": "materiais", "data_despesa": "2026-05-01"})
        arquivo = rng.choice([("nota.jpg", JPEG, "image/jpeg"), ("nota.png", PNG, "image/png")])
        files = {"comprovante": arquivo} if rng.random() > 0.05 else None
        r = self.chamar("lancar", "post", "/lancamentos", data=dados, files=files, headers=como("educador", autor))
        if r.status_code == 201:
            self.lancamentos.append(r.json()["id"])
            self.dono[r.json()["id"]] = (orcamento_id, autor)

    def _algum_lancamento(self, rng):
        if not self.lancamentos or rng.random() < 0.03:
            return "nao-existe"
        return rng.choice(self.lancamentos)

    def _aprovar(self, rng):
        papel = rng.choices(["coordenacao", "direcao", "educador", "voluntario_financeiro"], [5, 3, 1, 1])[0]
        self.chamar("aprovar", "patch", f"/lancamentos/{self._algum_lancamento(rng)}/aprovar", headers=como(papel, "decisor"))

    def _rejeitar(self, rng):
        papel = rng.choices(["coordenacao", "direcao", "educador"], [5, 3, 1])[0]
        motivo = rng.choice(["Nota ilegível", "Fora do escopo do projeto", "", "  ", "x" * 501])
        lancamento_id = self._algum_lancamento(rng)
        r = self.chamar(
            "rejeitar", "patch", f"/lancamentos/{lancamento_id}/rejeitar",
            json={"motivo": motivo}, headers=como(papel, "decisor"),
        )
        if r.status_code == 200:
            self.rejeitados.append(lancamento_id)

    def _reenviar(self, rng):
        # Na maior parte das vezes, quem reenvia é o autor de um rejeitado (o caminho
        # normal); no resto, lançamento qualquer e pessoa qualquer (404 e 409).
        if self.rejeitados and rng.random() < 0.8:
            lancamento_id = rng.choice(self.rejeitados)
            orcamento_id, autor = self.dono.get(lancamento_id, (rng.choice(self.orcamentos), "ana"))
        else:
            lancamento_id = self._algum_lancamento(rng)
            orcamento_id, autor = rng.choice(self.orcamentos), rng.choice(EDUCADORES)
        if orcamento_id not in self.vigencias:
            return
        dados = self._dados_despesa(rng, orcamento_id)
        files = {"comprovante": ("nova.jpg", JPEG, "image/jpeg")} if rng.random() < 0.5 else None
        r = self.chamar(
            "reenviar", "patch", f"/lancamentos/{lancamento_id}/reenviar",
            data=dados, files=files, headers=como("educador", autor),
        )
        if r.status_code == 200 and lancamento_id in self.rejeitados:
            self.rejeitados.remove(lancamento_id)

    def _importar_extrato(self, rng):
        # Linhas com poucas variações: reimportar repete itens (multiconjunto).
        linhas = [
            f"2026-{rng.randint(3, 5):02d}-{rng.randint(1, 3):02d};PIX {rng.randint(1, 3)};-{rng.randint(1, 3)}0,00"
            for _ in range(rng.randint(1, 4))
        ]
        if rng.random() < 0.1:
            linhas.append("ontem;PIX;1,00")  # linha inválida: 400 e nada entra
        papel = rng.choices(["voluntario_financeiro", "coordenacao", "educador"], [4, 1, 1])[0]
        csv = ("data;descricao;valor\n" + "\n".join(linhas) + "\n").encode()
        r = self.chamar(
            "importar-extrato", "post", "/extrato",
            files={"arquivo": ("extrato.csv", csv, "text/csv")}, headers=como(papel, "vera"),
        )
        if r.status_code == 201:
            self.itens_extrato += [i["id"] for i in r.json()["itens"]]

    def _conciliar(self, rng):
        papel = rng.choices(["voluntario_financeiro", "coordenacao"], [5, 1])[0]
        referencia = rng.choice(["ext-1", "ext-2", "ext-3", ""] + self.itens_extrato[-3:] * 2)
        self.chamar(
            "conciliar", "patch", f"/lancamentos/{self._algum_lancamento(rng)}/conciliar",
            json={"referencia_extrato": referencia}, headers=como(papel, "vera"),
        )

    def _editar_orcamento(self, rng):
        if not self.orcamentos:
            return
        orcamento_id = rng.choice(self.orcamentos)
        variante = rng.randint(0, 3)
        if variante == 0:
            corpo = {"valor_total": rng.randint(1, 30000)}
        elif variante == 1:
            nomes = rng.sample(CATEGORIAS, rng.randint(1, len(CATEGORIAS)))
            corpo = {"categorias_despesa": nomes}
        elif variante == 2:
            nomes = rng.sample(CATEGORIAS, rng.randint(1, len(CATEGORIAS)))
            corpo = {"categorias": [{"nome": n, "valor_orcado": rng.randint(0, 5000)} for n in nomes]}
        else:
            inicio, fim = self.vigencias[orcamento_id]
            corpo = {"data_fim": (fim + timedelta(days=rng.randint(-200, 60))).isoformat()}
        papel = rng.choices(["coordenacao", "direcao"], [6, 1])[0]
        r = self.chamar("editar-orcamento", "patch", f"/orcamentos/{orcamento_id}", json=corpo, headers=como(papel, "luana"))
        if r.status_code == 200:
            detalhe = r.json()
            self.categorias[orcamento_id] = list(detalhe["categorias_despesa"])
            self.vigencias[orcamento_id] = (date.fromisoformat(detalhe["data_inicio"]), date.fromisoformat(detalhe["data_fim"]))

    def _status_projeto(self, rng):
        status = rng.choice(["ativo", "encerrado", "pausado"])
        papel = rng.choice(["coordenacao", "direcao", "educador"])
        projeto_id = rng.choice(self.projetos + ["nao-existe"])
        self.chamar("status-projeto", "patch", f"/projetos/{projeto_id}/status", json={"status": status}, headers=como(papel, "luana"))

    def _rascunho(self, rng):
        autor = rng.choice(EDUCADORES)
        files = {"comprovante": ("foto.jpg", JPEG, "image/jpeg")} if rng.random() > 0.1 else None
        r = self.chamar("rascunho", "post", "/rascunhos", files=files, headers=como("educador", autor))
        if r.status_code == 201:
            self.rascunhos[autor].append(r.json()["id"])

    def _completar_rascunho(self, rng):
        autor = rng.choice(EDUCADORES)
        pendentes = self.rascunhos[autor] + self.rascunhos[EDUCADORES[1 - EDUCADORES.index(autor)]][:1]
        if not pendentes or not self.orcamentos:
            return
        rascunho_id = rng.choice(pendentes)
        orcamento_id = rng.choice(self.orcamentos)
        r = self.chamar(
            "completar-rascunho", "post", f"/rascunhos/{rascunho_id}/completar",
            data={"orcamento_id": orcamento_id, **self._dados_despesa(rng, orcamento_id)},
            headers=como("educador", autor),
        )
        if r.status_code == 201:
            self.rascunhos[autor].remove(rascunho_id)
            self.lancamentos.append(r.json()["id"])
            self.dono[r.json()["id"]] = (orcamento_id, autor)

    def _ler_notificacao(self, rng):
        usuario = rng.choice(EDUCADORES)
        lista = client.get("/notificacoes", headers=como("educador", usuario)).json()
        if not lista:
            return
        alvo = rng.choice(lista)["id"]
        # Às vezes é a outra pessoa tentando marcar a notificação: 404.
        quem = usuario if rng.random() > 0.35 else EDUCADORES[1 - EDUCADORES.index(usuario)]
        self.chamar("ler-notificacao", "patch", f"/notificacoes/{alvo}/lida", headers=como("educador", quem))

    def _leitura_avulsa(self, rng):
        if rng.random() < 0.5 and self.lancamentos:
            self.chamar("ler-lancamento", "get", f"/lancamentos/{rng.choice(self.lancamentos)}", headers=como("educador", "ana"))
        else:
            self.chamar("fila-pendentes", "get", "/lancamentos", params={"status": "pendente"}, headers=como("coordenacao"))


def _esvaziar_memoria():
    """O equivalente a reiniciar a API: some tudo o que estava só no processo."""
    _projetos.clear()
    _orcamentos.clear()
    caixa_de_notificacoes.limpar()
    caixa_de_rascunhos.limpar()
    caixa_do_extrato.limpar()
    AUDITORIA_EM_MEMORIA.clear()


def _preparar_memoria(monkeypatch):
    monkeypatch.setenv(VARIAVEL_ARMAZENAMENTO, "memoria")
    _esvaziar_memoria()


def _preparar_banco(monkeypatch, motor):
    import sqlalchemy as sa

    monkeypatch.delenv(VARIAVEL_ARMAZENAMENTO, raising=False)
    with motor.begin() as conexao:
        conexao.execute(sa.text("TRUNCATE projetos, rascunhos_lancamento, extrato_itens CASCADE"))
    _esvaziar_memoria()


def _rodar(semente, monkeypatch, motor=None):
    armazenamento = ArmazenamentoEmMemoria()
    app.dependency_overrides[obter_armazenamento] = lambda: armazenamento
    if motor is None:
        _preparar_memoria(monkeypatch)
    else:
        _preparar_banco(monkeypatch, motor)
    rodada = Rodada()
    rodada.cenario(semente)
    rodada.retrato("final")
    return rodada


def _comparar(memoria, banco):
    assert len(memoria) == len(banco)
    for i, (m, b) in enumerate(zip(memoria, banco)):
        assert m == b, f"chamada {i} ({m[0]}) diferente:\nmemória: {m[1]} {m[2]}\nbanco:   {b[1]} {b[2]}"


@pytest.mark.parametrize("semente", range(SEMENTES))
def test_mesmo_cenario_responde_igual_na_memoria_e_no_banco(semente, banco_financeiro, monkeypatch):
    memoria = _rodar(semente, monkeypatch)
    banco = _rodar(semente, monkeypatch, banco_financeiro)

    _comparar(memoria.registro, banco.registro)
    # O retrato final tem de ler dados de verdade, não respostas 401/403.
    assert all(status == 200 for nome, status, _ in banco.registro if nome.startswith("final:"))
    # O cenário precisa ter exercitado de verdade as decisões, não só erros.
    codigos = {(nome, status) for nome, status, _ in banco.registro}
    assert ("lancar", 201) in codigos


@pytest.mark.parametrize("semente", range(SEMENTES))
def test_banco_devolve_o_mesmo_depois_de_reiniciar(semente, banco_financeiro, monkeypatch):
    rodada = _rodar(semente, monkeypatch, banco_financeiro)
    antes = [r for r in rodada.registro if r[0].startswith("final:")]

    _esvaziar_memoria()
    rodada.registro = []
    rodada.retrato("final")
    depois = rodada.registro

    # Gerar o relatório grava na auditoria (T-34): o segundo retrato vê, no topo da
    # trilha, os relatórios gerados pelo primeiro. Fora isso, a trilha tem de ser igual.
    def sem_auditoria(registro):
        return [r for r in registro if r[0] != "final:auditoria"]

    _comparar(sem_auditoria(antes), sem_auditoria(depois))
    [(_, _, trilha_antes)] = [r for r in antes if r[0] == "final:auditoria"]
    [(_, _, trilha_depois)] = [r for r in depois if r[0] == "final:auditoria"]
    novos = trilha_depois["itens"][: len(trilha_depois["itens"]) - len(trilha_antes["itens"])]
    assert {i["codigo"] for i in novos} <= {"gerar_relatorio"}
    assert len(novos) == len(rodada.projetos)
    assert trilha_depois["itens"][len(novos):] == trilha_antes["itens"]


def test_cenarios_cobrem_os_caminhos_de_sucesso_e_de_erro(banco_financeiro, monkeypatch):
    """Garante que as sementes não estão testando só o caminho feliz (nem só erros)."""
    vistos = set()
    for semente in range(SEMENTES):
        rodada = _rodar(semente, monkeypatch, banco_financeiro)
        vistos |= {(nome, status) for nome, status, _ in rodada.registro}
    esperados = {
        ("lancar", 201), ("lancar", 400), ("aprovar", 200), ("aprovar", 409), ("aprovar", 403),
        ("rejeitar", 200), ("rejeitar", 400), ("reenviar", 200), ("reenviar", 404), ("reenviar", 409),
        ("conciliar", 200), ("completar-rascunho", 201), ("ler-notificacao", 200), ("ler-notificacao", 404),
        ("conciliar", 409), ("editar-orcamento", 200), ("editar-orcamento", 400),
        ("rascunho", 201), ("projeto-repetido", 409), ("orcamento-invalido", 400),
        ("importar-extrato", 201), ("importar-extrato", 403),
    }
    assert esperados <= vistos, f"faltaram: {sorted(esperados - vistos)}"
