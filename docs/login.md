# Login único (T-35)

Uma conta por pessoa (e-mail e senha) vale para todos os módulos. A página inicial
(`Frontend/index.html`) faz o login e mostra os módulos a que a pessoa tem acesso.

- Backend: `Backend/Acesso/` (senhas, códigos, sessões, administração, auditoria)
- Frontend: `Frontend/Shared/plataforma.js` e `pagina-inicial.js` (página inicial),
  `Frontend/Admin/` (administração de pessoas e papéis)
- Desenho: `docs/superpowers/specs/2026-11-05-login-unico-design.md`

## Fluxo

1. **Cadastro.** Quem tem o papel `administracao` abre "Administração" e cadastra a
   pessoa (nome, e-mail e papéis). A API devolve um **código de primeiro acesso**,
   mostrado uma vez só, válido por 7 dias e de uso único. A administradora entrega o
   código à pessoa.
2. **Primeiro acesso.** Na página inicial, "Primeiro acesso": e-mail, código e a
   senha escolhida (de 8 a 128 caracteres). A sessão já abre.
3. **Login.** E-mail e senha em `POST /auth/entrar`. "Manter conectado" estende a
   sessão de 12 horas para 30 dias (e a guarda em `localStorage` em vez de
   `sessionStorage`). Cinco falhas em 15 minutos para o mesmo e-mail dão 429.
4. **Módulos.** A página inicial lista Financeiro, Gestão e, só para `administracao`,
   Administração. O mesmo token vale em todos (chave `mdca.sessao`). Ao abrir, a página
   inicial, o Financeiro e a Administração conferem a pessoa em `GET /auth/eu` e passam a
   usar os papéis de agora (dados ou tirados pela administração depois do login); sem
   conexão, seguem com os guardados.
5. **Sair** (`POST /auth/sair`) encerra a sessão no servidor e apaga a do navegador.
   Pessoa desativada ou sessão vencida volta para a página inicial na próxima ação.

Os tokens de sessão só existem em claro no navegador; o banco guarda o hash. Senhas
usam scrypt; códigos também ficam com hash. Login, primeiro acesso, códigos,
desativações e trocas de papel vão para `log_auditoria` (módulo `plataforma`). O código
de acesso nunca entra na auditoria.

## Esqueci a senha

Ainda não há e-mail automático. A página mostra "peça um novo código à administração".
Na tela Administração, a ação de novo código chama `POST /admin/usuarios/{id}/codigo`,
que invalida os códigos anteriores. A pessoa usa "Primeiro acesso" com o código novo e
define outra senha; todas as sessões antigas dela caem.

## Primeira administradora

Com `DATABASE_URL` exportada no ambiente (o comando não lê `Backend/.env`) e as
migrations aplicadas, em `Backend/`:

```
.venv/bin/python -m Acesso.criar_admin --nome "Maria Silva" --email maria@mdca.org.br
```

O comando cria a pessoa com o papel `administracao` (ou reaproveita a do e-mail) e
imprime o código de primeiro acesso e a validade. Rode de novo para gerar outro código.

Se a pessoa já está em `usuarios` (cadastrada pela Gestão antes do login, talvez sem
e-mail), promova-a pelo id em vez de criar outra; o e-mail informado passa a ser o dela:

```
.venv/bin/python -m Acesso.criar_admin --id maria-silva --email maria@mdca.org.br
```

Para o time técnico dar senha direto a uma conta que já tem e-mail (por exemplo, as
da demonstração), sem código: `.venv/bin/python scripts/definir-senha.py ana@mdca.org.br`
na raiz do repositório (pede a senha no terminal e encerra as sessões abertas).

## Pessoas sem e-mail

Quem foi cadastrado antes do login pode não ter e-mail e, sem ele, não entra. Em
Administração → Editar, preencha o campo E-mail (é gravado em minúsculas; e-mail de
outra pessoa dá 409) e use "Gerar código" para o primeiro acesso.

## Rotas

| Rota | Quem | O que faz |
| --- | --- | --- |
| `POST /auth/entrar` | público | e-mail, senha, `lembrar`; devolve `token`, `expira_em` e a pessoa com seus papéis |
| `POST /auth/primeiro-acesso` | público | e-mail, código e senha nova; abre a sessão |
| `GET /auth/eu` | sessão | dados e papéis da pessoa da sessão |
| `POST /auth/sair` | sessão | encerra a sessão (204) |
| `GET /admin/usuarios` | administração | lista pessoas, papéis e situação |
| `POST /admin/usuarios` | administração | cadastra pessoa e devolve o código de primeiro acesso |
| `PATCH /admin/usuarios/{id}` | administração | altera nome, e-mail, papéis e `ativo` (não dá para desativar a si mesma) |
| `POST /admin/usuarios/{id}/codigo` | administração | emite novo código (esqueci a senha) |

Nas rotas do Financeiro, `Authorization: Bearer <token da sessão>` identifica a pessoa;
o papel de trabalho vai em `X-Papel-Usuario` e precisa ser um dos papéis dela.
`X-Usuario-Id` é ignorado nesse modo. Desativar a pessoa derruba as sessões. No
Financeiro, os papéis dos vínculos ativos (`vinculos_equipe`) também valem, e quem só é
educador vê apenas os programas do vínculo: veja
[permissoes-financeiro.md](permissoes-financeiro.md).

## Modo serviço

O `FINANCEIRO_API_TOKEN` continua valendo como token de serviço: com ele, papel e
usuário vêm de `X-Papel-Usuario` e `X-Usuario-Id`, como antes. Serve para testes e
scripts. O front da Gestão usa a sessão da tela inicial quando ela existe (lê
`mdca.sessao` e manda o token); sem sessão, volta ao código de acesso e ao
`X-Usuario-Id`. Sem `DATABASE_URL` no
servidor não existem sessões: só o token de serviço é aceito e qualquer outro Bearer
recebe 401 (503 se nem `FINANCEIRO_API_TOKEN` estiver configurado).

Erro do banco nas rotas `/auth` e `/admin` (fora do ar, ou a migration do login ainda
não aplicada) responde 503 "Banco de dados indisponível", com os cabeçalhos de CORS.

## Rodar local com Postgres

1. Banco: `createdb mdca_local`
2. Migrations, em `Backend/`:
   `DATABASE_URL=postgresql://localhost/mdca_local .venv/bin/alembic -c Shared/alembic.ini upgrade head`
3. Primeira administradora (comando acima, com a mesma `DATABASE_URL`).
4. API, **sempre a partir de `Backend/`** (o app integrado é `main:app`). Rodar de dentro
   de `Backend/Financeiro` quebra todas as rotas autenticadas, também no modo serviço:
   `exigir_autenticacao` importa `Acesso`, que só é encontrado a partir de `Backend/`:
   `DATABASE_URL=postgresql://localhost/mdca_local FINANCEIRO_API_TOKEN=dev CORS_ORIGINS=http://localhost:8090 .venv/bin/python -m uvicorn main:app --port 8081`
5. Frontend: `cd Frontend && python3 -m http.server 8090`
6. Abra `http://localhost:8090/`, abra "Servidor (avançado)", informe
   `http://localhost:8081`, use "Primeiro acesso" com o código da administradora e, em
   Administração, cadastre as demais pessoas.

Sem as variáveis `R2_*`, o envio de fotos de comprovante responde 503 (veja
`docs/lancamento-celular.md`).

## Publicação

O login muda o front publicado de uma vez: depois do merge, o Financeiro só abre com
uma sessão da plataforma. Por isso o banco e as contas vêm antes. O backend novo é
compatível com o front antigo (o token de serviço continua valendo), então pode ir
antes do merge.

1. **Migration no banco de produção.** Hoje o deploy da main aplica as migrations
   sozinho (veja [deploy-backend.md](deploy-backend.md#migrations)); este passo manual
   ficou registrado como foi feito na publicação do login. Em
   `Backend/`, com a `DATABASE_URL` de produção (a de `Backend/.env`, que o Alembic lê
   quando a variável não está no ambiente, ou exportada no terminal):
   ```
   .venv/bin/alembic -c Shared/alembic.ini current   # antes: 6bd565cae094 ou anterior
   .venv/bin/alembic -c Shared/alembic.ini upgrade head
   .venv/bin/alembic -c Shared/alembic.ini current   # depois: b7d4e2a9c1f0 (head)
   ```
   As migrations do login só acrescentam: a coluna `usuarios.senha_hash`
   (`62959ecab341`, da primeira versão do login, PR #96, que talvez já esteja aplicada)
   e as tabelas `sessoes` e `codigos_acesso` (`b7d4e2a9c1f0`). Senhas definidas pela
   primeira versão (`scripts/definir-senha.py`) continuam valendo. Se o banco permitir, faça um backup ou branch antes.
2. **Backend com as rotas `/auth` e `/admin`.** Publique a branch com o deploy manual
   (`bash scripts/deploy-backend.sh`, veja `docs/deploy-backend.md`). Confira
   `/health` e que `GET /auth/eu` com um token qualquer (`Authorization: Bearer x`)
   responde 401; 503 indica banco sem a migration.
3. **Primeira administradora**, contra o banco de produção:
   `DATABASE_URL='<url de produção>' .venv/bin/python -m Acesso.criar_admin ...` (com
   `--nome` ou `--id`, como acima). Guarde o código impresso.
4. **Cadastro das pessoas.** Abra o front da branch (preview do Pages ou
   `python3 -m http.server` em `Frontend/`) apontando para a API de produção; a origem
   precisa estar em `CORS_ORIGINS` do serviço. Faça o primeiro acesso da
   administradora e, em Administração, cadastre as pessoas, preencha o e-mail de quem
   já existia e entregue os códigos.
5. **Só então o merge na main.** O CI publica o backend da main e o Pages publica o
   front com o login.

Se algo der errado depois do merge, reverter o front basta: o backend segue aceitando
o token de serviço.

### Estado da produção (10/11/2026)

O banco de produção recebeu a migration `c2d8e4f6a1b3` (persistência do Financeiro) da
branch da E3 antes de ela entrar na main, e as tabelas `sessoes` e `codigos_acesso`
foram criadas à mão, com o mesmo código da `b7d4e2a9c1f0`.

A E3 traz a migration de junção `d9f1a7c3b5e2` (sem operações), que junta as duas
linhas que saem da `6bd565cae094`: a do login (`b7d4e2a9c1f0`) e a da persistência
(`c2d8e4f6a1b3`). Depois de conferir que as tabelas do login estavam iguais às da
migration, a produção foi marcada nela (`alembic stamp d9f1a7c3b5e2`). `alembic current`
lá mostra `d9f1a7c3b5e2 (head) (mergepoint)`.

Daqui para frente, migrations só vão para produção a partir da main.
