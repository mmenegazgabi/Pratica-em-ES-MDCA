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
  app.js          # moldura, rotas e telas de demonstração vindas do protótipo
  style.css       # design system MDCA + estilos da aplicação (bloco no fim)
  assets/         # fontes locais (Bitter e General Sans)
  base/
    api.js        # cliente único da API: toda chamada HTTP passa por aqui
    estados.js    # estados carregando, erro e acesso restrito
    papeis.js     # perfis e menu por perfil
    dom.js        # montagem de DOM sem innerHTML
  telas/          # telas ligadas à API (hoje: programas.js)
  tests/          # node --test + jsdom
```

## Telas ligadas à API

| Tela | Rota da API | Situação |
|---|---|---|
| Programas (lista) | `GET /gestao/programas` | ligada (T-00g) |
| Demais telas | — | demonstração, até a US de cada uma |

Para ligar uma tela nova:

1. Adicione a chamada em `base/api.js` (ex.: `export const listarTurmas = () => requisitar("/gestao/turmas")`).
2. Crie `telas/<tela>.js` com `carregarNaTela(container, buscar, mostrar)`, que já cuida de
   carregando, erro (com "Tentar de novo") e acesso restrito (401 pede o código; 403 avisa
   que o perfil não tem acesso).
3. Em `app.js`, troque a tela de demonstração pela nova e não mostre o aviso de
   demonstração nela (veja `programsApiPage` e `apiScreen` em `render`).
4. Teste em `tests/`.

Nenhum outro arquivo deve chamar `fetch`: o teste `estrutura.test.js` falha se isso acontecer.

## Acesso e perfis (provisórios)

- **Código de acesso:** até o login único (T-35), a API exige o token de serviço do
  Financeiro. A tela pede o código quando a API responde 401, e ele fica salvo só neste
  aparelho, nas mesmas chaves do Financeiro (um código vale para os dois módulos).
  O campo "Servidor (avançado)" troca o endereço da API, para testar com o backend local.
  Ele aparece também na tela de erro (aberto quando o endereço não é o padrão); em
  branco, volta para a API publicada.
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
