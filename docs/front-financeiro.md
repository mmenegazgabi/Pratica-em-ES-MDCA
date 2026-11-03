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

1. Os comprovantes vão para o Cloudflare R2; sem as variáveis `R2_*` a API responde
   503 ao receber fotos. Para testar sem R2, use o armazenamento em memória dos
   testes num arquivo fora do repositório (veja o passo 1 de "Testar com o backend
   local" em `docs/lancamento-celular.md`; o mesmo arquivo pode cadastrar projetos,
   orçamentos e lançamentos de exemplo na partida, já que tudo fica em memória).
2. API: `cd Backend && FINANCEIRO_API_TOKEN=dev CORS_ORIGINS=http://localhost:8081 PYTHONPATH=.:<pasta do app_local.py> .venv/bin/python -m uvicorn app_local:app --port 8080`
3. Frontend: `cd Frontend && python3 -m http.server 8081`
4. Abra `http://localhost:8081/Financeiro/`, informe nome, papel e o código `dev` e,
   em "Servidor (avançado)", `http://localhost:8080`.

## Código de acesso e perfil

Enquanto não há login (US-08), a tela "Entrar" pede **nome**, **papel** e o **código
de acesso** do Financeiro (`FINANCEIRO_API_TOKEN`). Tudo fica só neste navegador
(`localStorage`); o código não vai para o repositório, que é público. A API recebe
`Authorization: Bearer <código>`, `X-Papel-Usuario` e `X-Usuario-Id` (o nome em
minúsculas e com hífens, ex.: `marcos-vieira`). "Trocar perfil" na barra lateral
apaga a sessão e o código. Quem entra como educador é levado ao app do celular
(`lancamento/`). O celular guarda a sessão em outra chave
(`mdca.financeiro.sessao.celular`), então entrar no celular não troca a sessão do
computador no mesmo navegador.

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

Na tela Entrar também existe o papel **Educador**: ele vai direto para o app do
celular (`lancamento/`), já com o nome e o código informados. A gestão de pessoas e
papéis (Acessos) fica para depois do login da US-08; por enquanto ninguém tem essa
tela.

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
