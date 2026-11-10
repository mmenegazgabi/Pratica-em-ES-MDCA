# Login único da plataforma (T-35) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Login por e-mail e senha com papel vindo do banco, primeiro acesso por código, tela de administração e Financeiro sem tela "Entrar" própria.

**Architecture:** Pacote novo `Backend/Acesso` (senhas scrypt, códigos de primeiro acesso, sessões no Postgres, rotas `/auth` e `/admin`). `Financeiro/autenticacao.py` passa a aceitar, além do token de serviço, o token de sessão de um usuário (papéis do banco), o que cobre Financeiro e Gestão sem mudar as rotas. No front, `Frontend/Shared/plataforma.js` guarda a sessão lida pela página inicial, pela administração e pelo Financeiro.

**Tech Stack:** FastAPI, SQLAlchemy Core + Alembic, PostgreSQL, pytest; HTML/CSS/JS ES modules sem build, `node --test` + jsdom.

**Spec:** `docs/superpowers/specs/2026-11-05-login-unico-design.md`

## Global Constraints

- Nenhuma dependência nova no backend nem no frontend (scrypt e `secrets` da biblioteca padrão).
- Senha, código e token nunca em texto puro no banco: senha em scrypt (n=2**14, r=8, p=1, sal 16 bytes, formato `scrypt$n$r$p$<sal b64>$<hash b64>`); código e token em SHA-256 hex.
- Senha: 8 a 128 caracteres. Código: 9 caracteres de `ABCDEFGHJKMNPQRSTUVWXYZ23456789`, exibido `XXX-XXX-XXX`, conferência ignora hífen, espaço e caixa; vale 7 dias, uma vez.
- Sessão: `secrets.token_urlsafe(32)`; 30 dias com `lembrar=true`, 12 horas sem.
- Textos fixos: login falho → "E-mail ou senha incorretos." (401); código falho → "Código inválido ou vencido." (400); bloqueio → 429 "Muitas tentativas. Tente de novo em alguns minutos." após 5 falhas do mesmo e-mail em 15 min.
- Auditoria em `log_auditoria` com `modulo = 'plataforma'`.
- Papéis do Financeiro: `coordenacao`, `direcao`, `voluntario_financeiro`, `educador`. Papel de administração: `administracao`.
- Chaves do navegador: `mdca.sessao` (sessão), `mdca.api` (endereço da API, lendo também a antiga `mdca.financeiro.api`), `mdca.financeiro.papel` (papel escolhido no Financeiro).
- Token de serviço `FINANCEIRO_API_TOKEN` continua aceito exatamente como hoje (modo serviço).
- Texto ao usuário em português; código no estilo dos arquivos vizinhos (nomes em português, comentários curtos).
- Testes de banco usam `TEST_DATABASE_URL` (Postgres descartável); local: `postgresql://localhost/mdca_test`. Comando backend: `cd Backend && TEST_DATABASE_URL=postgresql://localhost/mdca_test FINANCEIRO_API_TOKEN=x .venv/bin/python -m pytest -q`. Frontend: `cd Frontend/Financeiro && node --test`.

## Review Focus

1. E-mail com maiúsculas/espaços no login, no cadastro e no primeiro acesso → tratado igual ao minúsculo sem espaços (teste na Task 2 e na Task 4).
2. Usuário desativado com sessão aberta → a sessão deixa de valer na hora, em `/auth/eu` e nas rotas do Financeiro (teste na Task 3 e na Task 4).
3. Pessoa sem nenhum papel do Financeiro abre o Financeiro → aviso, sem loop de redirecionamento (teste na Task 7).
4. Sessão vencida no navegador (API devolve 401) → volta para a página inicial e apaga a sessão, sem tela em branco (teste na Task 5 e Task 7).
5. Código usado duas vezes ou depois de gerado um novo → "Código inválido ou vencido." (teste na Task 2).

---

### Task 1: Migration e núcleo de senhas, códigos e sessões

**Files:**
- Create: `Backend/Shared/migrations/versions/b7d4e2a9c1f0_create_login_tables.py` (down_revision `5c2e8d41a7b3`)
- Create: `Backend/Acesso/__init__.py`, `Backend/Acesso/senhas.py`, `Backend/Acesso/codigos.py`, `Backend/Acesso/sessoes.py`, `Backend/Acesso/auditoria.py`
- Create: `Backend/Acesso/tests/__init__.py`, `Backend/Acesso/tests/conftest.py`, `Backend/Acesso/tests/test_nucleo.py`
- Modify: `Backend/pytest.ini` (testpaths ganha `Acesso/tests`)

**Interfaces:**
- Produces:
  - migration: `usuarios.senha_hash TEXT NULL`; `sessoes(token_hash TEXT PK, usuario_id TEXT FK usuarios, criada_em timestamptz default now(), expira_em timestamptz NOT NULL)` com índice em `usuario_id`; `codigos_acesso(id BIGINT identity PK, usuario_id TEXT FK usuarios, codigo_hash TEXT NOT NULL, criado_em timestamptz default now(), expira_em timestamptz NOT NULL, usado_em timestamptz NULL, criado_por TEXT NULL)` com índice em `usuario_id`. Downgrade remove só isso.
  - `senhas.gerar_hash(senha: str) -> str`, `senhas.conferir(senha: str, hash_: Optional[str]) -> bool` (False para `None`/formato inválido), `senhas.validar(senha: str) -> Optional[str]` (mensagem de erro ou None: "A senha precisa ter pelo menos 8 caracteres." / "A senha pode ter no máximo 128 caracteres.").
  - `codigos.gerar() -> str` (formato `XXX-XXX-XXX`), `codigos.normalizar(codigo: str) -> str`, `codigos.emitir(conexao, usuario_id: str, criado_por: Optional[str], agora: datetime) -> Tuple[str, datetime]` (invalida os não usados anteriores marcando `usado_em`, grava o novo, devolve código e validade), `codigos.consumir(conexao, usuario_id: str, codigo: str, agora: datetime) -> bool`.
  - `sessoes.criar(conexao, usuario_id: str, lembrar: bool, agora: datetime) -> Tuple[str, datetime]`, `sessoes.usuario_da_sessao(conexao, token: str, agora: datetime) -> Optional[str]` (None se não existe, venceu ou usuário inativo), `sessoes.encerrar(conexao, token: str) -> None`, `sessoes.encerrar_todas(conexao, usuario_id: str) -> None`.
  - `auditoria.registrar(conexao, *, usuario_id, acao, alvo_tipo=None, alvo_id=None, descricao=None, detalhes=None)` com `modulo='plataforma'` (mesma forma de `Gestao/auditoria.py`).
  - `conftest.py`: fixtures `banco` (igual à da Gestão, limpando também `sessoes` e `codigos_acesso`), `cliente`, `TOKEN`, e helper `criar_usuario(motor, *, id, nome, email, papeis=(), senha=None, ativo=True)`.

- [ ] **Step 1: Write the failing tests** in `test_nucleo.py`:
  - `test_hash_confere_e_nao_guarda_texto`: `h = gerar_hash("segredo123")`; `h.startswith("scrypt$16384$8$1$")`; `"segredo123" not in h`; `conferir("segredo123", h)`; `not conferir("outra", h)`; `not conferir("x", None)`; `not conferir("x", "lixo")`.
  - `test_validar_senha`: `validar("1234567") == "A senha precisa ter pelo menos 8 caracteres."`; `validar("x"*129)` é a mensagem de máximo; `validar("12345678") is None`.
  - `test_codigo_formato_e_normalizacao`: `re.fullmatch(r"[A-HJ-NP-Z2-9]{3}-[A-HJ-NP-Z2-9]{3}-[A-HJ-NP-Z2-9]{3}", gerar())`; `normalizar(" k7q-4mz 9p2 ") == "K7Q4MZ9P2"`.
  - `test_codigo_vale_uma_vez(banco)`: emite, `consumir` com o código em minúsculas → True; de novo → False.
  - `test_codigo_novo_invalida_anterior(banco)`: emite A, emite B; `consumir(A)` False; `consumir(B)` True.
  - `test_codigo_vence_em_7_dias(banco)`: emite em `agora`; `consumir(..., agora + timedelta(days=7, seconds=1))` False.
  - `test_sessao_validade(banco)`: `criar(lembrar=True)` expira em `agora+30d`; `lembrar=False` em `agora+12h`; o token não aparece em `SELECT token_hash FROM sessoes`; `usuario_da_sessao` devolve o id; depois de `encerrar` devolve None; vencida devolve None.
  - `test_sessao_de_usuario_desativado_nao_vale(banco)`.
  - `test_migration_cria_e_remove` (upgrade/downgrade de `b7d4e2a9c1f0`, seguindo `Backend/Shared/tests/test_migration_usuarios_papeis_auditoria.py`).

- [ ] **Step 2: Run** `… pytest Acesso -q` → FAIL (módulos inexistentes).
- [ ] **Step 3: Implement** migration e módulos com as interfaces acima.
- [ ] **Step 4: Run** `… pytest -q` (suíte inteira) → tudo PASS.
- [ ] **Step 5: Commit** `feat(acesso): tabelas de login e núcleo de senhas, códigos e sessões (T-35)`.

### Task 2: Rotas `/auth` e comando da primeira administradora

**Files:**
- Create: `Backend/Acesso/usuarios.py`, `Backend/Acesso/routers/__init__.py`, `Backend/Acesso/routers/auth.py`, `Backend/Acesso/criar_admin.py`
- Create: `Backend/Acesso/tests/test_auth.py`, `Backend/Acesso/tests/test_criar_admin.py`
- Modify: `Backend/main.py` (inclui o router)

**Interfaces:**
- Consumes: Task 1.
- Produces:
  - `usuarios.por_email(conexao, email: str) -> Optional[Row]` (compara `lower(email)` com o e-mail sem espaços em minúsculas; colunas `id, nome, email, ativo, senha_hash`), `usuarios.dados_publicos(conexao, usuario_id: str) -> dict` = `{"id", "nome", "email", "papeis": [{"id","nome"}]}` (papéis de `usuarios_papeis`, ordem por nome).
  - `POST /auth/entrar` `{email, senha, lembrar: bool=false}` → 200 `{token, expira_em, usuario}`; ações de auditoria `login` (usuario_id) e `login_falhou` (`alvo_tipo='usuario'`, `alvo_id`=e-mail normalizado). Limite: conta `login_falhou` com esse `alvo_id` nos últimos 15 min; com 5 ou mais responde 429 antes de conferir a senha.
  - `POST /auth/primeiro-acesso` `{email, codigo, senha, lembrar=false}` → valida a senha (400 com a mensagem de `senhas.validar`), consome o código, grava `senha_hash`, `encerrar_todas`, cria sessão, audita `primeiro_acesso`; responde como `/auth/entrar`. Usuário inexistente/inativo/código ruim → 400 "Código inválido ou vencido.".
  - `GET /auth/eu` (Bearer de sessão) → `usuario`; 401 "Sessão inválida ou vencida." caso contrário.
  - `POST /auth/sair` → 204 (também 204 sem sessão válida); audita `logout`.
  - Banco indisponível → 503 (reaproveitar `Gestao.banco.obter_conexao`).
  - `python -m Acesso.criar_admin --nome N --email E` (lê `DATABASE_URL`): cria a pessoa (id = slug do nome como `usuarioId` do front, com `-2`, `-3`… se existir) ou usa a existente pelo e-mail, garante o papel `administracao`, emite código e imprime `Código de primeiro acesso: XXX-XXX-XXX (vale até DD/MM/AAAA HH:MM)`. Função testável `criar_admin(conexao, nome, email, agora) -> Tuple[str, str, datetime]` (usuario_id, código, validade). A geração de id fica em `usuarios.novo_id(conexao, nome) -> str`.

- [ ] **Step 1: Write the failing tests** (`test_auth.py`), com `criar_usuario` do conftest:
  - `test_entrar_devolve_token_e_papeis`: usuária `ana` com senha e papéis `coordenacao`,`voluntario_financeiro`; POST com `" Ana@MDCA.org.br "` → 200, `usuario.papeis` ids == `["coordenacao","voluntario_financeiro"]` (ordem por nome), `token` não vazio.
  - `test_entrar_falhas_tem_a_mesma_resposta`: e-mail desconhecido, senha errada, usuário sem senha, usuário desativado → todos 401 com `detail == "E-mail ou senha incorretos."`.
  - `test_bloqueia_depois_de_5_falhas`: 5 senhas erradas → 6ª tentativa, mesmo com a senha certa, 429.
  - `test_primeiro_acesso_define_senha`: emite código; POST primeiro-acesso → 200; depois `/auth/entrar` com a senha nova → 200; mesmo código de novo → 400 "Código inválido ou vencido.".
  - `test_primeiro_acesso_senha_curta`: 400 com "A senha precisa ter pelo menos 8 caracteres." e o código continua válido.
  - `test_primeiro_acesso_encerra_outras_sessoes`.
  - `test_eu_e_sair`: `/auth/eu` com o token → 200 e mesmo `usuario`; `/auth/sair` → 204; `/auth/eu` → 401.
  - `test_auditoria_de_login`: depois de um login certo e um errado, `log_auditoria` tem `login` e `login_falhou` com `modulo='plataforma'`.
  - `test_criar_admin.py`: cria nova (id `maria-silva`), segunda pessoa com o mesmo nome vira `maria-silva-2`; e-mail existente reaproveita a pessoa e adiciona `administracao`; o código retornado é aceito por `/auth/primeiro-acesso`.
- [ ] **Step 2: Run** `… pytest Acesso -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** suíte inteira → PASS.
- [ ] **Step 5: Commit** `feat(acesso): rotas de login, primeiro acesso e saída (T-35)`.

### Task 3: Rotas existentes aceitam a sessão do usuário

**Files:**
- Modify: `Backend/Financeiro/autenticacao.py`
- Create: `Backend/Acesso/identidade.py`, `Backend/Acesso/tests/test_identidade.py`

**Interfaces:**
- Consumes: Task 1 (`sessoes.usuario_da_sessao`), Task 2 (`usuarios.dados_publicos`).
- Produces:
  - `identidade.Identidade` (dataclass frozen): `servico: bool`, `usuario_id: Optional[str]`, `papeis: FrozenSet[str]`.
  - `Financeiro.autenticacao.exigir_autenticacao` passa a devolver `Identidade` (antes `"servico-financeiro"`): token igual ao `FINANCEIRO_API_TOKEN` → `Identidade(servico=True, usuario_id=None, papeis=frozenset())` sem tocar no banco; outro token → abre conexão (`DATABASE_URL`; ausente/fora do ar → 503 "Banco de dados indisponível"), `usuario_da_sessao`; None → 401 "Autenticação obrigatória." com `WWW-Authenticate: Bearer`. Sem Bearer: 401 (ou 503 "Autenticação da API não configurada no servidor." quando `FINANCEIRO_API_TOKEN` não está configurado, como hoje). Sessão válida funciona mesmo sem `FINANCEIRO_API_TOKEN` configurado; os testes atuais de 503/401 do Financeiro continuam passando.
  - `exigir_papel(*permitidos)`: modo serviço = hoje. Modo sessão: cabeçalho presente → precisa estar em `identidade.papeis ∩ permitidos`, senão 403 com a mensagem atual; cabeçalho ausente → se `papeis ∩ permitidos` tem exatamente um, usa esse; senão 403.
  - `exigir_usuario` / `obter_usuario`: modo sessão devolve `identidade.usuario_id` e ignora `X-Usuario-Id`. `obter_usuario` hoje não depende da autenticação; passa a receber a `Identidade` opcional sem quebrar as rotas que o usam sem auth (verificar usos com `grep -rn obter_usuario Backend`).
- [ ] **Step 1: Write the failing tests** (`test_identidade.py`, rotas reais do Financeiro e da Gestão):
  - `test_coordenacao_por_sessao_cria_orcamento_e_projeto` (rota com `exigir_papel(COORDENACAO)`, cabeçalho `X-Papel-Usuario: coordenacao`) → sucesso.
  - `test_papel_que_a_pessoa_nao_tem_da_403`: usuária só `voluntario_financeiro` manda `X-Papel-Usuario: coordenacao` → 403.
  - `test_sem_cabeçalho_usa_o_unico_papel_permitido` e `test_sem_cabecalho_com_dois_papeis_permitidos_da_403`.
  - `test_autor_vem_da_sessao`: rascunho/lançamento criado com `X-Usuario-Id: outra-pessoa` fica com `autor_id` = id da sessão.
  - `test_token_desconhecido_da_401` e `test_usuario_desativado_perde_acesso_na_hora`.
  - `test_gestao_aceita_sessao`: `GET /gestao/papeis` com Bearer de sessão → 200.
  - `test_modo_servico_continua_igual`: token de serviço + `X-Papel-Usuario` qualquer dos 4 → como antes.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** suíte inteira (inclui os ~400 testes do Financeiro em modo serviço) → PASS.
- [ ] **Step 5: Commit** `feat(acesso): Financeiro e Gestão identificam quem chama pela sessão (T-35)`.

### Task 4: Rotas `/admin/usuarios`

**Files:**
- Create: `Backend/Acesso/admin.py`, `Backend/Acesso/routers/admin.py`, `Backend/Acesso/tests/test_admin.py`
- Modify: `Backend/main.py`

**Interfaces:**
- Consumes: Tasks 1–3 (`exigir_autenticacao` → `Identidade`; só modo sessão com papel `administracao`; modo serviço → 403).
- Produces:
  - `GET /admin/usuarios` → lista `{id, nome, email, ativo, papeis:[{id,nome}], situacao}` com `situacao` ∈ `ativo` | `aguardando_primeiro_acesso` (ativo e `senha_hash` nulo) | `desativado`; ordem por nome.
  - `POST /admin/usuarios` `{nome, email, papeis: [str] (≥1, ids existentes)}` → 201 `{usuario, codigo, codigo_expira_em}`; e-mail normalizado; 409 "Já existe uma pessoa com este e-mail."; 400 para papel desconhecido ou lista vazia ("Escolha ao menos um papel."), nome vazio, e-mail sem `@`.
  - `PATCH /admin/usuarios/{id}` `{nome?, papeis?, ativo?}` → 200 `usuario` com `situacao`; `ativo=false` chama `sessoes.encerrar_todas`; 400 "Você não pode desativar a própria conta." / "Você não pode tirar o próprio papel de administração."; 404 "Pessoa não encontrada.".
  - `POST /admin/usuarios/{id}/codigo` → 200 `{codigo, codigo_expira_em}`; 400 se a pessoa está desativada ("Reative a pessoa antes de gerar um código.").
  - Auditoria: `usuario_criado`, `usuario_editado`, `usuario_desativado`, `usuario_reativado`, `codigo_gerado` (nunca o código em `detalhes`); 403 grava `acesso_negado` com `alvo_tipo='usuarios'`.
- [ ] **Step 1: Write the failing tests**: sem sessão 401; sessão sem `administracao` 403 + `acesso_negado`; modo serviço 403; criar com `" Joao@MDCA.org.br "` → e-mail `joao@mdca.org.br`, situação `aguardando_primeiro_acesso`, código aceito em `/auth/primeiro-acesso` e depois situação `ativo`; e-mail repetido 409 (mesmo com outra caixa); papel desconhecido 400; desativar encerra a sessão da pessoa (`/auth/eu` dela → 401); não se desativa / não tira o próprio `administracao`; gerar código novo invalida o anterior; código não aparece em `log_auditoria`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** suíte inteira → PASS.
- [ ] **Step 5: Commit** `feat(acesso): administração de pessoas e papéis (T-35)`.

### Task 5: Sessão compartilhada no front e página inicial com login de verdade

**Files:**
- Create: `Frontend/Shared/plataforma.js`
- Modify: `Frontend/index.html` (script vira `type="module"` importando `./Shared/plataforma.js`)
- Create: `Frontend/Financeiro/tests/plataforma.test.js`, `Frontend/Financeiro/tests/pagina-inicial.test.js`

**Interfaces:**
- Produces (`plataforma.js`):
  - `API_PADRAO` (mesmo valor do Financeiro), `urlDaApi() -> string` (`mdca.api` → `mdca.financeiro.api` → padrão, sem barra final), `salvarUrlDaApi(url: string)`.
  - `lerSessao() -> {token, expira_em, usuario} | null` (procura em `localStorage` e `sessionStorage`; vencida → apaga e devolve null).
  - `entrar({email, senha, lembrar}) -> Promise<{ok: true, sessao} | {ok: false, mensagem}>`; `primeiroAcesso({email, codigo, senha, lembrar})` igual; mensagens: as do backend (`detail`), rede → "Sem conexão com o servidor. Tente de novo.".
  - `sair() -> Promise<void>` (POST `/auth/sair` com o token, ignora erro, apaga a sessão e `mdca.financeiro.papel`).
  - `encerrarSessaoLocal()`; `temPapel(sessao, papel) -> boolean`.
- Página inicial: formulários Entrar (já existe), **Primeiro acesso** (`#formPrimeiro`: e-mail, código, nova senha, repetir; "As senhas não conferem." no front), "Esqueci minha senha" mostra `#esqueci` com "Peça à administração um novo código de acesso e use **Primeiro acesso**." e botão para o formulário; `<details>` "Servidor (avançado)" com o endereço; botão de envio desabilitado durante a requisição; depois de entrar: escolha de módulos com "Olá, <nome>", **Sair** chama `sair()`, cartão e item de menu **Administração** (`Admin/`) só com `administracao`. A sessão provisória `mdca.plataforma.entrada` da versão anterior deixa de existir.
- [ ] **Step 1: Write the failing tests** (jsdom, `fetch` simulado): `plataforma.test.js` — `entrar` com `lembrar` grava em `localStorage`, sem em `sessionStorage`; erro 401 devolve a mensagem do backend; rede caída → mensagem de conexão; sessão vencida é apagada; `urlDaApi` lê a chave antiga. `pagina-inicial.test.js` — carrega `Frontend/index.html` com os scripts: sem sessão mostra Entrar; envio certo mostra os módulos com o nome; cartão Administração só para `administracao`; Sair volta ao login e chama `/auth/sair`; primeiro acesso com senhas diferentes não chama a API.
- [ ] **Step 2: Run** `cd Frontend/Financeiro && node --test` → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(front): página inicial com login, primeiro acesso e sessão compartilhada (T-35)`.

### Task 6: Tela de administração

**Files:**
- Create: `Frontend/Admin/index.html`, `Frontend/Admin/admin.js`, `Frontend/Admin/admin.css`
- Create: `Frontend/Financeiro/tests/admin.test.js`

**Interfaces:**
- Consumes: `plataforma.js` (Task 5); rotas da Task 4 e `GET /gestao/papeis`; `Financeiro/base/tokens.css`, `componentes.css`, `dom.js` (`el`, `limpar`), `logo.js`.
- Produces: `export function iniciar(raiz, { redirecionar })` em `admin.js` (mesmo padrão do `Financeiro/app.js`).
  - Sem sessão → `redirecionar("../")`; sessão sem `administracao` → aviso "Esta área é só da administração." com link para o início; API 401 → apaga a sessão e redireciona.
  - Tabela: Nome, E-mail, Papéis (nomes separados por vírgula), Situação ("Ativo", "Aguardando primeiro acesso", "Desativado"), ações **Editar** e **Gerar código** (esta não aparece para desativados).
  - **Cadastrar pessoa** (diálogo): nome, e-mail, caixas de papéis; ao salvar mostra o código em destaque, a validade (dd/mm/aaaa hh:mm), botão **Copiar** (`navigator.clipboard.writeText`) e "Este código não aparece de novo. Entregue à pessoa: ela entra em Primeiro acesso, informa o e-mail e o código e cria a senha.".
  - **Editar**: nome, papéis, "Conta ativa"; erros do backend aparecem no diálogo.
  - Textos do usuário só por `textContent` (`el`), nunca `innerHTML`.
- [ ] **Step 1: Write the failing tests**: redireciona sem sessão; aviso sem `administracao`; lista com situações traduzidas; cadastro envia `{nome, email, papeis}` e mostra o código; 409 mostra "Já existe uma pessoa com este e-mail."; Gerar código mostra o código novo; Editar envia só os campos alterados.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS. Conferir no navegador contra o backend local.
- [ ] **Step 5: Commit** `feat(front): tela de administração de pessoas e papéis (T-35)`.

### Task 7: Financeiro (computador) usa a sessão da plataforma

**Files:**
- Modify: `Frontend/Financeiro/base/sessao.js`, `Frontend/Financeiro/base/api.js`, `Frontend/Financeiro/app.js`, `Frontend/Financeiro/style.css`
- Modify: testes afetados (`sessao.test.js`, `api.test.js`, `estrutura.test.js`, telas que montam sessão)

**Interfaces:**
- Consumes: `plataforma.js`.
- Produces:
  - `sessao.js`: `PAPEIS` igual; `papeisDoFinanceiro(sessaoPlataforma) -> string[]` (na ordem de `PAPEIS`); `lerSessao() -> {papel, nome, usuarioId} | null` = sessão da plataforma + papel em uso (o salvo em `mdca.financeiro.papel` se ainda for da pessoa, senão o único papel do Financeiro, senão null); `escolherPapel(papel)`; `esquecerPapel()`. Saem `salvarSessao`, `usarChaveDeSessao`, `CHAVE_SESSAO_*` (o celular passa a usar a mesma sessão). `nomeDoAutor`, `usuarioId`, `itensDeMenu` ficam.
  - `api.js`: `urlDaApi` vem de `plataforma.js`; cabeçalhos `Authorization: Bearer <sessão.token>`, `X-Papel-Usuario: <papel em uso>`; sem `X-Usuario-Id`. Saem `TOKEN_FIXO`, `salvarAcesso`, `esquecerAcesso`, `tokenSalvo`. Resposta 401 → `encerrarSessaoLocal()` e `window.location.assign` para a página inicial (caminho relativo passado por quem chama: `configurarSaida(url)`; padrão `"../"`).
  - `app.js`: sem `telaEntrar`. Sem sessão da plataforma → `redirecionar("../")`. Nenhum papel do Financeiro → tela "Seu perfil não tem acesso ao Financeiro." com link "Voltar ao início" (`../`). Mais de um e nenhum escolhido (ou rota `#/papel`) → tela "Entrar como" com um botão por papel (rótulo de `PAPEIS`). Papel em uso `educador` → `redirecionar("lancamento/")`. Barra lateral: nome do banco, papel, **Trocar papel** (só com mais de um; vai a `#/papel`) e **Sair** (`sair()` da plataforma e `redirecionar("../")`).
  - Some do CSS a seção `.entrar`.
- [ ] **Step 1: Write the failing tests**: sem sessão redireciona para `../`; papel único entra direto no Início; dois papéis mostram "Entrar como" e a escolha persiste; papel salvo que a pessoa perdeu é ignorado; sem papel do Financeiro mostra o aviso sem redirecionar; requisições levam o token e o papel; 401 apaga a sessão e redireciona; Sair chama `/auth/sair`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** e ajustar os testes antigos que criavam sessão com `salvarSessao`/`salvarAcesso` (criar helper de teste `sessaoDeTeste({papeis, papel})` em `tests/ajuda-sessao.js`). **Step 4: Run** → PASS (todos).
- [ ] **Step 5: Commit** `feat(front-financeiro): entra pela sessão da plataforma e escolhe o papel (T-35)`.

### Task 8: App do celular usa a sessão da plataforma

**Files:**
- Modify: `Frontend/Financeiro/lancamento/lancamento.js`, `Frontend/Financeiro/tests/lancamento-tela.test.js`

**Interfaces:**
- Consumes: Task 7 (`lerSessao`, `escolherPapel`, `api.js` sem token próprio).
- Produces: sem sessão da plataforma → `window.location.assign("../../")`; pessoa sem papel `educador` → aviso "Este app é para educadores." com link para `../`; com `educador` → usa `educador` como papel (chama `escolherPapel("educador")`). Sai `telaPrimeiroAcesso` e o formulário de código/servidor do Perfil; Perfil mostra nome e e-mail e o botão **Sair deste aparelho** chama `sair()` e vai para `../../`. A saída padrão do `api.js` no celular é `../../`.
- [ ] **Step 1: Write the failing tests**: sem sessão redireciona para `../../`; educador vê Minhas despesas; pessoa sem educador vê o aviso; Perfil sem campo de código; Sair chama `/auth/sair` e redireciona.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(front-financeiro): app do celular entra pela sessão da plataforma (T-35)`.

### Task 9: Documentação e verificação ponta a ponta

**Files:**
- Modify: `docs/front-financeiro.md`, `docs/lancamento-celular.md`, `Backend/Gestao/README.md` (seção de acesso), `README.md` se citar o código de acesso
- Create: `docs/login.md` (como funciona, primeira administradora, rodar local com Postgres)

- [ ] **Step 1:** Escrever `docs/login.md`: fluxo (cadastro → código → primeiro acesso → login), "esqueci a senha", comando `criar_admin`, rotas, modo serviço, rodar local (`createdb mdca_local`, `alembic upgrade head`, `DATABASE_URL=postgresql://localhost/mdca_local`, uvicorn com `Backend/main.py`, front em `python3 -m http.server`, "Servidor (avançado)"). Atualizar os outros docs: sai "nome, papel e código"; Gestão front ainda usa o código.
- [ ] **Step 2:** Rodar backend completo e `node --test` no Financeiro e na Gestão → PASS.
- [ ] **Step 3:** Ponta a ponta no navegador contra o backend local com Postgres: criar admin pelo comando, primeiro acesso, cadastrar uma coordenadora e um educador, primeiro acesso de cada, Financeiro no computador e no celular, desativar e ver a sessão cair.
- [ ] **Step 4: Commit** `docs: login único, administração e como rodar local (T-35)`.
