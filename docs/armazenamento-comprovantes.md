# Armazenamento de comprovantes (T-11 · US-03)

Os comprovantes de despesa (fotos e PDFs) ficam no bucket **privado**
`mdca-arquivos` do Cloudflare R2, na pasta `comprovantes/`. O navegador nunca
acessa o R2 diretamente: todo envio e toda leitura passam pela API no Cloud Run,
que exige autenticação.

```
Navegador ──(Bearer token)──► API Cloud Run ──(credenciais S3 do R2)──► R2 privado
                                                                       comprovantes/AAAA/MM/<uuid>.<ext>
Navegador ───────────── URL direta do R2, sem assinatura ─────────────► negado (4xx)
```

## Rotas

| Rota | O que faz | Autenticação |
|---|---|---|
| `POST /comprovantes` | Recebe `arquivo` (multipart) e salva no R2. Devolve `chave` e `url` (caminho da API). | Obrigatória |
| `GET /comprovantes/{ano}/{mes}/{arquivo}` | Devolve o arquivo pela API, com `Cache-Control: private, no-store`. | Obrigatória |

Regras do upload:

- Tipos aceitos: JPG, PNG, WEBP, HEIC e PDF. O tipo é detectado pelo conteúdo do
  arquivo (assinatura dos primeiros bytes), não pela extensão nem pelo
  `Content-Type` enviado pelo navegador.
- Tamanho máximo: **5 MB** por arquivo (acima disso: HTTP 413).
- A chave é gerada pelo servidor (`comprovantes/AAAA/MM/<uuid>.<ext>`). O nome
  original vai só nos metadados, limpo para ASCII.
- A leitura só aceita chaves nesse formato, então a rota não lê arquivos de
  outras pastas do bucket (como os documentos da Gestão).

## Lançamento com comprovante (T-12)

`POST /lancamentos` cria a despesa e envia o comprovante no mesmo pedido
(`multipart/form-data`), com autenticação obrigatória:

| Campo | Tipo | Regra |
|---|---|---|
| `orcamento_id` | texto | orçamento existente (senão 404) |
| `valor` | número | maior que zero |
| `descricao` | texto | 1 a 200 caracteres |
| `categoria` | texto | uma das `categorias_despesa` do orçamento |
| `data_despesa` | data (AAAA-MM-DD) | dentro da vigência do orçamento |
| `comprovante` | arquivo | **obrigatório**; mesmas regras de tipo e tamanho acima |

- Sem comprovante: HTTP 400 `"Comprovante obrigatório."`.
- Lançamento válido: HTTP 201 com `status: "pendente"` e
  `status_descricao: "Pendente de aprovação"`. Pendente não altera o saldo;
  só a aprovação (T-07) debita.
- Os dados são validados **antes** do envio ao R2, para não deixar arquivo
  sem lançamento no bucket.

Exemplo:

```bash
curl -X POST https://<api>/lancamentos \
  -H "Authorization: Bearer $FINANCEIRO_API_TOKEN" \
  -F orcamento_id=<id> -F valor=150.75 -F descricao="Lanche da oficina" \
  -F categoria=materiais -F data_despesa=2026-10-10 \
  -F comprovante=@nota.jpg
```

## Consultar e rejeitar lançamento (T-16)

| Rota | Quem pode | O que faz |
|---|---|---|
| `GET /lancamentos/{id}` | qualquer usuário autenticado | Devolve `status`, `status_descricao`, `motivo_rejeicao` e `comprovante_url`. É onde quem lançou vê o motivo. |
| `PATCH /lancamentos/{id}/rejeitar` | `coordenacao` ou `direcao` (cabeçalho `X-Papel-Usuario`, como na T-15) | Corpo JSON `{"motivo": "..."}`. Só lançamento **pendente** pode ser rejeitado. |

- Sem motivo (sem corpo, `{}`, `null`, vazio ou só espaços): HTTP 400
  `"Motivo da rejeição é obrigatório."`. Máximo de 500 caracteres.
- Com motivo: HTTP 200 com `status: "rejeitado"`, `status_descricao: "Rejeitado"`,
  `motivo_rejeicao` e `saldo_orcamento` (mesmo formato da aprovação da T-15).
- Aprovado ou já rejeitado: HTTP 409; o motivo original é mantido.
- A rejeição **não altera o saldo**, e um lançamento rejeitado não pode mais ser aprovado.

## Autenticação (provisória até a US-08)

Enquanto não existe login de usuários, as rotas exigem um token de serviço:

```
Authorization: Bearer <FINANCEIRO_API_TOKEN>
```

- O valor fica na variável de ambiente `FINANCEIRO_API_TOKEN` do Cloud Run e no
  `Backend/.env` local. **Nunca no repositório nem no frontend publicado.**
- Sem a variável configurada, as rotas respondem 503: a API falha fechada.
- Quando a US-08 existir, só o corpo de `Backend/Financeiro/autenticacao.py`
  muda para validar o usuário logado. As rotas continuam iguais.

Gerar um token:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Configurar no Cloud Run (uma vez): Console do Google Cloud → Cloud Run →
`pratica-em-es-mdca` → **Editar e implantar nova revisão** → **Variáveis e
secrets** → adicionar `FINANCEIRO_API_TOKEN` → **Implantar**. O deploy
automático da `main` preserva as variáveis existentes. O deploy manual
(`scripts/deploy-backend.sh`) lê a variável do `Backend/.env`.

Na documentação interativa (`/docs`), use o botão **Authorize** e cole o token.

## Verificação dos critérios de aceitação

| Critério | Como é garantido | Evidência |
|---|---|---|
| Upload concluído fica acessível apenas via API autenticada | Bucket privado; rotas `/comprovantes` com `Bearer` obrigatório | `Backend/Financeiro/tests/test_comprovantes.py` + `scripts/verify-comprovantes.py` |
| Acesso direto à URL do arquivo sem autenticação é negado | Bucket sem acesso público (sem `r2.dev` e sem domínio público); a API devolve só o caminho da API, nunca a URL do R2 | `scripts/verify-comprovantes.py` (passo "Acesso direto") + print do painel do R2 com **Public access: Disabled** |
| Custo dentro da camada gratuita | Limite de 5 MB, só tipos de comprovante, upload só autenticado | Estimativa abaixo + painel de métricas do R2 |

Rodar a verificação contra o ambiente publicado (não precisa das chaves
secretas do R2):

```bash
FINANCEIRO_API_TOKEN=... R2_ACCOUNT_ID=... R2_BUCKET_NAME=mdca-arquivos \
  python scripts/verify-comprovantes.py https://<url-do-cloud-run>
```

Saída esperada: cinco linhas `[OK]`, incluindo
"Acesso direto à URL do arquivo no R2, sem assinatura, é negado".

## Custo: camada gratuita do R2

Camada gratuita mensal do R2 (armazenamento Standard), segundo a
[página de preços da Cloudflare](https://developers.cloudflare.com/r2/pricing/),
consultada em outubro de 2026:

| Recurso | Grátis por mês | Uso por comprovante |
|---|---|---|
| Armazenamento | 10 GB-mês | até 5 MB (foto de celular costuma ter de 1 a 3 MB) |
| Operações Classe A (`PutObject`, `ListObjects`) | 1 milhão | 1 por upload |
| Operações Classe B (`GetObject`, `HeadObject`) | 10 milhões | 1 por visualização |
| Saída de dados (egress) | gratuita | — |

Estimativa com média de 2 MB por comprovante: 10 GB comportam cerca de
**5.000 comprovantes**. Com 200 lançamentos por mês, o armazenamento chega
a 10 GB em pouco mais de 2 anos. As operações ficam muito abaixo do limite.

Para manter isso:

- O formulário de lançamento (T-13) pode reduzir a foto no navegador antes de
  enviar (ex.: 1600 px, JPEG 80%), o que costuma deixar cada foto abaixo de 500 KB.
- A camada gratuita vale só para a classe **Standard**. Não mude o bucket para
  *Infrequent Access*.
- Conferir uma vez por mês em Cloudflare → R2 → `mdca-arquivos` → **Metrics**.

## Pendências fora desta task

- **`POST /files` (em `Backend/Shared/infra_api.py`) continua sem autenticação**
  e grava no mesmo bucket. Ele não permite ler arquivos, mas qualquer pessoa
  pode encher o bucket, o que ameaça a camada gratuita. Como `Shared/` é dos dois
  grupos, proteger ou remover essa rota precisa ser combinado com o Grupo 2.
- A troca do token de serviço pelo login de usuários fica com a US-08.
- Apagar o comprovante de um lançamento excluído fica com as tasks de lançamentos.
