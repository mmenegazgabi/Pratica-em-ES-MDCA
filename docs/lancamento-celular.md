# Despesas no celular do educador

"Fotografa agora, completa depois" (redesign do Financeiro, visual B — esboço
em `docs/superpowers/specs/2026-10-27-redesign-financeiro/telas-celular.html`).

- Endereço publicado: `https://mdca-sistema.pages.dev/Financeiro/lancamento/`
- Arquivos: `Frontend/Financeiro/lancamento/` (`index.html`, `lancamento.css`,
  `lancamento.js`, `despesas-dados.js`, `formulario.js`) e `Frontend/Financeiro/base/`
- Testes: `cd Frontend/Financeiro && node --test`

## Telas

Uma página só; as telas trocam pelo endereço depois do `#`. Barra inferior:
Despesas, Avisos, Perfil.

1. **Entrada.** O app usa a sessão do login único (`mdca.sessao`, veja
   `docs/login.md`). Sem sessão, a página volta para a página inicial, onde a pessoa
   entra ou faz o primeiro acesso. Aqui o papel é sempre `educador`, guardado só na
   memória da página: entrar no celular não troca o papel de trabalho do computador
   no mesmo navegador. A pessoa precisa ter o papel educador. Sessão vencida ou
   pessoa desativada também voltam para a página inicial. O servidor (avançado) é o
   da página inicial.
2. **Minhas despesas** (`#/`). Botão "Fotografar comprovante" e, de cima para baixo:
   **Precisa de ajuste** (rejeitadas), **A completar** (fotos sem dados, com
   miniatura e horário) e **Enviadas** (as 5 mais recentes; "Ver todas" mostra o resto).
3. **Câmera.** "Fotografar comprovante" abre direto a câmera traseira
   (`capture="environment"`); "Escolher da galeria ou arquivo" abre a galeria
   (foto ou PDF). Fotos grandes são reduzidas no celular (maior lado com 1600 px,
   JPEG) e vão para `POST /rascunhos`. Aparece o aviso "Foto salva em "A completar""
   com "Completar agora".
4. **Completar despesa** (`#/completar/<rascunho>`). Uma tela: foto, valor, projeto,
   categoria (botões com as categorias do orçamento escolhido), "O que foi comprado"
   e data. A data vem da foto (fuso do aparelho) e o projeto lembra o da última
   despesa. "Enviar para aprovação" chama `POST /rascunhos/{id}/completar`.
5. **Despesa** (`#/despesa/<lançamento>`). Valor, status, foto e descrição. Se foi
   rejeitada, o motivo da coordenação aparece em destaque com "Corrigir e reenviar",
   que abre o mesmo formulário já preenchido (`#/corrigir/<lançamento>`, com
   "Trocar foto") e chama `PATCH /lancamentos/{id}/reenviar`.
6. **Avisos** (`#/avisos`). `GET /notificacoes`; ao abrir, as novas são marcadas
   como lidas.
7. **Perfil** (`#/perfil`). Nome e e-mail da sessão e "Sair" (encerra a sessão da
   plataforma).

Os comprovantes só saem da API com o token da sessão; a tela baixa a imagem
com os cabeçalhos e mostra pelo endereço local do navegador (`blob:`).

## Celular

- Campos com fonte de 16 px (o iPhone não dá zoom ao tocar) e área de toque de
  pelo menos 44 px.
- Verificado com Playwright em 390 px e 320 px: sem rolagem horizontal.

## Testar com o backend local

1. Os comprovantes vão para o Cloudflare R2; sem as variáveis `R2_*` a API
   responde 503 ao receber fotos. Para testar sem R2, suba a API com o
   armazenamento em memória dos testes, num arquivo fora do repositório:

   ```python
   # app_local.py
   from main import app
   from Financeiro.comprovantes import ArmazenamentoEmMemoria
   from Financeiro.routers.comprovantes import obter_armazenamento
   _memoria = ArmazenamentoEmMemoria()
   app.dependency_overrides[obter_armazenamento] = lambda: _memoria
   ```

   `cd Backend && DATABASE_URL=postgresql://localhost/mdca_local FINANCEIRO_API_TOKEN=dev CORS_ORIGINS=http://localhost:8090 PYTHONPATH=.:<pasta do app_local.py> .venv/bin/python -m uvicorn app_local:app --port 8080`
2. Em outro terminal, sirva o frontend: `cd Frontend && python3 -m http.server 8090`.
3. Crie a administradora e as pessoas (educador e coordenação) como em
   `docs/login.md`, e cadastre um projeto e um orçamento como coordenação.
4. Abra `http://localhost:8090/`, entre como educador (servidor `http://localhost:8080`
   em "Servidor (avançado)") e abra o Financeiro em tela de celular.
