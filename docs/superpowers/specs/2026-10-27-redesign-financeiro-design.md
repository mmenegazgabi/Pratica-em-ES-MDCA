# Redesign do módulo Financeiro — design

Data: 2026-10-27 · Escopo: só o módulo Financeiro (o módulo de Gestão fica como está)

Esboços aprovados, ao lado deste arquivo:

- `2026-10-27-redesign-financeiro/telas-celular.html` — fluxo do educador no celular
- `2026-10-27-redesign-financeiro/telas-computador.html` — as 7 seções no computador

Os esboços são referência de layout, hierarquia e tom. Os dados neles são fictícios.

## Por que

O protótipo atual (`Design/Financeiro/MDCA Financeiro.dc.html`) não é intuitivo e
parece poluído: cada tela mostra informação demais e não deixa claro o que fazer
primeiro. Há também telas demais falando da mesma coisa (Orçamentos, Projetos e
Detalhes do projeto mostram números do mesmo projeto em lugares diferentes).

A primeira tentativa de redesign ficou "infantil, com cara de IA" (emojis, pílulas
coloridas, cantos muito arredondados). O pedido é algo **sério**.

O redesign vem antes de implementar o restante do front.

## Objetivos

1. Cada tela tem um objetivo principal e uma ação em destaque. Detalhes só aparecem
   quando a pessoa clica no item.
2. Ao entrar, a pessoa vê só o que precisa dela agora.
3. Menos telas: todas as funções das 9 telas atuais continuam existindo, reorganizadas
   em no máximo 4 itens de menu por pessoa.
4. Visual sério, neutro e funcional, ainda reconhecível como MDCA.

## Entrega (decidido)

- **Implementado direto em `Frontend/Financeiro/`, ligado ao backend.** Não haverá
  um novo protótipo em `Design/`; os esboços ao lado deste arquivo são a referência.
- **Fotos "a completar" ficam no servidor como rascunho.** Precisa de backend novo:
  criar um lançamento em rascunho só com a foto, listar os rascunhos do autor, e
  completar o rascunho (vira "Pendente de aprovação"). Rascunho não entra no saldo
  nem aparece para aprovação.
- **"Corrigir e reenviar" edita a mesma despesa**, que volta para "Pendente de
  aprovação". Precisa de backend novo: só o autor edita, só despesa rejeitada; o
  motivo da rejeição anterior continua registrado no histórico/auditoria.

## Backend que o redesign precisa e ainda não existe

Decisão de quem escreveu (conferir): essas rotas entram neste projeto, uma tarefa
por item, e cada tela é ligada à API assim que a rota existir.

- Rascunho de despesa (criar com foto, listar do autor, completar) — acima.
- Editar e reenviar despesa rejeitada — acima.
- Listar lançamentos com filtros (status, projeto, autor, conciliado) — usado por
  Minhas despesas, Lançamentos, Início e Conciliação.
- Contagem de pendências por papel para o Início (pode sair da listagem acima).
- Extrato bancário: importar e listar itens (formato decidido nessa tarefa).
- Gerar prestação de contas (PDF e planilha).
- Pessoas, papéis e auditoria — dependem da US-08; até lá a tela Acessos fica fora
  da primeira entrega.

## Não objetivos

- Redesenhar o módulo de Gestão.
- Mudar regras de negócio ou permissões existentes.
- Dashboard executivo como tela separada (US-07): ele vira a visão geral de Projetos.

## Anti-objetivos (seria fracasso mesmo funcionando)

- Parecer infantil ou "gerado por IA": emojis, cores vivas em grandes áreas, pílulas
  e cantos muito arredondados, ilustrações decorativas.
- Painéis cheios de números e gráficos na tela de entrada.
- O educador ter que preencher um formulário longo na hora da compra.

## Quem usa e onde

| Pessoa | Papel | Aparelho | Tarefa principal |
|---|---|---|---|
| Marcos | Educador | Celular | Lançar despesas com foto do comprovante |
| Luana | Coordenação | Computador | Aprovar ou rejeitar despesas; acompanhar orçamentos; gerar prestação de contas |
| Lucas | Voluntário financeiro | Computador | Conciliar lançamentos aprovados com o extrato |
| Jane | Diretoria | Computador | Acompanhar orçamentos; ler relatórios e auditoria |
| Ana | Administração | Computador | Gerenciar pessoas, papéis e acesso a projetos |

## Linha visual (decidida: "B · Neutro e funcional")

- **Fundo** branco; cinzas claros para superfícies secundárias (barra lateral,
  cabeçalho de tabela).
- **Verde MDCA só onde importa:** botão de ação principal, item ativo do menu,
  status "Aprovado", barras de progresso normais. Verde de ação nos esboços: `#3f8a3a`;
  fundo do item ativo `#ecf5ea`, texto `#1f4d1c`.
- **Uma fonte sem serifa em tudo** — Inter nos esboços (gratuita, Google Fonts).
  Substitui Bitter + General Sans/Archivo do design system atual.
- **Cantos discretos:** 6–8 px em botões, campos e caixas. Sem pílulas.
- **Bordas finas** (`#e4e4e7`) em vez de sombras. Sombra só no painel lateral
  que se sobrepõe.
- **Ícones de traço fino** (Lucide). Nenhum emoji.
- **Números** com algarismos tabulares, alinhados à direita em tabelas.
- **Status** como etiquetas pequenas com fundo bem claro, mantendo o código de cor
  atual: pendente amarelo, aprovado verde, rejeitado vermelho, conciliado azul.
- **Logo** só na barra lateral (nos esboços é o texto "MDCA Finanças"; usar o logo
  real). As cores vivas do logo não se espalham pelas telas.

## Celular — educador

Aprovado: "fotografa agora, completa depois". Ver `telas-celular.html`.

1. **Minhas despesas** (tela principal). De cima para baixo:
   - botão grande "Fotografar comprovante";
   - **Precisa de ajuste** — despesas rejeitadas, com o valor e o status;
   - **A completar** — fotos tiradas ainda sem dados (miniatura + horário);
   - **Enviadas** — últimas despesas com status; "Ver todas".
   Barra inferior: Despesas, Avisos, Perfil.
2. **Câmera.** Abre direto na câmera traseira, com opção Galeria. Depois da foto,
   ela é salva em "A completar" e aparece um aviso com "Completar agora".
   O educador pode fechar e voltar depois.
3. **Completar despesa** — uma tela só: foto (com "Trocar foto"), valor, projeto,
   categoria (opções do projeto escolhido, como botões), "O que foi comprado" e data.
   Data vem preenchida com a da foto; projeto lembra o último usado.
   Ação: "Enviar para aprovação".
4. **Despesa rejeitada.** Valor, status, o motivo informado pela coordenação em
   destaque (com quem rejeitou e quando), a foto e a descrição. Uma ação:
   "Corrigir e reenviar".

Regras que vêm do código atual (`docs/lancamento-celular.md`) e continuam valendo:
campos com 16 px, área de toque ≥ 44 px, sem rolagem horizontal em 320 px, fotos
reduzidas no aparelho antes do envio.

## Computador — navegação

Barra lateral à esquerda com o logo, os itens de menu e, no rodapé, a pessoa logada
e o papel. Cada pessoa vê só os itens que usa:

| Menu | Reúne das telas atuais | Luana | Lucas | Jane | Ana |
|---|---|---|---|---|---|
| Início | nova | ✓ | ✓ | ✓ | ✓ |
| Lançamentos | 4 Lançamentos (com painel) | ✓ | ✓ | | |
| Projetos | 1 Orçamentos e Saldo, 2 Cadastro de orçamento, 10 Projetos, 11 Detalhes do projeto | ✓ | | ✓ | |
| Conciliação | 6 Conciliação bancária | | ✓ | | |
| Relatórios | 7 Prestação de contas | ✓ | | ✓ | |
| Acessos / Auditoria | 9 Papéis, acessos e auditoria | | | só aba Auditoria (item "Auditoria") | ✓ |

Luana também lê a auditoria (como hoje); no menu dela isso entra como um quinto item
"Auditoria" ou dentro de Relatórios — ver "Deixado para quem constrói".

O item Início mostra um contador com o número de pendências.

## Computador — telas

Ver `telas-computador.html` (na ordem abaixo).

1. **Início.** Saudação + "N itens precisam de você". Uma ou duas tabelas curtas,
   cada linha com uma ação. Conteúdo por papel:
   - Luana: despesas aguardando aprovação ("Analisar") e alertas de orçamento
     acima de 80% ("Ver projeto");
   - Lucas: lançamentos aprovados sem conciliação, destacando os abertos há mais de
     7 dias;
   - Jane: alertas de orçamento e prestações de contas a gerar;
   - Ana: convites ou acessos pendentes, se houver.
   Sem pendências: mensagem curta ("Nada pendente") no lugar das tabelas. Sem gráficos.
2. **Lançamentos.** Filtros por status como abas com contagem (Aguardando, Aprovados,
   Rejeitados, Todos) e filtro de projeto. Tabela: despesa (categoria + quem + projeto),
   data, valor. Clicar numa linha abre um **painel lateral** sem trocar de tela:
   status, valor, descrição, foto do comprovante, projeto, categoria, data, quem enviou,
   saldo após a aprovação, e os botões **Rejeitar** e **Aprovar**. Rejeitar pede o
   motivo (obrigatório, até 500 caracteres — regra da T-16).
3. **Projetos.** Quatro números no topo (Orçado, Gasto, Disponível, Aguardando
   aprovação) e uma linha por projeto: nome, centro de custo, vigência, orçado, gasto,
   barra de uso com %. Barra amarela a partir de 80%, vermelha em 100%. Botão
   "Novo projeto". Para a Jane, esta é a visão executiva.
   **Regra (decidida):** um orçamento só pode ser criado para um projeto que já
   existe. Na interface, "Criar orçamento" só aparece dentro de um projeto; no
   backend, `POST /orcamentos` com projeto inexistente é recusado.
4. **Detalhe do projeto.** Nome, centro de custo, vigência; três números (Orçado,
   Gasto, Disponível com % usado — destacado em amarelo/vermelho nos limites);
   orçamento por categoria com barras; últimos lançamentos com status ("Ver todos"
   leva a Lançamentos filtrado pelo projeto). "Editar orçamento" abre o formulário de
   orçamento (vigência, valor, categorias), com as validações atuais.
5. **Conciliação.** Duas colunas: extrato bancário do mês | lançamentos aprovados
   não conciliados. O Lucas marca um item de cada lado; uma barra embaixo mostra o
   par e o botão **Conciliar**. Itens de mesmo valor aparecem sugeridos; lançamentos
   abertos há mais de 7 dias têm aviso. Botão "Importar extrato". Usa
   `PATCH /lancamentos/{id}/conciliar` (T-21) com a referência do item do extrato.
6. **Relatórios.** Esquerda: projeto, período, formato (PDF ou Planilha), aviso de
   lançamentos não conciliados no período, botão "Gerar relatório". Direita: prévia
   do documento.
7. **Acessos.** Duas abas: **Pessoas e papéis** (tabela pessoa, papel, projetos,
   "Editar"; botão "Convidar pessoa") e **Auditoria** (histórico de ações).
   Coordenação e Diretoria veem só a aba Auditoria.

## Restrições

- O front atual é HTML, CSS e JavaScript puro em módulos (`Frontend/Financeiro/`),
  testado com `node --test`. Sem framework.
- Autenticação ainda é provisória (código de acesso salvo no aparelho; papel no
  cabeçalho `X-Papel-Usuario`) até a US-08.
- Repositório público: nada de segredo no código.

## Permissões que já existem (do mapa de telas atual)

- Projetos e orçamentos: Luana cria e edita; Jane só lê. Para a Jane, "Novo projeto"
  e "Editar orçamento" não aparecem.
- Lançamentos: Marcos só nos seus projetos; Lucas com edição limitada à conciliação.
- Acessos: Ana gerencia; Luana e Jane leem a auditoria.

## Decisões de quem escreveu este documento (conferir)

- **Celular continua sendo uma entrada separada** (como `Frontend/Financeiro/lancamento/`
  hoje), não uma aplicação única responsiva com o computador.
- **Quem está logado:** enquanto a US-08 não existe, o front usa o código de acesso
  atual mais um seletor de perfil (enviado em `X-Papel-Usuario`) para escolher o menu
  e o Início de cada papel. Na US-08 o perfil passa a vir do login.
- **Formato do extrato:** fora do escopo do redesign. A tela só precisa do botão
  "Importar extrato" e da lista; o formato (OFX/CSV) é decidido na tarefa de
  conciliação.

## Deixado para quem constrói

- Tokens exatos (escala de cinzas, espaçamento, tamanhos de fonte) dentro da linha
  visual acima.
- Estados vazios, de carregamento e de erro de cada tela, seguindo o mesmo tom.
- Como a tela de Completar valida e mostra erros (seguir o formulário atual).
