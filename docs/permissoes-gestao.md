# Matriz de permissões do Módulo de Gestão

O que cada papel pode fazer no Módulo de Gestão (T-42 · US-01). Complementa a matriz do
Financeiro (T-37), que deve ficar ao lado deste arquivo, em `docs/`.

A matriz descreve o que a **API aplica hoje**. Quem decide é o backend
([`Backend/Gestao/acesso.py`](../Backend/Gestao/acesso.py)), sempre com os papéis lidos
do banco. O menu do frontend só esconde telas e não protege nenhum dado. O teste
[`test_matriz_permissoes_doc.py`](../Backend/Gestao/tests/test_matriz_permissoes_doc.py)
compara a seção [Fonte no código](#fonte-no-código) com o `acesso.py`. Se uma regra
mudar no código e não aqui, o CI falha.

Quando o middleware de autorização (T-33) substituir o `acesso.py`, ele precisa manter
estas regras, ou este documento precisa mudar junto.

## Papéis

São os ids da tabela `papeis`, que é a mesma lista usada pelo Financeiro. Cada papel é
atribuído de um destes dois jeitos:

| Papel | id | Onde é atribuído | Alcance |
|---|---|---|---|
| Coordenação | `coordenacao` | vínculo com o programa (`vinculos_equipe`) | só os programas em que tem vínculo ativo |
| Educadora / Educador social | `educador` | vínculo com o programa | só os programas em que tem vínculo ativo |
| Assistente social | `assistente_social` | vínculo com o programa | só os programas em que tem vínculo ativo |
| Psicóloga / Psicólogo | `psicologo` | vínculo com o programa | só os programas em que tem vínculo ativo |
| Direção | `direcao` | papel da plataforma (`usuarios_papeis`) | todos os programas |
| Administração do sistema | `administracao` | papel da plataforma | todos os programas |

O papel `voluntario_financeiro` é do Financeiro e não dá nenhum acesso na Gestão.

**Vínculo ativo** é um vínculo sem data de saída, ou com a data de saída ainda no
futuro. A partir da data de saída, o acesso ao programa é bloqueado e o vínculo continua
no histórico. Uma pessoa com mais de um vínculo no mesmo programa soma as permissões de
todos eles.

## Matriz por funcionalidade

Legenda: **Todos** = em todos os programas · **Programa** = só nos programas em que
tem vínculo ativo · **—** = não pode (a API responde 403 e registra a tentativa).

### Equipe e espaços do programa (US-01)

| Ação | Coordenação | Educador | Assist. social | Psicólogo | Direção | Administração |
|---|---|---|---|---|---|---|
| Consultar equipe, histórico e espaços | Programa | Programa | Programa | Programa | Todos | Todos |
| Vincular profissional, registrar desligamento e cadastrar espaço | Programa | — | — | — | — | Todos |

Rotas: `GET`/`POST /gestao/programas/{id}/equipe`,
`PATCH …/equipe/{vinculo}/desligamento`, `GET`/`POST …/espacos`.

A lista de equipe ativa é a mesma que será usada para escolher o responsável de uma
turma (T-51).

### Usuários da plataforma (US-01)

| Ação | Coordenação | Educador | Assist. social | Psicólogo | Direção | Administração |
|---|---|---|---|---|---|---|
| Listar usuários e seus vínculos | Se coordena algum programa | — | — | — | — | Sim |
| Consultar o catálogo de papéis | Sim | Sim | Sim | Sim | Sim | Sim |

Rotas: `GET /gestao/usuarios` e `GET /gestao/papeis`. A coordenação precisa da lista
para escolher quem vincular à equipe. Criar e editar contas ainda não tem rota na API.

### Visão integrada do programa (US-12)

| Ação | Coordenação | Educador | Assist. social | Psicólogo | Direção | Administração |
|---|---|---|---|---|---|---|
| Consultar a execução física (metas do plano) | Programa | Programa | Programa | Programa | Todos | Todos |
| Ver os valores financeiros (orçado, realizado, saldo) | Programa | — | — | — | Todos | Todos |

Rota: `GET /gestao/programas/{id}/visao-integrada`. Quem não vê os valores
financeiros recebe a visão com `financeira: null`, sem 403. Toda consulta é registrada
na auditoria (`consulta_visao_integrada`).

### Pessoas atendidas (US-03)

Os cadastros têm dados de crianças e famílias. A Direção não vê cadastros individuais.

| Ação | Coordenação | Educador | Assist. social | Psicólogo | Direção | Administração |
|---|---|---|---|---|---|---|
| Listar, consultar o cadastro e a trajetória, buscar núcleos familiares | Programa | Programa | Programa | Programa | — | Todos |
| Verificar o uso de imagem de um material | Programa | Programa | Programa | Programa | — | Todos |
| Cadastrar pessoa (inclui a checagem de duplicidade) | Programa | — | Programa | — | — | Todos |
| Incluir responsável, registrar documento (com o arquivo, T-88) | Programa | — | Programa | — | — | Todos |
| Baixar o arquivo de um documento (registrado na auditoria) | Programa | Programa | Programa | Programa | — | Todos |
| Registrar e revogar autorização (uso de imagem) | Programa | — | Programa | — | — | Todos |

Rotas: `/gestao/pessoas…` e `GET /gestao/nucleos-familiares`. Sem filtro de programa,
a lista de pessoas e a busca de núcleos trazem só os programas da pessoa usuária. Para
a Direção, as duas voltam vazias, sem 403. O programa que vale é sempre o da pessoa
cadastrada.

### Atividades, chamada e evidências (US-05)

| Ação | Coordenação | Educador | Assist. social | Psicólogo | Direção | Administração |
|---|---|---|---|---|---|---|
| Consultar a agenda de encontros (sem nomes) | Programa | Programa | Programa | Programa | Todos | Todos |
| Registrar encontro com a chamada e enviar evidência | Programa | Programa | — | — | — | Todos |
| Consultar o encontro com a chamada e baixar evidência | Programa | Programa | Programa | Programa | — | Todos |

Rotas: `GET /gestao/programas/{id}/agenda`, `POST …/turmas/{turma}/atividades`,
`GET …/atividades/{id}`, `POST …/atividades/{id}/evidencias` e
`GET …/evidencias/{id}/arquivo`. A chamada e as evidências mostram crianças e
adolescentes, então consultá-las segue a regra de pessoas (a Direção não vê). Todo
download de evidência é registrado na auditoria (`download_evidencia`).

### Alertas de infrequência e busca ativa (US-06)

| Ação | Coordenação | Educador | Assist. social | Psicólogo | Direção | Administração |
|---|---|---|---|---|---|---|
| Consultar os alertas e o histórico do acompanhamento | Programa | — | Programa | — | — | Todos |
| Registrar ação de busca ativa e encerrar o alerta (com justificativa) | Programa | — | Programa | — | — | Todos |
| Configurar o limite de faltas do programa | pela edição do programa (pendente da T-33) | | | | | |

Rotas: `GET /gestao/alertas`, `GET /gestao/alertas/{id}`, `POST …/acoes` e
`POST …/encerramento`. Os alertas nascem sozinhos quando uma chamada é registrada; a
geração e cada ação e encerramento ficam na auditoria. Como no protótipo, educadores e
direção não veem os alertas (o resultado dos contatos com a família é sensível).

Na trajetória da pessoa (T-60), quem vê o cadastro vê também que houve o alerta, cada
ação de busca ativa e o encerramento; o resultado das ações e a justificativa do
encerramento só aparecem para quem acompanha os alertas do programa.

### Programas e plano de ação (US-02): pendente da T-33

| Ação | Hoje |
|---|---|
| Listar, consultar, cadastrar e editar programas; convênios e vagas | qualquer chamada autenticada |
| Objetivos, ações, metas, registros do realizado e painel | qualquer chamada autenticada |

Rotas: `/gestao/programas`, `/gestao/programas/{id}` e as sub-rotas de convênios,
vagas e plano de ação. Essas rotas só exigem autenticação e ainda não conferem o
papel. **A regra pretendida precisa ser definida e aplicada na T-33.** Sugestão,
seguindo o resto da matriz: Coordenação gerencia o próprio programa, Administração
gerencia todos, Direção e o restante da equipe só consultam.

### Ainda sem rota na API

Frequência consolidada, atendimentos técnicos (social e psicológico), relatórios,
rede e a consulta à trilha de auditoria ainda não têm API. A permissão de
cada um entra nesta matriz junto com a US correspondente. Por enquanto, as telas
dessas funcionalidades são só demonstração, com o menu por perfil em
[`Frontend/Gestao/base/papeis.js`](../Frontend/Gestao/base/papeis.js).

## Regras gerais

- **Quem chama:** o usuário vem do token de sessão do login único (T-35). Durante a
  transição, a API também aceita o token de serviço junto com o cabeçalho
  `X-Usuario-Id`. Os papéis são sempre lidos do banco, nunca de um cabeçalho.
- **Conta desativada** não acessa nada, mesmo que ainda tenha vínculo aberto.
- **Acesso negado:** a API responde 403, e a tentativa é gravada em `log_auditoria`
  (`modulo = gestao`, `acao = acesso_negado`). O registro guarda quem tentou, o alvo
  (programa, pessoa ou lista de usuários), a operação, o método e a rota. Ele
  permanece mesmo com o 403, e a tabela não aceita alteração nem exclusão.
- **Não são negação de acesso**, e por isso não geram registro: 401 (sem autenticação),
  400 (sem identificação do usuário) e 404 (programa ou pessoa inexistente; o 404 vem
  antes da checagem de papel).

## Fonte no código

Conjuntos de papéis usados pelo `acesso.py`. O teste lê este bloco e compara com o
código.

```python
PAPEIS_QUE_CONSULTAM_TODOS = {"direcao", "administracao"}
PAPEIS_QUE_GERENCIAM_TODOS = {"administracao"}
PAPEIS_QUE_GERENCIAM_O_PROGRAMA = {"coordenacao"}
PAPEIS_COM_TODAS_AS_PESSOAS = {"administracao"}
PAPEIS_QUE_CADASTRAM_PESSOAS = {"coordenacao", "assistente_social"}
PAPEIS_QUE_VEEM_FINANCEIRO_DE_TODOS = {"direcao", "administracao"}
PAPEIS_QUE_VEEM_FINANCEIRO_DO_PROGRAMA = {"coordenacao"}
PAPEIS_QUE_REGISTRAM_ATIVIDADES = {"coordenacao", "educador"}
PAPEIS_QUE_ACOMPANHAM_ALERTAS = {"coordenacao", "assistente_social"}
```

Qualquer vínculo ativo no programa, de qualquer papel, permite consultar o programa e
os cadastros de pessoas dele.
