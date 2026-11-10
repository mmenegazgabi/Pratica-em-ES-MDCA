# Login único da plataforma (T-35 · US-08) — desenho

Issue: #47 · T-35 · [US-08] Integrar autenticação (login único) compartilhada com o Módulo de Gestão.

## Por quê

Hoje cada pessoa entra duas vezes: na tela inicial (só visual) e de novo no Financeiro,
onde **escolhe o próprio papel** e digita o código único da API (`FINANCEIRO_API_TOKEN`).
Qualquer um com o código entra como qualquer papel. O banco já sabe quem é quem
(`usuarios`, `papeis`, `usuarios_papeis`, da T-32), mas ninguém tem senha.

O que a dona do projeto decidiu:

- Uma só tela de login, a da página inicial (`Frontend/index.html`, visual do Financeiro).
- O papel vem do banco; ninguém escolhe o próprio papel.
- Quem tem mais de um papel do Financeiro escolhe **depois de entrar**, entre os seus.
- A **administração** cadastra a pessoa (nome, e-mail, papéis) numa tela própria.
- A pessoa define a senha no **primeiro acesso**, com um **código de primeiro acesso**
  gerado no cadastro e entregue pela administração (sem ele, quem soubesse o e-mail
  criaria a senha no lugar da pessoa).
- "Esqueci minha senha" = a administração gera um código novo; não há envio de e-mail.

## Objetivos

1. Login por e-mail e senha, com sessão por usuário, para Financeiro e Gestão.
2. Primeiro acesso e redefinição pelo código de acesso.
3. Tela de administração de pessoas e papéis.
4. Financeiro sem a tela "Entrar" própria (computador e celular).

## Fora do escopo

- Ligar o **frontend da Gestão** ao login (ele continua com o código de acesso; o backend
  da Gestão já passa a aceitar a sessão, então a troca no front é uma tarefa futura).
- RBAC completo (T-33), auditoria automática de ações (T-34).
- Envio de e-mail, 2FA, login social.

## Anti-objetivos

- Guardar senha, código ou token em texto puro no banco.
- Mensagem de erro que revele se um e-mail está cadastrado.
- Qualquer caminho em que a pessoa escolha o próprio papel.

## Backend

### Pacote novo `Backend/Acesso/`

Código de login compartilhado pelos módulos (não é de um módulo só).

- `senhas.py`: `gerar_hash(senha) -> str` e `conferir(senha, hash) -> bool` com
  `hashlib.scrypt` (biblioteca padrão; n=2**14, r=8, p=1, sal de 16 bytes), formato
  `scrypt$n$r$p$<sal b64>$<hash b64>`, comparação com `hmac.compare_digest`.
  Senha: mínimo 8 caracteres, máximo 128.
- `codigos.py`: código de primeiro acesso de 9 caracteres do alfabeto sem ambíguos
  (`ABCDEFGHJKMNPQRSTUVWXYZ23456789`), exibido `XXX-XXX-XXX`; a conferência ignora
  hífens, espaços e maiúsculas/minúsculas. Guardado como SHA-256. Vale **7 dias**, uma vez.
  Gerar um código novo invalida os anteriores não usados da pessoa.
- `sessoes.py`: token `secrets.token_urlsafe(32)`, guardado como SHA-256. Validade:
  **30 dias** com "Manter conectado", **12 horas** sem. Sessão de usuário desativado não vale.
- `identidade.py`: resolve o `Authorization: Bearer` em uma identidade (ver abaixo).
- `routers/auth.py` e `routers/admin.py`.

### Migration nova (encadeada no head atual)

- `usuarios.senha_hash` (texto, nulo até o primeiro acesso).
- `sessoes` (`token_hash` PK, `usuario_id` FK, `criada_em`, `expira_em`).
- `codigos_acesso` (`id`, `usuario_id` FK, `codigo_hash`, `criado_em`, `expira_em`,
  `usado_em` nulo, `criado_por` nulo).

### Rotas

| Rota | Corpo | Resposta |
|---|---|---|
| `POST /auth/entrar` | `email`, `senha`, `lembrar` | 200 `{token, expira_em, usuario}`; 401 "E-mail ou senha incorretos." para qualquer falha (e-mail desconhecido, sem senha ainda, senha errada, desativado); 429 após 5 falhas do mesmo e-mail em 15 min |
| `POST /auth/primeiro-acesso` | `email`, `codigo`, `senha`, `lembrar` | define a senha, marca o código como usado, encerra as outras sessões da pessoa e responde como `/auth/entrar`; 400 "Código inválido ou vencido." para qualquer falha; 400 com a regra da senha se ela for curta |
| `GET /auth/eu` | — | `usuario` da sessão; 401 sem sessão válida |
| `POST /auth/sair` | — | 204; apaga a sessão |

`usuario` = `{id, nome, email, papeis: [{id, nome}]}` (papéis da plataforma).

Login, falha de login, primeiro acesso e saída vão para `log_auditoria`
(`modulo = 'plataforma'`, `alvo_tipo = 'usuario'`, `alvo_id` = e-mail em minúsculas nas
falhas). O limite de tentativas conta as falhas no próprio `log_auditoria`, então vale
entre instâncias do Cloud Run.

### Administração (`/admin`, só papel `administracao` da sessão)

| Rota | O que faz |
|---|---|
| `GET /admin/usuarios` | Pessoas com papéis e `situacao`: `ativo`, `aguardando_primeiro_acesso` (sem senha), `desativado` |
| `POST /admin/usuarios` | `nome`, `email`, `papeis` (ao menos um) → cria a pessoa (id = nome em minúsculas com hífens, `-2`, `-3`… se repetir, igual ao `autor_id` do Financeiro) e devolve o **código** e a validade, mostrados uma única vez; 409 se o e-mail já existe |
| `PATCH /admin/usuarios/{id}` | `nome`, `papeis`, `ativo` (opcionais). Desativar encerra as sessões. A pessoa logada não pode se desativar nem tirar o próprio papel `administracao` (400) |
| `POST /admin/usuarios/{id}/codigo` | Gera um código novo (primeiro acesso ou "esqueci a senha"); a senha antiga continua valendo até o código ser usado |

Cada ação vai para `log_auditoria`. Sem sessão: 401; sessão sem `administracao`: 403
(também registrado, como `acesso_negado`).

### Como as rotas existentes passam a identificar quem chama

`Financeiro/autenticacao.py` continua sendo a porta de entrada (as rotas não mudam):

- Bearer igual ao `FINANCEIRO_API_TOKEN` → **modo serviço**, exatamente como hoje
  (papel e usuário pelos cabeçalhos). Fica para testes, scripts e o front da Gestão
  enquanto ele não migra. *(minha escolha: nada quebra durante a transição)*
- Qualquer outro Bearer → procura a sessão no banco (`DATABASE_URL`).
  - `exigir_papel`: o `X-Papel-Usuario` precisa ser um dos papéis da pessoa **e** um dos
    permitidos na rota; sem cabeçalho, vale o único papel permitido que ela tiver.
    Senão 403.
  - `exigir_usuario` / `obter_usuario`: o usuário é o da sessão; o `X-Usuario-Id` é ignorado.
  - Sessão inválida ou vencida: 401. Banco fora do ar: 503.

Como `Gestao/acesso.py` já usa `exigir_usuario`, a Gestão aceita a sessão sem mudança.

### Primeira administradora

Sem administração não há quem cadastre. Um comando cria (ou promove) a pessoa e mostra o
código de primeiro acesso:

`cd Backend && DATABASE_URL=… .venv/bin/python -m Acesso.criar_admin --nome "…" --email "…"`

## Frontend

### Sessão compartilhada `Frontend/Shared/plataforma.js`

Um módulo ES usado pela página inicial, pelo Financeiro e pela tela de administração:

- endereço da API: chave `mdca.api` (lê também a antiga `mdca.financeiro.api`), padrão o
  Cloud Run;
- sessão `{token, expira_em, usuario}` na chave `mdca.sessao`, em `localStorage` com
  "Manter conectado" e em `sessionStorage` sem;
- `entrar`, `primeiroAcesso`, `sair` (chama `/auth/sair` e apaga a sessão local), `lerSessao`.

### Página inicial (`Frontend/index.html`)

- **Entrar**: e-mail, senha, "Manter conectado neste aparelho". Erros da API na caixa
  vermelha que já existe.
- **Primeiro acesso** (link "Primeiro acesso? Use seu código"): e-mail, código, nova
  senha, repetir a senha.
- **Esqueci minha senha**: texto "Peça à administração um novo código de acesso e use
  *Primeiro acesso*." com o link para o formulário de primeiro acesso.
- **Servidor (avançado)**: o mesmo campo recolhido de hoje, para testar com a API local.
- Depois de entrar: escolha de módulo com o nome da pessoa e **Sair**; o cartão
  **Administração** só aparece para quem tem o papel `administracao`.

### Tela de administração (`Frontend/Admin/`)

Visual do Financeiro (tokens e componentes de `Financeiro/base`). Uma tela só:

- tabela: Nome, E-mail, Papéis, Situação, ações (Editar, Gerar código);
- **Cadastrar pessoa**: nome, e-mail, papéis (caixas de marcar, do `GET /gestao/papeis`);
  ao salvar, mostra o código grande, com "Copiar" e a validade, e o aviso de que ele não
  aparece de novo;
- **Editar**: nome, papéis, ativo/desativado;
- sem sessão → volta para a página inicial; sem `administracao` → aviso.

### Financeiro

- Sai a tela "Entrar" (computador) e o formulário de acesso do celular.
- Sem sessão → página inicial (`../` ou `../../`). API respondeu 401 → apaga a sessão e
  volta para a página inicial.
- Papéis do Financeiro da pessoa (`coordenacao`, `direcao`, `voluntario_financeiro`,
  `educador`):
  - nenhum → aviso "Seu perfil não tem acesso ao Financeiro" com link para o início;
  - um → entra direto;
  - mais de um → tela "Entrar como" com um botão por papel; a escolha fica na chave
    `mdca.financeiro.papel` e a barra lateral ganha **Trocar papel**.
- Educador escolhido → app do celular, que lê a mesma sessão.
- Requisições: `Authorization: Bearer <token da sessão>` e `X-Papel-Usuario` = papel em uso.
- A barra lateral mostra o nome do banco e troca "Trocar perfil" por **Sair**.

## Testes

- Backend: `Backend/Acesso/tests/` contra o Postgres descartável (`TEST_DATABASE_URL`, como
  na Gestão); rodam no job "Backend · Infraestrutura integrada" (`pytest Backend`). Os
  testes atuais do Financeiro (modo serviço) continuam iguais.
- Frontend: `node --test` com jsdom para `plataforma.js`, página inicial, administração e
  as mudanças do Financeiro.

## Decisões deixadas para quem implementa

Nomes internos de funções e arquivos além dos citados, textos de ajuda, e a ordem das
colunas da tabela de administração.
