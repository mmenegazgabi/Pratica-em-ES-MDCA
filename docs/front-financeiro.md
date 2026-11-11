# Financeiro no computador (redesign)

Visual B "Neutro e funcional" (esboços em
`docs/superpowers/specs/2026-10-27-redesign-financeiro/telas-computador.html` e
`telas-celular.html`; desenho em `docs/superpowers/specs/2026-10-27-redesign-financeiro-design.md`).
O celular do educador está em `docs/lancamento-celular.md`.

- Endereço publicado: `https://mdca-sistema.pages.dev/Financeiro/`
- Arquivos: `Frontend/Financeiro/` (`index.html`, `app.js`, `style.css`), `base/`
  (tokens, API, sessão, rotas, DOM), `telas/` (uma tela por arquivo, com o módulo
  `-dados.js` ao lado quando há regra) e `lancamento/` (celular)
- Testes: `cd Frontend/Financeiro && node --test` e `cd Backend && .venv/bin/python -m pytest -q`

## Como rodar local

Siga "Rodar local com Postgres" em `docs/login.md` (a API integrada precisa rodar a
partir de `Backend/`, com `DATABASE_URL`). Sem as variáveis `R2_*`, a API responde 503
ao receber fotos; para testar sem R2, veja `docs/lancamento-celular.md`. Depois,
abra `http://localhost:8090/`, entre e escolha Financeiro.

## Login e papel

O Financeiro não tem tela de entrada própria: usa a sessão do login único
(`docs/login.md`, chave `mdca.sessao`). Sem sessão, a página volta para a página
inicial. Quem tem mais de um papel financeiro (coordenação, direção, voluntário
financeiro) escolhe em "Entrar como"; a escolha fica em `mdca.financeiro.papel`.
"Trocar papel" na barra lateral reabre a escolha e "Sair" encerra a sessão da
plataforma. A API recebe `Authorization: Bearer <token da sessão>` e
`X-Papel-Usuario` (que precisa ser um dos papéis da pessoa); `X-Usuario-Id` não é
mais enviado. Quem só tem o papel educador é levado ao app do celular (`lancamento/`).

## Telas por papel

| Tela | Coordenação | Direção | Voluntário financeiro |
| --- | --- | --- | --- |
| Início (`#/inicio`) | Despesas aguardando aprovação e alertas de orçamento (>= 80%) | Alertas de orçamento, prestações de contas a gerar (vigência terminou ou termina em até 30 dias) e orçado, realizado e saldo por projeto (`GET /dashboard/projetos`, com total) | Aprovados sem conciliação |
| Lançamentos (`#/lancamentos`) | Filas Aguardando/Aprovados/Rejeitados/Todos, filtro por projeto, painel com Aprovar e Rejeitar (motivo obrigatório) | não aparece | Abre em Aprovados (consulta) |
| Projetos (`#/projetos`) | Totais, uso por projeto (projeto encerrado aparece como "Encerrado"), Novo projeto/Criar orçamento | Só leitura | não aparece |
| Detalhe do projeto (`#/projetos/<orçamento>`) | Orçado, gasto, disponível, gasto / limite por categoria, últimos lançamentos, **Editar orçamento** e **Encerrar/Reativar projeto** (com confirmação, `PATCH /projetos/{id}/status`) | Igual, sem Editar orçamento | não aparece |
| Conciliação (`#/conciliacao`) | não aparece | não aparece | Extrato em aberto (`GET /extrato?em_aberto=true`) e aprovados lado a lado; marca um de cada e concilia (`PATCH /lancamentos/{id}/conciliar` com o `id` do item em `referencia_extrato`); **Importar extrato (CSV)** (`POST /extrato`). A Conciliação e a importação são do voluntário financeiro; a API também aceita a importação pela coordenação, mas o front não oferece |
| Relatórios (`#/relatorios`) | Prestação de contas: projeto, período, prévia na tela e arquivo oficial da API em PDF ou Planilha (XLSX) (`GET /relatorios/prestacao-contas`) | Igual | não aparece |
| Auditoria (`#/auditoria`) | Histórico de ações da plataforma (`GET /auditoria`): busca (espera 300 ms), módulo e período | Igual | não aparece |

O papel **Educador** vai direto para o app do celular (`lancamento/`). A gestão de
pessoas e papéis fica na tela Administração da página inicial (`Frontend/Admin/`,
veja `docs/login.md`), não no Financeiro.

As barras de uso são verdes abaixo de 80%, amarelas de 80% a 99,99% e vermelhas a
partir de 100% (campo `nivel_alerta`: normal, atencao, estourado). Rotas fora do
papel voltam para o Início.

### Dados de exemplo

Nenhum. `telas/dados-exemplo.js` (extrato e histórico fixos) saiu: a Conciliação e a
Auditoria usam a API. A geração do relatório também deixou de ser feita no navegador
(saíram o CSV montado no front e a impressão com `window.print`): o arquivo é o oficial
do backend, com o nome do `Content-Disposition` (ou
`prestacao-de-contas-<projeto>-<início>-a-<fim>.<pdf|xlsx>` se o cabeçalho não vier).
A prévia na tela continua calculada dos lançamentos aprovados.

Detalhes das telas ligadas à API:

- **Relatórios**: `baixarRelatorio(parametros)` em `base/api.js` devolve
  `{status, blob, nome, corpo}`; o projeto é o `projeto_id` do orçamento escolhido.
  Erros (404, 422, 403, sem conexão) aparecem abaixo do botão.
- **Conciliação**: o extrato tem saída negativa; "mesmo valor" e o aviso de valor
  diferente comparam sem o sinal. A importação mostra "N itens importados, M repetidos
  ignorados." (repetidos = linhas que já estavam guardadas) ou o erro da API, que diz
  a linha ("Linha 3: valor inválido."). Arquivo acima de 1 MB nem é enviado. Enquanto importa, "Conciliar" fica
  bloqueado (e vice-versa). Se o
  extrato não carregar, só a coluna dele mostra o erro. O extrato fica em memória no
  backend (como os outros dados do Financeiro até a E3): reiniciar a API apaga o que
  foi importado.
- **Auditoria**: colunas Data/hora (horário de Brasília), Pessoa (nome, ou o id),
  Módulo, Ação (códigos conhecidos com rótulo em português) e Descrição. Só a
  resposta do pedido mais recente aparece; período invertido avisa sem chamar a API;
  a busca pendente é cancelada ao sair da tela.
- **Início da direção**: o painel "Projetos" lista ativos primeiro e os encerrados
  marcados, com uma linha de total. Se `GET /dashboard/projetos` falhar, as pendências
  continuam e o painel mostra o aviso.

## Rotas do backend adicionadas na parte 1

- `GET /lancamentos` — filtros `status`, `orcamento_id`, `conciliado` e `meus`;
  mais antigos primeiro; exige papel.
- `POST /rascunhos`, `GET /rascunhos`, `POST /rascunhos/{id}/completar` — foto agora,
  dados depois.
- `PATCH /lancamentos/{id}/reenviar` — corrige e reenvia despesa rejeitada.
- `PATCH /orcamentos/{id}` — edita valor, vigência e categorias (o valor não pode
  ficar abaixo do gasto; o servidor responde 400).
- `POST /projetos` e `GET /projetos` — cadastro de projetos; `POST /orcamentos` só
  aceita projeto cadastrado.
- `GET /orcamentos` (lista com `projeto_nome`, `realizado`, `percentual_consumido`,
  `nivel_alerta`) e `aprovado_em` nos lançamentos.

CORS só permite GET, POST, PATCH e OPTIONS; por isso não há PUT nem DELETE.

## Falta no backend

- As ações do Financeiro ainda não entram em `log_auditoria` (os dados do Financeiro
  estão em memória até a E3): a Auditoria mostra hoje as ações da plataforma e da
  Gestão.
- Quem rejeitou e quando, para mostrar no aviso da despesa rejeitada no celular.

Tickets de acompanhamento:

- **Trocar foto de rascunho**: em "A completar" só dá para completar; falta trocar a
  foto antes de enviar (em despesa rejeitada já existe "Trocar foto").
- **Segundo orçamento por projeto**: "Criar orçamento" só aparece em projeto sem
  orçamento.
