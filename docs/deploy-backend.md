# Backend no Cloud Run

O deploy usa `Backend/` como contexto. `Backend/main.py` compõe a API:
os endpoints de infraestrutura ficam em `Backend/Shared/infra_api.py` e
as rotas financeiras continuam em `Backend/Financeiro/routers/`.
As regras financeiras da main foram preservadas; os imports foram ajustados
para permitir tanto os testes de domínio quanto a API integrada.

## Configuração local

Crie `Backend/.env` a partir de `Backend/.env.example` e preencha os valores
reais. Esse arquivo é ignorado pelo Git, pelo upload do Google Cloud e pelo
Docker. Não coloque chaves em arquivos do frontend.

`DATABASE_URL` mantém a conexão PostgreSQL existente. As quatro variáveis
`R2_*` obrigatórias identificam conta, credenciais S3 e bucket.
O token da API administrativa Cloudflare não é necessário para a API S3.
`R2_PUBLIC_URL` é opcional: em um bucket privado o upload retorna a chave
do objeto e `url: null`, sem inventar um endereço público.

`CORS_ORIGINS` contém as origens autorizadas separadas por vírgula.
O frontend publicado está em `https://mdca-sistema.pages.dev`.
Previews do Pages precisam de sua própria origem na configuração.

## Executar e testar

```bash
python3 -m venv .venv
.venv/bin/pip install -r Backend/requirements-dev.txt
.venv/bin/python -m pytest Backend
.venv/bin/python -m uvicorn main:app --app-dir Backend --env-file Backend/.env --reload --port 8080
```

Endpoints: `/health` verifica a API; `/db/health` verifica PostgreSQL;
`/storage/health` verifica o R2; `POST /files` recebe `arquivo` e `pasta`
como multipart; `/orcamentos` e `/orcamentos/{id}` expõem o domínio Financeiro.
O banco é consultado sob demanda, permitindo que a API inicie mesmo quando
uma dependência estiver indisponível. A antiga tabela de teste `app_metadata`
não é criada automaticamente durante o início do serviço.

Os orçamentos da implementação atual ficam em memória. A infraestrutura
PostgreSQL não altera essa regra: reiniciar o container perde esses registros,
e diferentes instâncias não compartilham esse armazenamento. O upload herdado
da infra ainda não implementa autenticação/RBAC; CORS não substitui autorização.

## Publicar

Com `gcloud` autenticado no projeto existente:

```bash
bash scripts/deploy-backend.sh
```

Padrões: projeto `pratica-em-es-mdca`, região `southamerica-east1`, serviço
`pratica-em-es-mdca`. Para outro destino use `GCP_PROJECT`, `GCP_REGION` e
`CLOUD_RUN_SERVICE`. O script preserva a política IAM atual e gera um arquivo
temporário de configuração que é removido ao terminar. As variáveis são
configuradas no serviço Cloud Run, não no código versionado.

O Pages continua publicando `Frontend/`, conforme a main. O painel técnico
herdado da infra fica em `Frontend/Shared/infra-smoke.html` para verificar a
comunicação frontend/API; ele não substitui a página inicial da plataforma.
