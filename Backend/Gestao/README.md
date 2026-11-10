# Backend/Gestao

Backend do Módulo de Gestão.

Dono: time de Gestão.

## Estrutura

```
Gestao/
  banco.py        # conexão com o PostgreSQL (DATABASE_URL), via Depends(obter_conexao)
  acesso.py       # quem pode consultar e gerenciar cada programa (provisório até a T-33)
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

| Rota | O que faz |
|---|---|
| `GET /gestao/programas` | Lista os programas (id e nome) |
| `POST /gestao/programas` | Cadastra um programa: `nome`, `identificador`, `publico`, `responsavel`, `vigencia_inicio`, `vigencia_fim` e `descricao` opcional |
| `GET /gestao/programas/{id}` | Dados completos do programa |
| `GET`/`POST …/{id}/convenios` | Convênios e parcerias: `nome`, `concedente` e vigência opcionais |
| `GET`/`POST …/{id}/vagas` | Vagas ofertadas: `descricao` e `quantidade` |
| `GET`/`POST …/{id}/objetivos` | Objetivos do plano de ação: `descricao` |
| `GET`/`POST …/{id}/acoes` | Ações de um objetivo: `objetivo_id`, `descricao`, `periodo_inicio`, `periodo_fim`, `resultado_esperado` e `periodicidade` |
| `GET`/`POST …/{id}/metas` | Metas de uma ação: `acao_id`, `descricao`, `valor_planejado` e `unidade` opcional |
| `GET`/`POST …/{id}/metas/{meta_id}/registros` | O que foi realizado: `data`, `valor_realizado` e `observacao` opcional |
| `GET …/{id}/painel` | Planejado, realizado (soma dos registros) e percentual de cada meta |

Regras:

- Campo obrigatório ausente ou em branco responde **400** com a lista do que falta
  (ex.: `Programa sem público e responsável.`). Tipo errado, como uma data mal
  formatada, continua **422**.
- O período de cada ação precisa caber na vigência do programa.
- `periodicidade`: `semanal`, `quinzenal`, `mensal`, `bimestral`, `trimestral`,
  `semestral` ou `anual`.
- Identificador repetido (sem diferenciar maiúsculas) e vagas com a mesma descrição no
  programa respondem **409**. Programa ou meta inexistente: **404**.
- Estas rotas exigem só o token de serviço; ainda não usam o acesso por programa
  da seção abaixo.

### Equipe, espaços e usuários (US-01)

| Rota | O que faz | Quem pode |
|---|---|---|
| `GET /gestao/programas/{programa_id}/equipe` | Vínculos ativos (quem pode ser responsável de turma); `?incluir_desligados=true` traz o histórico | Equipe ativa do programa, direção, administração |
| `POST /gestao/programas/{programa_id}/equipe` | Vincula uma pessoa: `usuario_id`, `papel_id`, `data_entrada` | Coordenação vinculada ao programa, administração |
| `PATCH /gestao/programas/{programa_id}/equipe/{vinculo_id}/desligamento` | Registra a `data_saida`; o vínculo não é apagado | Coordenação vinculada ao programa, administração |
| `GET /gestao/programas/{programa_id}/espacos` | Espaços do programa | Equipe ativa do programa, direção, administração |
| `POST /gestao/programas/{programa_id}/espacos` | Cadastra um espaço: `nome`, `capacidade` opcional | Coordenação vinculada ao programa, administração |
| `GET /gestao/usuarios` | Usuários da plataforma (ativos e desativados) com papéis da plataforma e vínculos ativos; alimenta "Usuários e acessos" e a escolha de quem vincular | Administração, coordenação ativa em algum programa |
| `GET /gestao/papeis` | Catálogo de papéis (`id`, `nome`) | Qualquer usuário identificado |

Respostas de erro: 404 (programa ou vínculo inexistente), 403 (sem permissão),
409 (vínculo ativo repetido, desligamento já registrado, espaço com nome repetido),
400 (usuário ou papel inexistente, saída antes da entrada) e 422 (corpo inválido).

## Acesso às rotas de programa (provisório até a T-33)

- O backend aceita a sessão do login único (`docs/login.md`): com o token da sessão,
  quem chama é o dono dela. Também aceita o token de serviço com o cabeçalho
  `X-Usuario-Id`, como no Financeiro (sem ele, 400). O front da Gestão usa a sessão
  quando a pessoa entrou pela tela inicial (`mdca.sessao`); sem sessão, cai no código de
  acesso e no `X-Usuario-Id`, como antes.
- Os papéis vêm do banco, não de cabeçalho: os da plataforma em `usuarios_papeis`
  (direção e administração) e os do programa em `vinculos_equipe`.
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
  INSERT INTO vinculos_equipe (id, usuario_id, programa_id, papel_id, data_entrada) VALUES
    ('v-ana', 'ana', 'p-semear', 'coordenacao', '2026-01-10'),
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
