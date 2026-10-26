# Lançamento de despesa no celular (T-13 · US-03)

Tela do educador para lançar uma despesa com a foto do comprovante.

- Endereço publicado: `https://mdca-sistema.pages.dev/Financeiro/lancamento/`
- Arquivos: `Frontend/Financeiro/lancamento/` (`index.html`, `lancamento.css`,
  `lancamento.js`, `formulario.js`, `api.js`)
- Testes: `cd Frontend/Financeiro && node --test`

## Como funciona

1. **Código de acesso (provisório até a US-08).** Na primeira vez, a tela pede o
   código de acesso do Financeiro (`FINANCEIRO_API_TOKEN`). Ele fica salvo só
   naquele aparelho (`localStorage`) e não vai para o código, porque o
   repositório é público. O botão ⚙ permite trocar ou remover o código.
2. **Projeto e categoria** vêm de `GET /orcamentos?vigentes_em=<hoje>`: só
   aparecem orçamentos vigentes, e a categoria depende do projeto escolhido.
3. **Comprovante:** "Fotografar comprovante" abre direto a câmera traseira
   (`capture="environment"`); "Escolher da galeria ou arquivo" abre a galeria
   ou os arquivos (foto ou PDF). Fotos grandes são reduzidas no próprio celular
   (maior lado com 1600 px, JPEG) antes do envio, para respeitar o limite de
   5 MB e a camada gratuita do R2.
4. **Envio:** `POST /lancamentos` (T-12). Ao concluir, aparece a confirmação
   "Lançamento enviado · Pendente de aprovação" com o resumo.

## Celular

- Campos com fonte de 16 px (o iPhone não dá zoom ao tocar) e área de toque de
  pelo menos 44 px.
- Testado com Playwright em 390 px (iPhone 13) e 320 px: sem rolagem
  horizontal e todos os campos obrigatórios visíveis.

## Testar com o backend local

1. Suba a API na porta 8000, com o frontend liberado no CORS:
   `CORS_ORIGINS=http://localhost:8080 python -m uvicorn main:app --app-dir Backend --env-file Backend/.env --port 8000`
2. Em outro terminal, sirva o frontend: `cd Frontend && python -m http.server 8080`.
3. Abra `http://localhost:8080/Financeiro/lancamento/`, informe o código de
   acesso e, em "Servidor (avançado)", o endereço `http://localhost:8000`.
