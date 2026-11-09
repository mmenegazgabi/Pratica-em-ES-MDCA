# Login único da plataforma (T-35 · US-08)

Uma conta só para a Gestão e o Financeiro: a pessoa entra uma vez na tela inicial
(`Frontend/index.html`) e os dois módulos usam a mesma sessão para chamar a API.

## Como funciona

1. **Tela "Entrar":** e-mail e senha vão para `POST /auth/entrar`.
2. **A API confere a senha** em `usuarios.senha_hash` (hash scrypt; a senha em si nunca é
   guardada) e devolve um **token de sessão**, que vale por 8 horas, com os dados da
   pessoa:

   ```json
   {
     "token": "mdca1.…",
     "expira_em": "2026-11-08T20:00:00Z",
     "usuario": { "id": "ana", "nome": "Ana Martins", "email": "ana@mdca.org.br", "papeis": ["coordenacao"] }
   }
   ```

   `papeis` junta os papéis da plataforma (`usuarios_papeis`) e os papéis com vínculo
   ativo em algum programa (`vinculos_equipe`).
3. **A sessão fica no navegador** em `mdca.sessao`: em `localStorage` com "Manter
   conectado", senão em `sessionStorage` (some ao fechar a aba).
4. **Cada chamada à API** leva `Authorization: Bearer <token>`. A API sabe quem é a
   pessoa pelo token. Com token, o cabeçalho `X-Usuario-Id` é ignorado: não dá para se
   passar por outra pessoa.
5. **"Sair"** apaga a sessão.

`GET /auth/eu` devolve quem está logado (para as telas mostrarem nome e papéis).

### Segurança

- O token é **assinado** com a chave `SESSAO_CHAVE` (HMAC-SHA256): alterar qualquer
  parte dele invalida a assinatura.
- **Conta desativada perde o acesso na hora:** cada requisição com token confere
  `usuarios.ativo` no banco.
- **Entrada recusada** responde sempre "E-mail ou senha inválidos.", sem dizer se o
  e-mail existe, e leva o mesmo tempo nos dois casos.
- **Toda tentativa de entrada vai para `log_auditoria`** (módulo `plataforma`): `login`
  quando dá certo e `login_recusado` com o motivo (`senha_incorreta`,
  `email_nao_cadastrado`, `usuario_desativado`, `sem_senha`).
- Fora do escopo por enquanto: limite de tentativas e "Esqueci minha senha" (a tela
  continua só com o aviso).

## O que já usa o login

| Parte | Situação |
|---|---|
| API (todas as rotas da Gestão e do Financeiro) | Aceita o token de sessão. O código de acesso (`FINANCEIRO_API_TOKEN`) e os cabeçalhos continuam valendo durante a transição. |
| Tela inicial "Entrar" | Chama a API e guarda a sessão. |
| Frontend da Gestão | Usa a sessão: não pede código nem usuário; o menu mostra "Conectado como …"; sessão recusada mostra "Sessão encerrada" com o link para entrar de novo. Sem sessão, funciona como antes. |
| Frontend do Financeiro | **A fazer pelo Financeiro** (abaixo). Até lá, continua pedindo nome, papel e código, sem quebrar nada. |

### O que o Financeiro precisa fazer no frontend

- Ler a sessão de `mdca.sessao` (`localStorage` ou `sessionStorage`) em vez da tela
  "Entrar" própria; sem sessão válida, mandar para a tela inicial (`../`).
- Mandar `Authorization: Bearer <token da sessão>` no lugar do código de acesso. O
  `X-Usuario-Id` deixa de ser necessário.
- Oferecer só os papéis de `usuario.papeis` na escolha de papel e continuar mandando
  `X-Papel-Usuario` até a T-33 (RBAC), que vai conferir o papel no banco.
- Fazer o mesmo no app do celular (`lancamento/`), e o "Sair" apagar `mdca.sessao`.
- O autor dos lançamentos passa a ser o `id` da tabela `usuarios` (ex.: `ana`).

## Contas e senhas

Ainda não há cadastro de contas pela API. A conta é uma linha em `usuarios` com e-mail,
e a senha é definida pelo script (pede a senha no terminal, sem mostrar):

```bash
.venv/bin/python scripts/definir-senha.py ana@mdca.org.br
```

Ele usa a `DATABASE_URL` do ambiente ou do `Backend/.env`. Senha com pelo menos 8
caracteres. Conta sem senha não consegue entrar.

## Configuração

- **`SESSAO_CHAVE`:** chave secreta que assina os tokens. Gere com
  `python -c "import secrets; print(secrets.token_urlsafe(32))"` e cadastre no Cloud Run
  (Editar e implantar nova revisão → Variáveis e secrets) e no `Backend/.env` local.
  O deploy automático preserva as variáveis; o deploy manual
  (`scripts/deploy-backend.sh`) a leva junto do `.env`.
- **Migration** `62959ecab341` (coluna `usuarios.senha_hash`): aplicar na produção
  depois do merge, como as outras.

## Rollback

- **Desligar o login sem deploy:** tirar a `SESSAO_CHAVE` do Cloud Run. Nenhum token é
  emitido nem aceito (`/auth/entrar` responde 503), e a API volta a funcionar só com o
  código de acesso e os cabeçalhos, como antes da T-35. Os frontends sem sessão voltam
  ao comportamento antigo.
- **Desfazer a migration:** `alembic downgrade b7d4e19a2c60` remove só a coluna
  `senha_hash`.
- **Desfazer o código:** "Revert" do PR no GitHub.

## Testar localmente

```bash
# API com o login ligado (Postgres local já migrado)
DATABASE_URL=… SESSAO_CHAVE=chave-local FINANCEIRO_API_TOKEN=token-local \
  .venv/bin/python -m uvicorn main:app --app-dir Backend --port 8000

# Frontend
python3 -m http.server 8080 --directory Frontend
```

No navegador, antes de entrar, aponte a tela para a API local:
`localStorage.setItem('mdca.financeiro.api', 'http://localhost:8000')`.

Testes: `Backend/Shared/tests/test_sessao.py` (senha e token),
`Backend/Gestao/tests/test_login_unico.py` (rotas e integração, com Postgres) e
`Frontend/Gestao/tests/api.test.js` (sessão no cliente da API).
