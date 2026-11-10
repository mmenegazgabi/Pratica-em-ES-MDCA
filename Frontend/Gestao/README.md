# Frontend/Gestao

Frontend do Módulo de Gestão, publicado no Cloudflare Pages em `/Gestao/`.

Dono: time de Gestão.

A aplicação parte do protótipo da E2 (`Design/Gestao`): mesmo design system, mesmo
menu lateral e mesmas telas. Elas passam a usar a API aos poucos, uma US por vez.
Enquanto uma tela não está ligada à API, ela mostra os dados fictícios do protótipo e
o aviso **Demonstração** no topo.

## Estrutura

```
Gestao/
  index.html      # entrada (carrega app.js como módulo)
  sw.js           # service worker: guarda os arquivos do app para abrir sem rede no navegador
  app.js          # moldura, rotas e telas de demonstração vindas do protótipo
  style.css       # design system MDCA + estilos da aplicação (bloco no fim)
  assets/         # fontes locais (Bitter e General Sans)
  base/
    api.js        # cliente único da API: toda chamada HTTP passa por aqui
    estados.js    # estados carregando, erro e acesso restrito
    papeis.js     # perfis e menu por perfil
    dom.js        # montagem de DOM sem innerHTML
    formulario.js # formulário em diálogo que mostra a recusa da API sem fechar
    fila.js       # fila do aparelho (IndexedDB) do registro em campo e sincronização
    copia-local.js # última agenda e lista da turma, para a chamada sem rede
  telas/          # telas ligadas à API (programas, equipe, usuarios)
  tests/          # node --test + jsdom
```

## Telas ligadas à API

| Tela | Rota da API | Situação |
|---|---|---|
| Programas (lista, com identificador e vigência) | `GET /gestao/programas` | ligada (T-00g; colunas da T-45) |
| Novo programa (`#/programas/novo`) e Editar programa (`#/programas/{id}/editar`) | `POST /gestao/programas`, `PATCH /gestao/programas/{id}` | ligada (T-45) |
| Programa: resumo, convênios e vagas (`#/programas/{id}`) | `GET /gestao/programas/{id}`, `…/convenios`, `…/vagas` | ligada (T-45) |
| Plano e metas (`#/programas/{id}/plano`) | `…/objetivos`, `…/acoes`, `…/metas`, `…/metas/{meta}/registros`, `…/painel` | ligada (T-45) |
| Equipe e espaços do programa (`#/programas/{id}/equipe`) | `…/equipe`, `…/equipe/{vinculo}/desligamento`, `…/espacos`, `/gestao/usuarios`, `/gestao/papeis` | ligada (T-40) |
| Usuários e acessos (administração) | `GET /gestao/usuarios` | ligada, só consulta (T-40) |
| Atividades e frequência (`#/atividades`, `#/atividades/{programa}`) | `…/agenda` | ligada (T-57) |
| Registrar o encontro, em 4 passos (`#/atividades/{programa}/registro/{turma}?data=`) | `…/turmas/{turma}` (lista), `…/turmas/{turma}/atividades`, `…/atividades/{id}/evidencias` (pela fila) | ligada (T-57) |
| Registros no dispositivo · fila local (`#/sincronizacao`) | a fila do aparelho | ligada (T-57) |
| Alertas e busca ativa (`#/alertas`, `#/alertas/{id}`) | `GET /gestao/alertas`, `GET /gestao/alertas/{id}`, `…/acoes`, `…/encerramento` | ligada (T-60) |
| Demais telas | — | demonstração, até a US de cada uma |

- **Equipe e espaços:** aberta pelo link de cada programa na lista. Mostra a equipe com
  o histórico (quem saiu aparece como Desligado) e os espaços. Coordenação e
  administração veem os botões de vincular, desligar (com data de saída obrigatória) e
  cadastrar espaço. Os programas fictícios do protótipo (`p1`…) continuam na
  demonstração.
- **Programas (T-45):** cada programa do cadastro real tem as abas Resumo, Plano e metas
  e Equipe e espaços. O cadastro bloqueia o envio quando falta campo obrigatório e mostra
  a recusa da API (ex.: identificador repetido). No plano, cada meta mostra planejado,
  realizado e percentual; a ação mostra a média dos percentuais das suas metas, porque
  metas da mesma ação podem ter unidades diferentes. Os botões de cadastro, edição e
  registro aparecem para coordenação e administração; quem gerencia de fato será
  conferido pela API na T-87.
- **Usuários e acessos:** contas com perfis da plataforma e vínculos ativos. Criar e
  editar contas ainda não têm rota na API.

Para ligar uma tela nova:

1. Adicione a chamada em `base/api.js` (ex.: `export const listarTurmas = () => requisitar("/gestao/turmas")`).
2. Crie `telas/<tela>.js` com `carregarNaTela(container, buscar, mostrar)`, que já cuida de
   carregando, erro (com "Tentar de novo") e acesso restrito (401 pede o código; 400 sem
   usuário pede o usuário; 403 avisa que o perfil não tem acesso).
3. Em `app.js`, troque a tela de demonstração pela nova e não mostre o aviso de
   demonstração nela (veja `programsApiPage` e `apiScreen` em `render`).
4. Teste em `tests/`.

Nenhum outro arquivo deve chamar `fetch`: o teste `estrutura.test.js` falha se isso acontecer.

## Registro em campo sem conexão (T-57)

- **Tudo passa pela fila do aparelho** (`base/fila.js`): salvar o registro grava o
  encontro (com a chamada) e cada evidência no IndexedDB. Com conexão, a fila envia em
  seguida; sem conexão, o registro fica no aparelho e a fila envia sozinha quando a rede
  volta (evento `online`) ou quando o app é aberto.
- **Sem duplicar:** cada item tem um `registro_id` gerado no aparelho. A API (T-56)
  responde 200 com o que já estava gravado se o mesmo registro chega de novo, então
  reenviar é seguro, mesmo quando a resposta do primeiro envio se perdeu.
- **Fila local** (`#/sincronizacao`, "Registros no dispositivo") mostra cada registro com a confirmação
  ("Enviado em 05/10 às 17:32") ou o erro. Falha de conexão ou do servidor é tentada de
  novo sozinha; recusa da API (por exemplo, pessoa fora da turma) fica com a mensagem e
  os botões "Tentar de novo" e "Descartar". Os enviados saem da lista depois de 7 dias.
- **Sem rede**, a agenda e a lista da turma vêm da última consulta salva no aparelho
  (`base/copia-local.js`), com o aviso da data da cópia. Essas cópias têm nomes de
  crianças e saem ao clicar em "Sair".
- **Abrir sem rede no navegador:** o sistema roda no navegador do celular, sem instalar.
  `sw.js` guarda os arquivos do app (rede primeiro, cópia sem rede) e só atende arquivos
  do próprio site; a API não passa por ele. Ao mudar a lista de arquivos do app, atualize
  `ARQUIVOS` no `sw.js` (o teste `pwa.test.js` confere) e troque a `VERSAO`.

## Acesso e perfis (provisórios)

- **Código de acesso:** até o login único (T-35), a API exige o token de serviço do
  Financeiro. A tela pede o código quando a API responde 401, e ele fica salvo só neste
  aparelho, nas mesmas chaves do Financeiro (um código vale para os dois módulos).
  O campo "Servidor (avançado)" troca o endereço da API, para testar com o backend local.
  Ele aparece também na tela de erro (aberto quando o endereço não é o padrão); em
  branco, volta para a API publicada.
- **Seu usuário:** as rotas de programa e de usuários exigem saber quem chama
  (`X-Usuario-Id`, o `id` da tabela `usuarios`, ex.: `jessica`). A tela de acesso pede o
  usuário junto com o código, e ele pode ser trocado em "Usuário na API" no menu do
  usuário. Fica salvo só neste aparelho, em `mdca.gestao.usuario`. Até o login, qualquer
  pessoa com o código pode se identificar como outro usuário.
- **Perfil:** escolhido na entrada ou no menu do usuário e salvo em `mdca.gestao.papel`.
  Ele só define o que aparece no menu; quem protege os dados é a API (RBAC, T-33).

## Rodar localmente

```bash
python3 -m http.server 8080 --directory Frontend
# abrir http://localhost:8080/Gestao/
```

Para usar o backend local, suba a API em outra porta (ex.: 8000; o CORS já aceita
`http://localhost:8080`) e informe `http://localhost:8000` em "Servidor (avançado)".

## Testes

```bash
cd Frontend/Gestao
npm install
npm test
```
