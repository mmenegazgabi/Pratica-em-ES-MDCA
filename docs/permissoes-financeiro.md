# Matriz de permissões do Módulo Financeiro (T-37 · US-08)

Quem pode fazer o quê no Financeiro, por papel. Os papéis são os da tabela `papeis`, os
mesmos da Gestão. Implementação: `Backend/Financeiro/autenticacao.py`; testes:
`Backend/Financeiro/tests/test_acesso_por_papel.py` (T-36).

## De onde vem o papel

| Como a pessoa chama a API | Papéis | Programas que vê |
|---|---|---|
| **Sessão do login único** (T-35; é o que as telas do Financeiro usam) | Do banco: papéis da plataforma (`usuarios_papeis`) **e** papéis com vínculo ativo em algum programa (`vinculos_equipe`). | Coordenação, Direção e voluntário financeiro: **todos**. Quem só é educador: **só os programas em que tem vínculo ativo**. |
| **Token de serviço** (`FINANCEIRO_API_TOKEN`: testes, scripts e o front da Gestão enquanto ele não migra) | Do cabeçalho `X-Papel-Usuario`, como antes do login. | Todos. |

- **Escolha do papel (T-35):** na sessão, o `X-Papel-Usuario` (o "Entrar como" da tela)
  escolhe com qual dos papéis da pessoa ela age; um papel que ela não tem dá **403**. Sem
  o cabeçalho, vale o único papel permitido na rota que ela tiver (se tiver mais de um,
  **403**).
- Vínculo ativo: sem `data_saida`, ou com `data_saida` depois de hoje.
- Na sessão, quem não tem nenhum papel do Financeiro (ex.: psicólogo, assistente
  social) recebe **403** em todas as rotas do Financeiro.
- Conta desativada (`usuarios.ativo = false`) perde o acesso na hora (**401**).
- A tela do Financeiro decide o menu pelos papéis **da plataforma** que o login devolve.
  Por isso o educador precisa do papel `educador` na plataforma; o vínculo decide em
  quais programas ele trabalha.

## Matriz

| Ação | Rota | Coordenação | Direção | Voluntário financeiro | Educador |
|---|---|---|---|---|---|
| Ver programas | `GET /projetos` | Todos | Todos | Todos | Do vínculo |
| Cadastrar projeto | `POST /projetos` | Sim | — | — | — |
| Encerrar / reabrir projeto | `PATCH /projetos/{id}/status` | Sim | Sim | — | — |
| Ver orçamentos | `GET /orcamentos`, `/orcamentos/{id}`, `/orcamentos/projeto/{id}` | Todos | Todos | Todos | Do vínculo (403 nos outros) |
| Criar orçamento | `POST /orcamentos` | Sim | — | — | — |
| Editar orçamento | `PATCH /orcamentos/{id}` | Sim | — | — | — |
| Lançar despesa (com foto) | `POST /lancamentos`, `/rascunhos/.../completar` | Sim | Sim | Sim | No programa do vínculo |
| Ver lista de lançamentos | `GET /lancamentos` | Todos | Todos | Todos | Só os próprios |
| Ver um lançamento | `GET /lancamentos/{id}` | Sim | Sim | Sim | Só os próprios (404 nos outros) |
| Aprovar / rejeitar despesa | `PATCH /lancamentos/{id}/aprovar`, `/rejeitar` | Sim | Sim | **Não** | — |
| Reenviar despesa rejeitada | `PATCH /lancamentos/{id}/reenviar` | Quem lançou | Quem lançou | Quem lançou | Quem lançou |
| Conciliar com o extrato | `PATCH /lancamentos/{id}/conciliar` | — | — | Sim | — |
| Dashboard da Diretoria | `GET /dashboard/projetos` | — | Sim | — | — |
| Prestação de contas (PDF/XLSX) | `GET /relatorios/prestacao-contas` | Sim | Sim | — | — |
| Auditoria do Financeiro | `GET /auditoria?modulo=financeiro` | Sim | Sim | — | — |
| Notificações e rascunhos | `/notificacoes`, `/rascunhos` | Os próprios | Os próprios | Os próprios | Os próprios |

Sem login, todas as rotas acima respondem **401**.

## Auditoria (T-34)

Ficam em `log_auditoria` (`modulo = 'financeiro'`), na mesma transação da ação: cadastrar
e encerrar/reabrir projeto; criar e editar orçamento; criar, aprovar, rejeitar, reenviar e
conciliar lançamento; gerar prestação de contas; e todo **acesso negado (403)**, com quem
tentou e a rota. A trilha é só de leitura. Detalhes em
[persistencia-financeiro.md](persistencia-financeiro.md).

## Decisões em aberto (para o time)

- **Coordenação por programa ou geral?** Seguindo o plano ("a Coordenação vê tudo"),
  quem tem o papel de Coordenação, mesmo que só pelo vínculo com um programa, vê e aprova
  em todos. Se o time preferir restringir aos programas do vínculo, como na Gestão, a
  mudança fica em `PAPEIS_QUE_VEEM_TODOS_OS_PROGRAMAS`, em `autenticacao.py`.
- **Administração** (`administracao`) não é um papel do Financeiro: hoje recebe 403 nas
  rotas do Financeiro (na Visão integrada da Gestão ela vê os valores).
- **`POST /projetos`** continua existindo e grava na mesma tabela dos programas da Gestão.
  O plano recomenda que só a Gestão cadastre programas.
