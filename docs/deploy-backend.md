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

## Deploy automático pela main

O job `deploy-backend` em `.github/workflows/ci.yml` publica somente em um
`push` na `main` do repositório `mmenegazgabi/Pratica-em-ES-MDCA`, depois que
os três jobs de testes passarem. Um merge de PR na main gera esse push.
PRs e outras branches não publicam o backend. O job usa `Backend/` e seu
Dockerfile, preservando as variáveis e a política de acesso do serviço.
Não lê `Backend/.env` nem envia credenciais do banco/R2 pelo GitHub.

A autenticação usa Workload Identity Federation, sem chave JSON permanente:

- Conta de deploy: `mdca-github-deploy@pratica-em-es-mdca.iam.gserviceaccount.com`.
- Provider: `projects/547285598829/locations/global/workloadIdentityPools/mdca-github/providers/github-main`.
- Repositório autorizado: ID `1333555429`; proprietário: ID `177751658`.
- Condições: branch `refs/heads/main`, evento `push` e workflow
  `mmenegazgabi/Pratica-em-ES-MDCA/.github/workflows/ci.yml@refs/heads/main`.

Esses identificadores são públicos, não segredos; estão diretamente no
workflow. Não é necessário cadastrar `GCP_SA_KEY` ou copiar o `.env` para
GitHub Secrets. Forks e outro workflow não recebem essa autorização.
Renomear/mover o workflow ou trocar o proprietário do repositório exige
atualizar a condição do provider.

A conta de deploy tem `roles/run.sourceDeveloper` e
`roles/serviceusage.serviceUsageConsumer` no projeto, e
`roles/iam.serviceAccountUser` apenas na identidade atual do serviço:
`547285598829-compute@developer.gserviceaccount.com`.
O build continua usando a configuração existente do Cloud Build. A identidade
padrão de execução já tinha o papel Editor; este pipeline não altera essa
configuração herdada. Uma futura redução desses privilégios deve ser tratada
separadamente, com revisão do impacto no build e na execução.

Deploys são serializados pelo grupo de concorrência `cloud-run-production`.
Dentro dessa fila, `scripts/check-main-head.sh` consulta a main no GitHub:
se o commit testado já não for seu HEAD, a execução ignora autenticação e
publicação. Uma falha nessa consulta bloqueia o job. O checkout continua
no commit testado, sem substituir o código por uma versão ainda não testada.
Depois da publicação, `scripts/verify-backend.py` consulta `/health`, exige
HTTP 200 com `status: ok`, e repete a consulta em caso de falha transitória.
Uma falha nessa verificação deixa o job vermelho; não há rollback automático.
`/health` verifica a API, não substitui os testes de PostgreSQL/R2.

Para conferir a execução, abra GitHub → Actions → CI → Backend · Deploy no
Cloud Run e examine as etapas de autenticação, publicação e verificação.
A primeira execução real desse caminho só acontece após o workflow chegar
à main; validar YAML e testes localmente não prova a troca de tokens OIDC.

O deploy manual continua disponível para diagnóstico. Ele não tem a
restrição de branch do workflow e usa as configurações do `.env` local.
