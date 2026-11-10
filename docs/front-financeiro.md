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
Com `DATABASE_URL`, os dados do Financeiro vão para esse banco (cuidado para não
apontar para o de produção); `FINANCEIRO_ARMAZENAMENTO=memoria` força a memória. Veja
`docs/persistencia-financeiro.md`.

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
| Início (`#/inicio`) | Despesas aguardando aprovação e alertas de orçamento (>= 80%) | Alertas de orçamento e prestações de contas a gerar (vigência terminou ou termina em até 30 dias) | Aprovados sem conciliação |
| Lançamentos (`#/lancamentos`) | Filas Aguardando/Aprovados/Rejeitados/Todos, filtro por projeto, painel com Aprovar e Rejeitar (motivo obrigatório) | não aparece | Abre em Aprovados (consulta) |
| Projetos (`#/projetos`) | Totais, uso por projeto, Novo projeto/Criar orçamento | Só leitura | não aparece |
| Detalhe do projeto (`#/projetos/<orçamento>`) | Orçado, gasto, disponível, gasto / limite por categoria, últimos lançamentos e **Editar orçamento** | Igual, sem Editar orçamento | não aparece |
| Conciliação (`#/conciliacao`) | não aparece | não aparece | Extrato e aprovados lado a lado; marca um de cada e concilia (`PATCH /lancamentos/{id}/conciliar`) |
| Relatórios (`#/relatorios`) | Prestação de contas: projeto, período, PDF (impressão) ou planilha (CSV) | Igual | não aparece |
| Auditoria (`#/auditoria`) | Histórico de ações com busca | Igual | não aparece |

O papel **Educador** vai direto para o app do celular (`lancamento/`). A gestão de
pessoas e papéis fica na tela Administração da página inicial (`Frontend/Admin/`,
veja `docs/login.md`), não no Financeiro.

As barras de uso são verdes abaixo de 80%, amarelas de 80% a 99,99% e vermelhas a
partir de 100% (campo `nivel_alerta`: normal, atencao, estourado). Rotas fora do
papel voltam para o Início.

### O que ainda usa dados de exemplo

`telas/dados-exemplo.js` guarda dados fixos para o que ainda não tem backend: o
**extrato bancário** da Conciliação e o **histórico** da Auditoria. As telas avisam ("exemplo") e nada disso é salvo. "Importar extrato" só
mostra um aviso. O resto (lançamentos, orçamentos, conciliar, prévia e arquivos do
relatório) já usa a API de verdade. Quando existirem as rotas, troque as importações
de `dados-exemplo.js` por chamadas em `base/api.js` e apague o arquivo.

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

- Extrato: importar o arquivo do banco e listar os itens (a Conciliação usa o extrato
  de exemplo).
- Registro de ações para a Auditoria. Pessoas, papéis e convites (tela Acessos)
  dependem da US-08, login.
- Quem rejeitou e quando, para mostrar no aviso da despesa rejeitada no celular.

Tickets de acompanhamento:

- **Trocar foto de rascunho**: em "A completar" só dá para completar; falta trocar a
  foto antes de enviar (em despesa rejeitada já existe "Trocar foto").
- **Segundo orçamento por projeto**: "Criar orçamento" só aparece em projeto sem
  orçamento.
