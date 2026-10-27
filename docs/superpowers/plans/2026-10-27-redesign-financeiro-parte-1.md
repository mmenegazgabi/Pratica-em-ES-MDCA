# Redesign do Financeiro — Parte 1 · Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar o celular do educador redesenhado (fotografa agora, completa depois) e, no computador, a estrutura nova com Início, Lançamentos (com painel de aprovação), Projetos e Detalhe do projeto — tudo ligado ao backend.

**Architecture:** Backend FastAPI em memória (`Backend/Financeiro/`) ganha listagem de lançamentos, rascunhos, reenvio de rejeitada e edição de orçamento. Frontend continua HTML/CSS/JS puro em módulos ES, sem build: uma base comum (`Frontend/Financeiro/base/`), o app do celular em `lancamento/` e o app do computador em `index.html` + `app.js` + `telas/`. Regras sem DOM ficam em arquivos `*-dados.js` testados com `node --test`; arquivos de tela só montam DOM.

**Tech Stack:** Python 3 + FastAPI + pytest; JavaScript ES modules + `node --test`; fonte Inter (Google Fonts); ícones Lucide inline (SVG).

**Spec:** `docs/superpowers/specs/2026-10-27-redesign-financeiro-design.md` (esboços em `docs/superpowers/specs/2026-10-27-redesign-financeiro/`)

**Fora desta parte (Parte 2):** extrato bancário, tela de Conciliação, Relatórios. Tela Acessos espera a US-08.

**Branch:** `feature/redesign-financeiro-parte-1`, criada a partir de `main` depois do merge do PR da T-21; se ainda não tiver sido mergeado, criar a partir de `feature/T-21-US-05-marcar-conciliado` (a listagem expõe `conciliado`).

## Global Constraints

- Backend: rodar testes com `cd Backend/Financeiro && .venv/bin/python -m pytest -q`. Frontend: `cd Frontend/Financeiro && node --test`.
- Autenticação provisória continua: `Authorization: Bearer <token>`, `X-Papel-Usuario`, `X-Usuario-Id`. CORS só permite GET, POST, PATCH, OPTIONS — não usar PUT/DELETE.
- Repositório público: nenhum token no código.
- Visual "B · Neutro e funcional": fundo `#fff`; bordas `#e4e4e7`; texto `#18181b`, secundário `#71717a`; verde de ação `#3f8a3a`; item ativo fundo `#ecf5ea` texto `#1f4d1c`; fonte Inter; raio 6–8 px, sem pílulas; sem emojis; ícones Lucide de traço fino; números com `font-variant-numeric: tabular-nums`, alinhados à direita em tabelas.
- Status (etiqueta pequena, fundo claro): pendente `#854d0e`/`#fef9c3`; aprovado `#1f4d1c`/`#ecf5ea`; rejeitado `#991b1b`/`#fee2e2`; conciliado `#1e40af`/`#dbeafe`. Barras de uso: verde < 80%, amarelo `#ca8a04` de 80% a 99,99%, vermelho `#dc2626` em ≥ 100% (vem de `nivel_alerta`).
- Celular: campos com 16 px, área de toque ≥ 44 px, sem rolagem horizontal em 320 px; fotos reduzidas no aparelho antes do envio (regras atuais de `formulario.js`).
- Texto vindo do usuário (descrição, motivo, nome) entra no DOM só por `textContent` / o helper `el()` — nunca `innerHTML`.
- Textos da interface em português, no tom dos esboços ("Fotografar comprovante", "Enviar para aprovação", "Corrigir e reenviar", "Nada pendente").

## Review Focus

1. Educador pedindo `GET /lancamentos` sem filtro → recebe só os próprios; sem `X-Usuario-Id` → 400. (Task 1)
2. Alguém completando ou listando rascunho de outra pessoa → 404, e o rascunho continua lá. (Task 2)
3. Reenviar despesa que não está rejeitada, ou de outro autor → 409 / 404, sem alterar nada; reenvio com dados inválidos mantém o status "rejeitado". (Task 3)
4. Editar orçamento para valor abaixo do já gasto, ou removendo categoria com lançamento → 400. (Task 4) Criar orçamento para projeto que não existe → 400 e nada criado. (Task 5)
5. Soma de valores em reais com centavos (ex.: 0,10 + 0,20) nos totais das telas → `R$ 0,30`, sem erro de ponto flutuante. (Task 6, `somarReais`)

---

### Task 1: Listagem de lançamentos com filtros

**Files:**
- Modify: `Backend/Financeiro/orcamento.py` (campos `criado_em`, `aprovado_em` em `Lancamento`; `aprovar_lancamento` preenche `aprovado_em`)
- Modify: `Backend/Financeiro/routers/lancamentos.py` (rota `GET /lancamentos`, modelo `LancamentoResumo`)
- Test: `Backend/Financeiro/tests/test_listar_lancamentos.py`

**Interfaces:**
- Produces: `GET /lancamentos?status=<pendente|aprovado|rejeitado>&orcamento_id=<id>&conciliado=<bool>&meus=<bool>` → `List[LancamentoResumo]`, mais recentes primeiro (`criado_em` desc).
  `LancamentoResumo = {id, orcamento_id, projeto_id, valor, descricao, categoria, data_despesa, status, status_descricao, autor_id, motivo_rejeicao, conciliado, referencia_extrato, comprovante_url, criado_em, aprovado_em}`.
- `Lancamento.criado_em: datetime` (UTC, default agora), `Lancamento.aprovado_em: Optional[datetime]`.
- Regra de acesso: papel `educador` (cabeçalho `X-Papel-Usuario`) sempre filtra por `autor_id == X-Usuario-Id`; `meus=true` faz o mesmo para qualquer papel. Nos dois casos, sem `X-Usuario-Id` → 400 "Identificação do usuário obrigatória.".

- [ ] **Step 1: Write the failing tests** (mesmo esquema de `cabecalhos()` de `test_notificacoes.py`)

```python
def test_lista_todos_mais_recentes_primeiro(): ...          # 3 lançamentos → ordem por criado_em desc
def test_filtra_por_status():                               # ?status=pendente → só pendentes
def test_filtra_por_orcamento_e_conciliado():               # ?orcamento_id=o1&conciliado=false
def test_educador_ve_so_os_proprios():                      # papel=educador, usuario=marcos → só autor_id == "marcos"
def test_educador_sem_usuario_recebe_400():
def test_meus_true_filtra_pelo_usuario_em_qualquer_papel():
def test_status_invalido_retorna_422():
def test_aprovar_preenche_aprovado_em():                    # PATCH /aprovar → item listado com aprovado_em != None
def test_resumo_traz_projeto_e_comprovante_url():           # projeto_id do orçamento; comprovante_url == f"/{chave}"
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_listar_lancamentos.py` — Expected: FAIL (405/404 na rota).
- [ ] **Step 3: Implement** — `status: Optional[StatusLancamento]` como Query (FastAPI devolve 422 sozinho); papel lido com `Header(None, alias=CABECALHO_PAPEL)` normalizado como em `exigir_papel`; percorre `_orcamentos`. Declarar a rota antes de `GET /{lancamento_id}`.
- [ ] **Step 4: Run** a suíte inteira — Expected: todos passam.
- [ ] **Step 5: Commit** `feat(financeiro): GET /lancamentos com filtros para as telas do redesign`

---

### Task 2: Rascunhos de despesa (foto agora, dados depois)

**Files:**
- Create: `Backend/Financeiro/rascunhos.py` (dataclass `Rascunho` + `CaixaDeRascunhos` em memória, com lock)
- Create: `Backend/Financeiro/routers/rascunhos.py`
- Modify: `Backend/Financeiro/routers/lancamentos.py` (extrair `_receber_comprovante` e `_criar_lancamento` do `criar_lancamento` atual, sem mudar o comportamento de `POST /lancamentos`)
- Modify: `Backend/Financeiro/main.py`, `Backend/main.py` (incluir o router)
- Test: `Backend/Financeiro/tests/test_rascunhos.py`

**Interfaces:**
- `Rascunho(autor_id: str, comprovante_chave: str, nome_original: str, content_type: str, tamanho: int, id: str = uuid4, criado_em: datetime = agora)`.
- `CaixaDeRascunhos.criar(r) -> Rascunho`, `.do_autor(autor_id) -> list[Rascunho]` (mais recente primeiro), `.retirar(id, autor_id) -> Rascunho` (remove e devolve; `RascunhoNaoEncontrado` se não existe ou é de outro autor). Instância global `caixa_de_rascunhos`.
- `async _receber_comprovante(comprovante: Optional[UploadFile], armazenamento) -> tuple[str, str, str, int]` → `(chave, content_type, nome_original, tamanho)`; levanta as mesmas HTTPException de hoje (400 "Comprovante obrigatório.", 400/413 tipo/tamanho, 503).
- Rotas (todas exigem token; autor via `exigir_usuario`):
  - `POST /rascunhos` (multipart `comprovante`) → 201 `RascunhoSaida {id, criado_em, comprovante_url, nome_original, content_type, tamanho}`
  - `GET /rascunhos` → `List[RascunhoSaida]` só do autor
  - `POST /rascunhos/{id}/completar` (form `orcamento_id, valor, descricao, categoria, data_despesa`) → 201 `LancamentoCriado` (mesmo modelo de `POST /lancamentos`), status pendente, `autor_id` = autor, reaproveita a chave da foto; remove o rascunho. Rascunho de outro autor/inexistente → 404 "Rascunho não encontrado". Dados inválidos → 400 e o rascunho **continua** existindo.
- Rascunho não aparece em `GET /lancamentos` nem afeta saldo.

- [ ] **Step 1: Write the failing tests**

```python
def test_criar_rascunho_salva_foto_e_devolve_201():
def test_criar_rascunho_sem_foto_retorna_400():
def test_criar_rascunho_sem_usuario_retorna_400():
def test_listar_mostra_so_os_do_autor():                       # marcos e ana criam; marcos vê 1
def test_completar_cria_lancamento_pendente_com_mesma_foto():  # comprovante.chave == rascunho chave; status "pendente"
def test_completar_remove_o_rascunho():
def test_completar_rascunho_de_outro_autor_retorna_404_e_mantem():
def test_completar_com_categoria_invalida_retorna_400_e_mantem():
def test_rascunho_nao_aparece_em_listar_lancamentos_nem_no_saldo():
def test_post_lancamentos_continua_igual():                   # a suíte test_lancamentos.py segue passando
```

Use o `ArmazenamentoComprovantes` falso que `test_lancamentos.py` já usa (override de `obter_armazenamento`).

- [ ] **Step 2: Run** `pytest -q tests/test_rascunhos.py` — Expected: FAIL (404).
- [ ] **Step 3: Implement** as interfaces acima. Completar = `orcamento.validar_lancamento` → `retirar` → `registrar_lancamento`, nessa ordem, para o rascunho só sumir quando os dados são válidos.
- [ ] **Step 4: Run** a suíte inteira — Expected: todos passam.
- [ ] **Step 5: Commit** `feat(financeiro): rascunhos de despesa (fotografa agora, completa depois)`

---

### Task 3: Corrigir e reenviar despesa rejeitada

**Files:**
- Modify: `Backend/Financeiro/orcamento.py` (campo `motivos_rejeicao_anteriores: list[str]`; método `reenviar_lancamento`; exceção reaproveita `AprovacaoInvalida`)
- Modify: `Backend/Financeiro/routers/lancamentos.py` (rota `PATCH /lancamentos/{id}/reenviar`)
- Test: `Backend/Financeiro/tests/test_reenviar_lancamento.py`

**Interfaces:**
- `Orcamento.reenviar_lancamento(lancamento_id: str, *, valor: float, descricao: str, categoria: str, data_despesa: date, comprovante_chave: Optional[str]) -> Lancamento`: só de `REJEITADO` (senão `AprovacaoInvalida("Só despesas rejeitadas podem ser reenviadas")`); valida com `validar_lancamento` antes de mudar qualquer campo; move `motivo_rejeicao` para o fim de `motivos_rejeicao_anteriores`, zera `motivo_rejeicao`, status → `PENDENTE`, `criado_em` → agora; troca a chave só se veio foto nova.
- `PATCH /lancamentos/{id}/reenviar` multipart: `valor, descricao, categoria, data_despesa` obrigatórios; `comprovante` opcional (se vier, passa por `_receber_comprovante`). Exige `exigir_usuario`; autor diferente de `autor_id` → 404 "Lançamento não encontrado" (não revela existência). Resposta: `LancamentoDetalhe` (ganha `motivos_rejeicao_anteriores: list[str]`).
- O projeto/orçamento da despesa não muda no reenvio.

- [ ] **Step 1: Write the failing tests**

```python
def test_reenviar_rejeitada_volta_para_pendente_e_guarda_motivo_anterior():
    # motivo_rejeicao None; motivos_rejeicao_anteriores == ["Nota ilegível"]
def test_reenviar_sem_foto_mantem_comprovante():
def test_reenviar_com_foto_troca_comprovante():
def test_reenviar_pendente_ou_aprovada_retorna_409_sem_mudar():
def test_reenviar_de_outro_autor_retorna_404():
def test_reenviar_com_valor_invalido_retorna_400_e_continua_rejeitada():
def test_rejeitar_de_novo_depois_do_reenvio_acumula_motivos():
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** conforme interfaces.
- [ ] **Step 4: Run** a suíte inteira — Expected: todos passam.
- [ ] **Step 5: Commit** `feat(financeiro): reenviar despesa rejeitada após correção`

---

### Task 4: Editar orçamento

**Files:**
- Modify: `Backend/Financeiro/orcamento.py` (método `Orcamento.editar`)
- Modify: `Backend/Financeiro/routers/orcamentos.py` (rota `PATCH /orcamentos/{id}`)
- Test: `Backend/Financeiro/tests/test_editar_orcamento.py`

**Interfaces:**
- `Orcamento.editar(*, valor_total: float, data_inicio: date, data_fim: date, categorias_despesa: list[str]) -> None` — sob o lock; recalcula `saldo_atual = valor_total - realizado`. Erros (`LancamentoInvalido`, mensagem exata):
  - `valor_total < realizado` → "O valor total não pode ser menor que o já gasto (R$ X)." (`formatar_reais` de `notificacoes.py`)
  - `data_fim < data_inicio` → "data_fim não pode ser anterior a data_inicio"
  - categoria removida com lançamento não rejeitado → "A categoria \"<nome>\" tem lançamentos e não pode ser removida."
  - lista vazia → "Informe ao menos uma categoria."
- `PATCH /orcamentos/{id}` com corpo `OrcamentoCreate` sem `projeto_id` (novo modelo `OrcamentoEdicao`); papel `coordenacao` (`exigir_papel(Papel.COORDENACAO)`; direção recebe 403); resposta `OrcamentoDetalhe`.

- [ ] **Step 1: Write the failing tests** — um teste por erro acima, mais `test_editar_atualiza_valor_e_saldo`, `test_direcao_recebe_403`, `test_orcamento_inexistente_404`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** a suíte inteira — Expected: todos passam.
- [ ] **Step 5: Commit** `feat(financeiro): PATCH /orcamentos/{id} para editar orçamento`

---

### Task 5: Cadastro de projetos e orçamento só para projeto existente

**Files:**
- Create: `Backend/Financeiro/projetos.py` (dataclass `Projeto` + registro em memória `_projetos`, com lock)
- Create: `Backend/Financeiro/routers/projetos.py`
- Modify: `Backend/Financeiro/routers/orcamentos.py` (`POST /orcamentos` valida o projeto)
- Modify: `Backend/Financeiro/main.py`, `Backend/main.py` (incluir o router)
- Modify: `Backend/Financeiro/tests/test_orcamento.py` (os testes que criam orçamento passam a criar o projeto antes)
- Test: `Backend/Financeiro/tests/test_projetos.py`

**Interfaces:**
- `Projeto(nome: str, id: str = uuid4, criado_em: datetime = agora)`.
- `buscar_projeto(projeto_id: str) -> Optional[Projeto]`; `registrar_projeto(nome: str) -> Projeto` — nome sem espaços nas pontas, 1 a 120 caracteres, único sem diferenciar maiúsculas/acentos (`LancamentoInvalido`-like: `ProjetoInvalido` com as mensagens abaixo).
- `POST /projetos` `{nome}` → 201 `ProjetoSaida {id, nome}`; só `coordenacao` (`exigir_papel`); nome vazio → 400 "Informe o nome do projeto."; repetido → 409 "Já existe um projeto com esse nome."
- `GET /projetos` → `List[ProjetoSaida]` em ordem alfabética; qualquer papel autenticado.
- `POST /orcamentos` com `projeto_id` que não existe → **400 "Projeto não encontrado. Cadastre o projeto antes de criar o orçamento."** e nada é criado. Orçamentos já existentes em memória não são revalidados.
- `GET /orcamentos` e `OrcamentoDetalhe` ganham `projeto_nome: Optional[str]` (nome do registro, `None` se o projeto não existir mais).
- *Decisão do plano (combinar com o time de Gestão):* o registro de projetos fica no Financeiro, em memória como o resto, até existir o cadastro compartilhado (a tabela `projetos` em `Backend/Shared/migrations` é só um esboço). Quando o compartilhado existir, `buscar_projeto` passa a consultá-lo e a regra do `POST /orcamentos` continua igual.

- [ ] **Step 1: Write the failing tests**

```python
def test_criar_orcamento_para_projeto_inexistente_retorna_400_e_nao_cria():
    resposta = client.post("/orcamentos", json={**ORCAMENTO, "projeto_id": "nao-existe"}, headers=cabecalhos())
    assert resposta.status_code == 400
    assert resposta.json()["detail"] == "Projeto não encontrado. Cadastre o projeto antes de criar o orçamento."
    assert _orcamentos == []
def test_criar_orcamento_para_projeto_existente_retorna_201_com_nome():
def test_criar_projeto_coordenacao_201():
def test_criar_projeto_outros_papeis_403():
def test_criar_projeto_nome_vazio_400():
def test_criar_projeto_nome_repetido_409():          # "Leitura" e " leitura " colidem
def test_listar_projetos_em_ordem_alfabetica():
```

- [ ] **Step 2: Run** `pytest -q tests/test_projetos.py` — Expected: FAIL.
- [ ] **Step 3: Implement** conforme interfaces; limpar `_projetos` nas fixtures `ambiente` que já limpam `_orcamentos`.
- [ ] **Step 4: Run** a suíte inteira — Expected: todos passam.
- [ ] **Step 5: Commit** `feat(financeiro): orçamento só pode ser criado para projeto cadastrado`

---

### Task 6: Base do frontend (visual B, sessão, API, formatação)

**Files:**
- Create: `Frontend/Financeiro/base/tokens.css` — variáveis da linha B (Global Constraints) + `@import` da Inter.
- Create: `Frontend/Financeiro/base/componentes.css` — `.btn` (`--sec`, `--perigo`, `--pequeno`), `.caixa`, `.tabela`, `.etiqueta` (`--pendente/--aprovado/--rejeitado/--conciliado`), `.filtro` (aba com contagem), `.barra-uso` (`--alerta/--critica`), `.campo`, `.entrada`, `.painel-lateral`, `.dialogo`, `.vazio`. Valores visuais = `docs/superpowers/specs/2026-10-27-redesign-financeiro/telas-computador.html`.
- Create: `Frontend/Financeiro/base/icones.js` — `icone(nome: string): SVGElement` para: `inicio, lancamentos, projetos, relatorios, auditoria, camera, galeria, fechar, voltar, seta, mais, sino, perfil, calendario, envio`.
- Create: `Frontend/Financeiro/base/dom.js` — `el(tag, atributos = {}, ...filhos): HTMLElement` (strings viram `textContent`), `limpar(no)`.
- Create: `Frontend/Financeiro/base/formatar.js`
- Create: `Frontend/Financeiro/base/sessao.js`
- Create: `Frontend/Financeiro/base/api.js` — substitui `lancamento/api.js` (mover `API_PADRAO`, `TOKEN_FIXO`, token/servidor em `localStorage`, `requisitar`); cabeçalhos passam a vir da sessão.
- Modify: `Frontend/Financeiro/lancamento/formulario.js` — `formatarMoeda` passa a reexportar de `base/formatar.js`.
- Delete: `Frontend/Financeiro/lancamento/api.js` (importadores apontam para `../base/api.js`).
- Test: `Frontend/Financeiro/tests/formatar.test.js`, `tests/sessao.test.js`, `tests/api.test.js`

**Interfaces:**
- `formatar.js`: `formatarMoeda(valor: number): string` ("R$ 1.234,50"); `somarReais(valores: number[]): number` (soma em centavos inteiros); `formatarData(iso: string): string` ("26/10/2026"); `formatarDataCurta(iso): string` ("26/10"); `diasDesde(isoDataHora: string, agora = new Date()): number` (inteiro, ≥ 0); `tempoRelativo(isoDataHora, agora): string` ("hoje", "há 1 dia", "há 3 dias").
- `sessao.js`: `PAPEIS = {coordenacao: "Coordenação", direcao: "Diretoria", voluntario_financeiro: "Voluntário financeiro", educador: "Educador"}`; `lerSessao(): {papel, nome} | null`; `salvarSessao({papel, nome})`; `encerrarSessao()`; `usuarioId(nome): string` (nome em minúsculas, sem acento, espaços → "-"); `itensDeMenu(papel): Array<{id, rotulo, icone, rota}>`:
  - coordenacao → inicio, lancamentos, projetos
  - direcao → inicio, projetos
  - voluntario_financeiro → inicio, lancamentos
  - educador → [] (usa o celular)
  (Relatórios, Conciliação e Auditoria entram na Parte 2.)
- `api.js`: `requisitar(caminho, opcoes) -> Promise<{status, corpo}>` (status 0 = sem conexão), envia `Authorization`, `X-Papel-Usuario` e `X-Usuario-Id` da sessão; mantém `urlDaApi, tokenSalvo, salvarAcesso, esquecerAcesso, API_PADRAO`. Funções: `listarProjetos()`, `criarProjeto(nome)`, `criarOrcamento(dados)`, `listarOrcamentos(vigentesEm?)`, `obterOrcamento(id)`, `editarOrcamento(id, dados)`, `listarLancamentos(filtros)`, `obterLancamento(id)`, `aprovarLancamento(id)`, `rejeitarLancamento(id, motivo)`, `criarRascunho(arquivo)`, `listarRascunhos()`, `completarRascunho(id, formData)`, `reenviarLancamento(id, formData)`, `listarNotificacoes()`, `marcarNotificacaoLida(id)`.

- [ ] **Step 1: Write the failing tests**

```js
test("somarReais evita erro de ponto flutuante", () => assert.equal(somarReais([0.1, 0.2]), 0.3));
test("formatarMoeda", () => assert.equal(formatarMoeda(1234.5).replace(/\s/g, " "), "R$ 1.234,50"));
test("diasDesde conta dias inteiros", ...)               // 2026-10-20T10:00Z → agora 2026-10-27T09:00Z → 6
test("tempoRelativo", ...)                               // "hoje", "há 1 dia", "há 3 dias"
test("usuarioId normaliza o nome", () => assert.equal(usuarioId(" Marcos Vieira "), "marcos-vieira"));
test("itensDeMenu por papel", ...)                       // ids exatamente como na lista acima
test("api envia papel e usuário da sessão", ...)        // globalThis.fetch falso + localStorage falso
test("api devolve status 0 sem conexão", ...)
```

- [ ] **Step 2: Run** `node --test` — Expected: FAIL (módulos não existem).
- [ ] **Step 3: Implement** os módulos; atualizar imports em `lancamento/lancamento.js` e testes existentes.
- [ ] **Step 4: Run** `node --test` — Expected: todos passam (inclusive os antigos).
- [ ] **Step 5: Commit** `feat(front-financeiro): base visual B, sessão e cliente da API`

---

### Task 7: Celular — Minhas despesas, câmera, completar, rejeitada

**Files:**
- Rewrite: `Frontend/Financeiro/lancamento/index.html`, `lancamento.css`, `lancamento.js` (usa `../base/*`)
- Create: `Frontend/Financeiro/lancamento/despesas-dados.js`
- Modify: `Frontend/Financeiro/lancamento/formulario.js` — `validarFormulario(dados, { exigirArquivo = true } = {})`; `montarFormDataDados(dados)` sem a foto (para completar/reenviar), mantendo `montarFormData` antigo.
- Modify: `docs/lancamento-celular.md` (descrever o fluxo novo)
- Test: `Frontend/Financeiro/tests/despesas-dados.test.js`, ajustar `tests/lancamento-formulario.test.js`

**Interfaces:**
- `agruparDespesas(lancamentos, rascunhos) -> {ajuste: Lancamento[], aCompletar: Rascunho[], enviadas: Lancamento[]}` — `ajuste` = status `rejeitado`; `enviadas` = demais, no máximo 5, mais recentes primeiro; `aCompletar` na ordem recebida.
- `ultimoProjetoUsado(lancamentos) -> orcamento_id | null` (do mais recente).
- Telas (uma página, trocadas por `location.hash`): `#/` Minhas despesas · `#/completar/<rascunhoId>` · `#/despesa/<lancamentoId>` (rejeitada: motivo em destaque + "Corrigir e reenviar" abre o mesmo formulário preenchido) · `#/avisos` (`GET /notificacoes`, marcar como lida ao abrir) · `#/perfil` (nome, código de acesso, servidor avançado, sair). Barra inferior: Despesas, Avisos, Perfil.
- Primeiro acesso sem sessão/token: tela única pedindo nome + código de acesso; papel fixo `educador`.
- "Fotografar comprovante": `<input type="file" accept="image/*,application/pdf" capture="environment">`, comprime com as regras atuais, `criarRascunho`, mostra aviso "Foto salva em \"A completar\"" com ação "Completar agora".
- Completar: data padrão = data do rascunho (`criado_em`, fuso do aparelho); projeto padrão = `ultimoProjetoUsado`; categorias como botões de escolha do orçamento escolhido; botão "Enviar para aprovação".

- [ ] **Step 1: Write the failing tests**

```js
test("rejeitadas vão para ajuste, rascunhos para a completar, o resto para enviadas", ...)
test("enviadas mostra no máximo 5, mais recentes primeiro", ...)
test("ultimoProjetoUsado pega o orçamento da despesa mais recente; lista vazia → null", ...)
test("validarFormulario sem exigir arquivo aceita dados sem foto", ...)
```

- [ ] **Step 2: Run** `node --test` — Expected: FAIL.
- [ ] **Step 3: Implement** a lógica e as telas seguindo `telas-celular.html`.
- [ ] **Step 4: Run** `node --test` — Expected: todos passam.
- [ ] **Step 5: Verificar no navegador** (skill `run` ou Playwright) com o backend local em 390 px e 320 px: fotografar → aparece em "A completar" → completar → aparece em "Enviadas" como "Em análise"; rejeitar pelo `curl`/coordenação → aparece em "Precisa de ajuste" → reenviar. Sem rolagem horizontal.
- [ ] **Step 6: Commit** `feat(front-financeiro): celular redesenhado — fotografa agora, completa depois`

---

### Task 8: Estrutura do computador (menu, perfil, rotas)

**Files:**
- Create: `Frontend/Financeiro/index.html` (hoje vazio), `Frontend/Financeiro/app.js` (hoje vazio), `Frontend/Financeiro/style.css` (hoje vazio; layout da barra lateral + área principal)
- Create: `Frontend/Financeiro/base/rotas.js`
- Modify: `Frontend/index.html` — trocar o `<span>`/`<div>` de Financeiro pelos links indicados nos comentários
- Test: `Frontend/Financeiro/tests/rotas.test.js`

**Interfaces:**
- `lerRota(hash: string) -> {tela: "inicio"|"lancamentos"|"projetos"|"projeto"|"entrar", parametros: object}` — `""`/`#/` → inicio; `#/lancamentos?status=aprovado&orcamento=o1` → `{tela: "lancamentos", parametros: {status: "aprovado", orcamento: "o1"}}`; `#/projetos/o1` → `{tela: "projeto", parametros: {id: "o1"}}`; desconhecida → inicio.
- `rotaPermitida(tela, papel) -> boolean` — usa `itensDeMenu`; `projeto` segue `projetos`; fora do menu → app redireciona para Início.
- Cada tela: `export async function mostrar(container: HTMLElement, { parametros, sessao, navegar })`.
- Barra lateral: "MDCA Finanças" (logo real de `Design/Financeiro/_ds/mdca-…/` se houver SVG; senão texto), itens de `itensDeMenu`, contador no Início (preenchido pela Task 9 via `definirContador(n)`), rodapé com nome, papel e "Trocar perfil".
- Sem sessão: tela "Entrar" com nome, papel (os três papéis do computador) e código de acesso. Papel `educador` é encaminhado para `lancamento/`.

- [ ] **Step 1: Write the failing tests** para `lerRota` (casos acima) e `rotaPermitida` (direção não abre `lancamentos`; coordenação abre `projeto`).
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `node --test` — Expected: todos passam.
- [ ] **Step 5: Commit** `feat(front-financeiro): estrutura do computador com menu por papel`

---

### Task 9: Início — "O que precisa de você"

**Files:**
- Create: `Frontend/Financeiro/telas/inicio.js`, `Frontend/Financeiro/telas/inicio-dados.js`
- Test: `Frontend/Financeiro/tests/inicio-dados.test.js`

**Interfaces:**
- `montarPendencias(papel, { lancamentos, orcamentos }, agora) -> { total: number, secoes: Array<{titulo, itens: Array<{rotulo, detalhe, valor, acao: {rotulo, rota}}>}> }`:
  - coordenacao: "Despesas aguardando aprovação" (status pendente; detalhe "Projeto X · enviada hoje"; ação "Analisar" → `#/lancamentos?status=pendente&abrir=<id>`) + "Alertas de orçamento" (`nivel_alerta` alerta/critico; ação "Ver projeto")
  - direcao: só "Alertas de orçamento"
  - voluntario_financeiro: "Aprovados sem conciliação" (aprovado e `conciliado == false`; detalhe com "aberto há N dias" quando N > 7, contado de `aprovado_em`; ação "Ver" → `#/lancamentos?status=aprovado&abrir=<id>`)
  - seções vazias são omitidas; `total` = soma dos itens.
- Tela: saudação "Bom dia/Boa tarde/Boa noite, <primeiro nome>", "N itens precisam de você" (ou "Nada pendente" + texto curto quando `total == 0`), uma tabela por seção; chama `definirContador(total)`.

- [ ] **Step 1: Write the failing tests** — um por papel, mais "sem pendências → total 0 e secoes []" e "aprovado há 8 dias mostra 'aberto há 8 dias'".
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `node --test` — Expected: todos passam.
- [ ] **Step 5: Commit** `feat(front-financeiro): tela Início com pendências por papel`

---

### Task 10: Lançamentos com painel de análise

**Files:**
- Create: `Frontend/Financeiro/telas/lancamentos.js`, `Frontend/Financeiro/telas/lancamentos-dados.js`
- Test: `Frontend/Financeiro/tests/lancamentos-dados.test.js`

**Interfaces:**
- `contarPorStatus(lancamentos) -> {pendente, aprovado, rejeitado, todos}`.
- `saldoAposAprovar(orcamento, lancamento) -> number` (`orcamento.saldo - lancamento.valor`, em centavos).
- `validarMotivo(texto) -> string | null` — vazio → "Informe o motivo da rejeição."; > 500 → "Use no máximo 500 caracteres."; ok → null.
- Tela: abas Aguardando / Aprovados / Rejeitados / Todos com contagem (filtro `status` na rota; padrão `pendente` para coordenação, `aprovado` para voluntário); filtro de projeto (`orcamento`); tabela Despesa (categoria + autor · projeto) · Data · Valor. Clique (ou `abrir=<id>` na rota) abre o painel lateral: etiqueta de status, valor, descrição, foto (`comprovante_url` relativo à API; PDF vira link "Abrir comprovante"), projeto, categoria, data, enviada por, "Saldo após" (só se pendente), motivo (se rejeitado), etiqueta "Conciliado" + referência (se conciliado).
  - Botões só para coordenação/direção e só em pendente: **Rejeitar** abre diálogo com campo de motivo (`validarMotivo`) → `rejeitarLancamento`; **Aprovar** → `aprovarLancamento`. Após sucesso: fecha o painel, recarrega a lista, atualiza o contador do Início. Erro 409 mostra a mensagem do servidor no painel.
  - Voluntário vê o painel sem botões (a ação de conciliar entra na Parte 2).

- [ ] **Step 1: Write the failing tests** para `contarPorStatus`, `saldoAposAprovar` (1000,00 − 180,00 = 820,00; 0,30 − 0,10 = 0,20), `validarMotivo` (vazio, só espaços, 501 caracteres, ok).
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `node --test` — Expected: todos passam.
- [ ] **Step 5: Commit** `feat(front-financeiro): Lançamentos com painel de aprovação`

---

### Task 11: Projetos, Detalhe do projeto e editar orçamento

**Files:**
- Create: `Frontend/Financeiro/telas/projetos.js`, `Frontend/Financeiro/telas/projeto.js`, `Frontend/Financeiro/telas/projetos-dados.js`
- Test: `Frontend/Financeiro/tests/projetos-dados.test.js`

**Interfaces:**
- Projetos vêm de `GET /projetos` (Task 5); orçamentos de `GET /orcamentos`. Nome exibido = `projeto_nome` (ou o `projeto_id` se vier `None`).
- Botão do topo **"Novo projeto"** (só coordenação): diálogo com o nome → `criarProjeto`; 409 mostra "Já existe um projeto com esse nome.".
- Projeto sem orçamento aparece na lista com "Sem orçamento" e, para coordenação, a ação **"Criar orçamento"**: diálogo (valor total, vigência, categorias) com o projeto já escolhido → `criarOrcamento`. Não há como criar orçamento fora de um projeto existente na interface.
- `totaisGerais(orcamentos, pendentes) -> {orcado, gasto, disponivel, aguardando}` (via `somarReais`; `gasto` = `realizado`; `aguardando` = soma dos lançamentos pendentes).
- `gastoPorCategoria(orcamento, lancamentos) -> Array<{categoria, gasto}>` — todas as categorias do orçamento (inclusive com 0), só lançamentos aprovados, ordem do orçamento. *(Decisão do plano: o backend não tem orçamento por categoria, então o Detalhe mostra o gasto por categoria e a barra relativa à maior categoria, não "gasto / limite" como no esboço.)*
- `validarEdicao({valor_total, data_inicio, data_fim, categorias}) -> {campo: mensagem}` — espelha as regras da Task 4 que dá para checar no navegador (valor > 0, datas em ordem, ao menos uma categoria).
- Projetos: 4 números (Orçado, Gasto, Disponível, Aguardando aprovação) + tabela (projeto, vigência, orçado, gasto, barra de uso com %, seta) — clique → `#/projetos/<id>`.
- Detalhe: "Projetos /" + nome + vigência; 3 números (Disponível destacado em amarelo/vermelho conforme `nivel_alerta`); "Por categoria"; "Últimos lançamentos" (5, com etiqueta) + "Ver todos" → `#/lancamentos?orcamento=<id>&status=todos`; "Editar orçamento" (só coordenação) abre diálogo com valor total, vigência e categorias (adicionar/remover) → `editarOrcamento`; erro 400 do servidor aparece no diálogo.

- [ ] **Step 1: Write the failing tests** para `totaisGerais` (centavos), `gastoPorCategoria` (categoria sem gasto aparece com 0; pendentes e rejeitados não contam) e `validarEdicao`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `node --test` — Expected: todos passam.
- [ ] **Step 5: Commit** `feat(front-financeiro): Projetos, Detalhe do projeto e edição de orçamento`

---

### Task 12: Verificação ponta a ponta e documentação

**Files:**
- Create: `docs/front-financeiro.md` (como rodar local, perfis, telas, o que fica para a Parte 2)
- Modify: `.gitignore` (adicionar `.superpowers/`)

- [ ] **Step 1:** Subir o backend local com dados de exemplo (2 orçamentos, lançamentos em cada status) e o front estático (`python3 -m http.server 8080` em `Frontend/`).
- [ ] **Step 2:** No navegador (1280 px), percorrer como coordenação: Início → Analisar → Aprovar; Analisar → Rejeitar sem motivo (erro) → com motivo; Projetos → Detalhe → Editar orçamento abaixo do gasto (erro do servidor) → valor válido. Como direção: menu sem Lançamentos e sem "Editar orçamento". Como voluntário: Início lista aprovados sem conciliação.
- [ ] **Step 3:** No celular (390 px e 320 px), repetir o fluxo da Task 7 contra o mesmo backend e conferir que a rejeição feita no computador aparece em "Precisa de ajuste".
- [ ] **Step 4:** Comparar lado a lado com `telas-computador.html` e `telas-celular.html`: sem emojis, sem pílulas, verde só em ações/ativos, números alinhados.
- [ ] **Step 5:** Rodar as duas suítes — Expected: tudo passa.
- [ ] **Step 6: Commit** `docs(front-financeiro): guia do redesign e verificação`
