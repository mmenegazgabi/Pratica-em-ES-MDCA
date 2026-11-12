# Backend/Gestao

Backend do Módulo de Gestão.

Dono: time de Gestão.

## Estrutura

```
Gestao/
  banco.py        # conexão com o PostgreSQL: reexporta Shared/banco.py (a mesma do Financeiro)
  acesso.py       # quem pode consultar e gerenciar cada programa (provisório até a T-33);
                  # regras documentadas em docs/permissoes-gestao.md
  auditoria.py    # registro de eventos na trilha única (log_auditoria)
  programas.py    # programas, convênios e vagas (regras e consultas, um arquivo por assunto)
  plano_de_acao.py  # objetivos, ações, metas, registros do realizado e painel
  equipe.py       # equipe e espaços de cada programa
  usuarios.py     # usuários e papéis da plataforma (só consulta)
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

### Programas e plano de ação (US-02)

Sobre o cadastro canônico de Programas/Projetos
(tabela `projetos`, ARQ-02, a mesma que o Financeiro usa em orçamentos e lançamentos):

Quem pode (T-87): **consultar** = equipe ativa do programa, direção, coordenação e
administração; **alterar** = coordenação e administração. A coordenação é uma só: o
papel `coordenacao` na conta (`usuarios_papeis`), que vale para todos os programas. Ela
não existe como vínculo de programa (a API recusa e o banco tem um CHECK). A plataforma
final não terá perfil de administração: a coordenação tem a visão geral, e a equipe fica
limitada aos programas em que está vinculada.

| Rota | O que faz | Quem pode |
|---|---|---|
| `GET /gestao/programas` | Lista os programas (id, nome, identificador e vigência) | Cada um vê só os que pode consultar (direção, coordenação e administração: todos) |
| `POST /gestao/programas` | Cadastra um programa: `nome`, `identificador`, `publico`, `responsavel`, `vigencia_inicio`, `vigencia_fim` e `descricao` opcional | Coordenação e administração (US-02) |
| `GET /gestao/programas/{id}` | Dados completos do programa | Consultar |
| `PATCH /gestao/programas/{id}` | Edita os dados do programa: só os campos enviados mudam, e o resultado segue as regras do cadastro (um programa antigo, só com nome, precisa ganhar os obrigatórios) | Alterar |
| `GET`/`POST …/{id}/convenios` | Convênios e parcerias: `nome`, `concedente` e vigência opcionais | Consultar / alterar |
| `GET`/`POST …/{id}/vagas` | Vagas ofertadas: `descricao` e `quantidade` | Consultar / alterar |
| `GET`/`POST …/{id}/objetivos` | Objetivos do plano de ação: `descricao` | Consultar / alterar |
| `GET`/`POST …/{id}/acoes` | Ações de um objetivo: `objetivo_id`, `descricao`, `periodo_inicio`, `periodo_fim`, `resultado_esperado` e `periodicidade` | Consultar / alterar |
| `GET`/`POST …/{id}/metas` | Metas de uma ação: `acao_id`, `descricao`, `valor_planejado` e `unidade` opcional | Consultar / alterar |
| `GET`/`POST …/{id}/metas/{meta_id}/registros` | O que foi realizado: `data`, `valor_realizado` e `observacao` opcional | Consultar / alterar |
| `GET …/{id}/painel` | Planejado, realizado (soma dos registros) e percentual de cada meta | Consultar |

Regras:

- Campo obrigatório ausente ou em branco responde **400** com a lista do que falta
  (ex.: `Programa sem público e responsável.`). Tipo errado, como uma data mal
  formatada, continua **422**.
- O período de cada ação precisa caber na vigência do programa.
- `periodicidade`: `semanal`, `quinzenal`, `mensal`, `bimestral`, `trimestral`,
  `semestral` ou `anual`.
- Identificador repetido (sem diferenciar maiúsculas) e vagas com a mesma descrição no
  programa respondem **409**. Programa ou meta inexistente: **404**.
- O acesso segue a seção "Acesso às rotas de programa": quem não pode recebe **403**, e a
  tentativa fica em `log_auditoria`. Programa inexistente continua **404**.

### Equipe, espaços e usuários (US-01)

| Rota | O que faz | Quem pode |
|---|---|---|
| `GET /gestao/programas/{programa_id}/equipe` | Vínculos ativos (quem pode ser responsável de turma); `?incluir_desligados=true` traz o histórico | Equipe ativa do programa, direção, administração |
| `POST /gestao/programas/{programa_id}/equipe` | Vincula uma pessoa: `usuario_id`, `papel_id`, `data_entrada` | Coordenação, administração |
| `PATCH /gestao/programas/{programa_id}/equipe/{vinculo_id}/desligamento` | Registra a `data_saida`; o vínculo não é apagado | Coordenação, administração |
| `GET /gestao/programas/{programa_id}/espacos` | Espaços do programa | Equipe ativa do programa, direção, administração |
| `POST /gestao/programas/{programa_id}/espacos` | Cadastra um espaço: `nome`, `capacidade` opcional | Coordenação, administração |
| `GET /gestao/usuarios` | Usuários da plataforma (ativos e desativados) com papéis da plataforma e vínculos ativos; alimenta "Usuários e acessos" e a escolha de quem vincular | Administração, coordenação |
| `GET /gestao/papeis` | Catálogo de papéis (`id`, `nome`) | Qualquer usuário identificado |

Respostas de erro: 404 (programa ou vínculo inexistente), 403 (sem permissão),
409 (vínculo ativo repetido, desligamento já registrado, espaço com nome repetido),
400 (usuário ou papel inexistente, papel `coordenacao` — que é da conta, não de vínculo —,
saída antes da entrada) e 422 (corpo inválido).

## Acesso às rotas de programa (provisório até a T-33)

- O backend aceita a sessão do login único (`docs/login.md`): com o token da sessão,
  quem chama é o dono dela. Também aceita o token de serviço com o cabeçalho
  `X-Usuario-Id`, como no Financeiro (sem ele, 400). O front da Gestão usa a sessão
  quando a pessoa entrou pela tela inicial (`mdca.sessao`); sem sessão, cai no código de
  acesso e no `X-Usuario-Id`, como antes.
- Os papéis vêm do banco, não de cabeçalho: os da plataforma em `usuarios_papeis`
  (direção, coordenação e administração) e os do programa em `vinculos_equipe`.
- **Vínculo ativo** é o que não tem data de saída ou tem a saída no futuro. A partir
  da data de saída o acesso ao programa é bloqueado, e o vínculo fica no histórico.
- Usuário inexistente ou desativado não acessa nenhum programa.
- Toda negação grava em `log_auditoria` (módulo `gestao`, ação `acesso_negado`,
  programa, método e rota) antes de responder 403. Na lista de usuários o alvo é
  `usuarios`, sem id.
- No modo serviço, quem tem o token pode se identificar como qualquer usuário; a
  proteção real vem quando o front migrar para a sessão e com a T-33 (RBAC).
- O cadastro de pessoas e papéis da plataforma é feito na tela Administração (ou com
  `python -m Acesso.criar_admin`, veja `docs/login.md`). Para testar as telas de Gestão, vale incluir também
  um programa, uma coordenação e uma educadora:

  ```sql
  INSERT INTO usuarios (id, nome) VALUES ('admin', 'Administração');
  INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('admin', 'administracao');

  -- Opcional, para testar o frontend:
  INSERT INTO projetos (id, nome) VALUES ('p-semear', 'Semear');
  INSERT INTO usuarios (id, nome) VALUES ('ana', 'Ana Martins'), ('jessica', 'Jéssica Almeida');
  INSERT INTO usuarios_papeis (usuario_id, papel_id) VALUES ('ana', 'coordenacao');
  INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) VALUES
    ('v-jessica', 'jessica', 'p-semear', 'educador', '2026-03-01');
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
