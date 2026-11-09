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
  pessoas.py      # pessoas atendidas, núcleos familiares, responsáveis e duplicidade (US-03)
  autorizacoes.py # autorizações (uso de imagem): situação, revogação e uso externo
  trajetoria.py   # linha do tempo da pessoa atendida (T-49)
  erros.py        # erros de regra do cadastro de pessoas, traduzidos em HTTP pelas rotas
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
- Autenticação: o token de sessão do login único (T-35, veja
  [`docs/login-unico.md`](../../docs/login-unico.md)) ou, durante a transição, o token de
  serviço do Financeiro (`FINANCEIRO_API_TOKEN`).

## Rotas

### Programas e plano de ação (US-02)

Sobre o cadastro canônico de Programas/Projetos
(tabela `projetos`, ARQ-02, a mesma que o Financeiro usa em orçamentos e lançamentos):

| Rota | O que faz |
|---|---|
| `GET /gestao/programas` | Lista os programas (id, nome, identificador e vigência) |
| `POST /gestao/programas` | Cadastra um programa: `nome`, `identificador`, `publico`, `responsavel`, `vigencia_inicio`, `vigencia_fim` e `descricao` opcional |
| `GET /gestao/programas/{id}` | Dados completos do programa |
| `PATCH /gestao/programas/{id}` | Edita os dados do programa: só os campos enviados mudam, e o resultado segue as regras do cadastro (um programa antigo, só com nome, precisa ganhar os obrigatórios) |
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

### Pessoas atendidas (US-03)

| Rota | O que faz |
|---|---|
| `GET /gestao/pessoas?programa_id=&busca=` | Pessoas dos programas em que a pessoa usuária atua (administração: todas); busca por nome, núcleo ou responsável |
| `POST /gestao/pessoas/duplicidades` | Possíveis duplicados de um cadastro ainda não concluído (etapa de revisão); não grava nada |
| `POST /gestao/pessoas` | Cadastra a pessoa com núcleo familiar (`nucleo_familiar_id` existente ou `nucleo_familiar_nome` novo) e responsáveis (`id` existente ou `nome` novo, com `parentesco` e `responsavel_legal`) |
| `GET /gestao/pessoas/{pessoa_id}` | Detalhe com idade, núcleo, responsáveis, documentos e autorizações |
| `GET /gestao/pessoas/{pessoa_id}/trajetoria` | Linha do tempo, do mais recente ao mais antigo: cadastro, responsáveis incluídos depois, documentos e autorizações (registro, revogação e vencimento). Frequência, atendimentos e matrículas entram com as US delas (T-49) |
| `POST /gestao/pessoas/{pessoa_id}/responsaveis` | Inclui um responsável |
| `POST /gestao/pessoas/{pessoa_id}/documentos` | Registra os dados do documento (`tipo`, `nome_arquivo`, `tamanho`); o envio do arquivo ainda não existe: as telas da T-49 registram só esses dados |
| `POST /gestao/pessoas/{pessoa_id}/autorizacoes` | Registra autorização (`tipo: uso_de_imagem`, `valida_ate`, `valida_de` opcional = hoje, `documento_id` opcional) |
| `POST /gestao/pessoas/{pessoa_id}/autorizacoes/{autorizacao_id}/revogacao` | Revoga; fica na auditoria (`autorizacao_revogada`) |
| `POST /gestao/pessoas/uso-de-imagem` | `{pessoa_ids, uso}`: uso externo só com autorização de imagem vigente de todos |
| `GET /gestao/nucleos-familiares?busca=` | Núcleos com alguém nos programas em que a pessoa usuária atua |

**Quem pode:** consultam quem tem vínculo ativo no programa da pessoa e a
administração; a direção não vê cadastros individuais. Cadastram e alteram a
coordenação e a assistência social vinculadas ao programa, e a administração.

**Regras:**

- **Possível duplicidade:** mesmo nome (sem diferenciar maiúsculas, espaços e acentos)
  e, além disso, mesmo nascimento **ou** mesmo responsável. O `POST /gestao/pessoas`
  responde **409** com `detail.codigo = "possivel_duplicidade"` e `detail.candidatos`, e
  não grava nada. Para cadastrar mesmo assim, reenvie com `confirmar_duplicidade: true`;
  a confirmação fica na auditoria (`duplicidade_confirmada`).
- **Responsável legal:** menor de 18 anos sem nenhum responsável com
  `responsavel_legal: true` → **400**.
- **Situação da autorização** (calculada, não gravada): `revogada` se tem revogação,
  `vencida` se `valida_ate` já passou, senão `vigente`. O início da validade não pode
  estar no futuro.
- **Uso externo de imagem:** liberado só se cada pessoa tem ao menos uma autorização de
  imagem vigente; senão **409** com `detail.codigo = "uso_de_imagem_bloqueado"` e
  `detail.bloqueios` (motivo `vencida`, `revogada` ou `sem_autorizacao`). Uso interno é
  sempre liberado. A mesma regra (`autorizacoes.verificar_uso_de_imagem`) serve às
  evidências de atividade (T-56).

## Acesso às rotas de programa

- Quem chama vem do **token de sessão** do login único (T-35). Sem sessão, durante a
  transição, vale o cabeçalho `X-Usuario-Id` junto com o token de serviço, como no
  Financeiro; sem nenhum dos dois, a resposta é 400. Com token de sessão, o
  `X-Usuario-Id` é ignorado.
- Os papéis vêm do banco, não de cabeçalho: os da plataforma em `usuarios_papeis`
  (direção e administração) e os do programa em `vinculos_equipe`.
- **Vínculo ativo** é o que não tem data de saída ou tem a saída no futuro. A partir
  da data de saída o acesso ao programa é bloqueado, e o vínculo fica no histórico.
- Usuário inexistente ou desativado não acessa nenhum programa.
- Toda negação grava em `log_auditoria` (módulo `gestao`, ação `acesso_negado`,
  programa, método e rota) antes de responder 403. Na lista de usuários o alvo é
  `usuarios`, sem id.
- Pelo caminho antigo (token de serviço + `X-Usuario-Id`), quem tem o token ainda pode
  se identificar como qualquer usuário; esse caminho sai quando os dois frontends
  usarem o login.
- Ainda não há rota de cadastro de usuários (a API só consulta): para começar, inclua
  um administrador direto no banco. Para entrar pelo login, a conta precisa de e-mail e
  de senha, definida com `scripts/definir-senha.py <email>`. Para testar as telas de
  Gestão, vale incluir também um programa, uma coordenação e uma educadora:

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
