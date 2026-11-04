# Backend/Gestao

Backend do Módulo de Gestão.

Dono: time de Gestão.

## Estrutura

```
Gestao/
  banco.py        # conexão com o PostgreSQL (DATABASE_URL), via Depends(obter_conexao)
  acesso.py       # quem pode consultar e gerenciar cada programa (provisório até a T-33)
  auditoria.py    # registro de eventos na trilha única (log_auditoria)
  programas.py    # regras e consultas do domínio (uma por assunto)
  equipe.py
  routers/        # rotas FastAPI, todas com prefixo /gestao
    __init__.py   # junta todos os routers de Gestão num só
  tests/          # testes do módulo, rodados pelo job backend-gestao do CI
```

- A API não tem entrada própria: [`Backend/main.py`](../main.py), a entrada única
  publicada no Cloud Run, inclui só o router de `routers/__init__.py`. Uma rota nova
  de Gestão entra nesse arquivo, sem mexer no `main.py` compartilhado com o Financeiro.
- As tabelas são criadas pelas migrations do Alembic em
  [`Backend/Shared/migrations`](../Shared/migrations) (head único, compartilhado com
  o Financeiro). O código de Gestão só lê e grava.
- Sem `DATABASE_URL` configurada ou com o banco fora do ar, as rotas respondem 503.
- Autenticação provisória: o mesmo token de serviço do Financeiro
  (`FINANCEIRO_API_TOKEN`), até o login único (T-35) e o RBAC (T-33).

## Rotas

| Rota | O que faz | Quem pode |
|---|---|---|
| `GET /gestao/programas` | Lista o cadastro canônico de Programas/Projetos (`projetos`, ARQ-02) | Quem tem o token |
| `GET /gestao/programas/{programa_id}/equipe` | Vínculos ativos (quem pode ser responsável de turma); `?incluir_desligados=true` traz o histórico | Equipe ativa do programa, direção, administração |
| `POST /gestao/programas/{programa_id}/equipe` | Vincula uma pessoa: `usuario_id`, `papel_id`, `data_entrada` | Coordenação vinculada ao programa, administração |
| `PATCH /gestao/programas/{programa_id}/equipe/{vinculo_id}/desligamento` | Registra a `data_saida`; o vínculo não é apagado | Coordenação vinculada ao programa, administração |
| `GET /gestao/programas/{programa_id}/espacos` | Espaços do programa | Equipe ativa do programa, direção, administração |
| `POST /gestao/programas/{programa_id}/espacos` | Cadastra um espaço: `nome`, `capacidade` opcional | Coordenação vinculada ao programa, administração |

Respostas de erro: 404 (programa ou vínculo inexistente), 403 (sem permissão),
409 (vínculo ativo repetido, desligamento já registrado, espaço com nome repetido),
400 (usuário ou papel inexistente, saída antes da entrada) e 422 (corpo inválido).

## Acesso às rotas de programa (provisório até a T-33 e a T-35)

- Quem chama é identificado pelo cabeçalho `X-Usuario-Id`, junto com o token de
  serviço, como no Financeiro. Sem ele, a resposta é 400.
- Os papéis vêm do banco, não de cabeçalho: os da plataforma em `usuarios_papeis`
  (direção e administração) e os do programa em `vinculos_equipe`.
- **Vínculo ativo** é o que não tem data de saída ou tem a saída no futuro. A partir
  da data de saída o acesso ao programa é bloqueado, e o vínculo fica no histórico.
- Usuário inexistente ou desativado não acessa nenhum programa.
- Toda negação grava em `log_auditoria` (módulo `gestao`, ação `acesso_negado`,
  programa, método e rota) antes de responder 403.
- Enquanto não há login, quem tem o token pode se identificar como qualquer usuário.
  A proteção real vem com a T-35 (login) e a T-33 (RBAC).
- Ainda não há rota de cadastro de usuários: para começar, inclua um administrador
  direto no banco:

  ```sql
  INSERT INTO usuarios (id, nome) VALUES ('admin', 'Administração');
  INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('admin', 'administracao');
  ```

## Testes

```bash
cd Backend/Gestao
pip install -r requirements.txt
pytest
```

Os testes que leem do banco precisam de um PostgreSQL descartável em
`TEST_DATABASE_URL` (o nome do banco deve conter `test`; as fixtures apagam dados e
aplicam as migrations). Sem a variável, eles são pulados localmente; no CI a falta
do banco faz o job falhar. Um jeito rápido de subir um banco local:

```bash
docker run --rm -d --name mdca-test -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=mdca_test -p 5432:5432 postgres:16
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/mdca_test pytest
```
