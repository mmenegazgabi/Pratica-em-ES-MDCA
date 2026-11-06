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
   Administração. O mesmo token vale em todos (chave `mdca.sessao`).
5. **Sair** (`POST /auth/sair`) encerra a sessão no servidor e apaga a do navegador.
   Pessoa desativada ou sessão vencida volta para a página inicial na próxima ação.

Os tokens de sessão só existem em claro no navegador; o banco guarda o hash. Senhas
usam scrypt; códigos também ficam com hash. Login, primeiro acesso, códigos,
desativações e trocas de papel vão para `log_auditoria` (módulo `acesso`).

## Esqueci a senha

Ainda não há e-mail automático. A página mostra "peça um novo código à administração".
Na tela Administração, a ação de novo código chama `POST /admin/usuarios/{id}/codigo`,
que invalida os códigos anteriores. A pessoa usa "Primeiro acesso" com o código novo e
define outra senha; todas as sessões antigas dela caem.

## Primeira administradora

Com `DATABASE_URL` configurada e as migrations aplicadas, em `Backend/`:

```
python -m Acesso.criar_admin --nome "Maria Silva" --email maria@mdca.org.br
```

O comando cria a pessoa com o papel `administracao` (ou reaproveita a do e-mail) e
imprime o código de primeiro acesso e a validade. Rode de novo para gerar outro código.

## Rotas

| Rota | Quem | O que faz |
| --- | --- | --- |
| `POST /auth/entrar` | público | e-mail, senha, `lembrar`; devolve `token`, `expira_em` e a pessoa com seus papéis |
| `POST /auth/primeiro-acesso` | público | e-mail, código e senha nova; abre a sessão |
| `GET /auth/eu` | sessão | dados e papéis da pessoa da sessão |
| `POST /auth/sair` | sessão | encerra a sessão (204) |
| `GET /admin/usuarios` | administração | lista pessoas, papéis e situação |
| `POST /admin/usuarios` | administração | cadastra pessoa e devolve o código de primeiro acesso |
| `PATCH /admin/usuarios/{id}` | administração | altera nome, papéis e `ativo` (não dá para desativar a si mesma) |
| `POST /admin/usuarios/{id}/codigo` | administração | emite novo código (esqueci a senha) |

Nas rotas do Financeiro, `Authorization: Bearer <token da sessão>` identifica a pessoa;
o papel de trabalho vai em `X-Papel-Usuario` e precisa ser um dos papéis dela.
`X-Usuario-Id` é ignorado nesse modo. Desativar a pessoa derruba as sessões.

## Modo serviço

O `FINANCEIRO_API_TOKEN` continua valendo como token de serviço: com ele, papel e
usuário vêm de `X-Papel-Usuario` e `X-Usuario-Id`, como antes. Serve para testes e
scripts. O front da **Gestão ainda não migrou**: continua pedindo o código de acesso
(token de serviço) e se identificando por `X-Usuario-Id`. Sem `DATABASE_URL`, qualquer
Bearer que não seja o token de serviço cai na regra antiga do Financeiro.

## Rodar local com Postgres

1. Banco: `createdb mdca_local`
2. Migrations, em `Backend/`:
   `DATABASE_URL=postgresql://localhost/mdca_local .venv/bin/alembic -c Shared/alembic.ini upgrade head`
3. Primeira administradora (comando acima, com a mesma `DATABASE_URL`).
4. API, **sempre a partir de `Backend/`** (o app integrado é `main:app`; rodar de dentro
   de `Backend/Financeiro` quebra o modo sessão, pois `Acesso` não é encontrado):
   `DATABASE_URL=postgresql://localhost/mdca_local FINANCEIRO_API_TOKEN=dev CORS_ORIGINS=http://localhost:8090 .venv/bin/python -m uvicorn main:app --port 8081`
5. Frontend: `cd Frontend && python3 -m http.server 8090`
6. Abra `http://localhost:8090/`, abra "Servidor (avançado)", informe
   `http://localhost:8081`, use "Primeiro acesso" com o código da administradora e, em
   Administração, cadastre as demais pessoas.

Sem as variáveis `R2_*`, o envio de fotos de comprovante responde 503 (veja
`docs/lancamento-celular.md`).
