# Pratica-em-ES-MDCA

Estrutura genérica para publicar o trabalho com:

- `frontend/`: site estático para Cloudflare Pages.
- `backend/`: API Python FastAPI para Google Cloud Run.
- Neon PostgreSQL configurado pela variável `DATABASE_URL`.
- Cloudflare R2 configurado para armazenar arquivos enviados pela API.

## Onde preencher as configurações

Para teste local, edite `backend/.env`:

```env
DATABASE_URL=postgresql://usuario:senha@ep-xxxx-pooler.regiao.aws.neon.tech/neondb?sslmode=require
APP_NAME=Pratica-em-ES-MDCA
R2_ACCOUNT_ID=COLE_AQUI_O_ACCOUNT_ID_DA_CLOUDFLARE
R2_ACCESS_KEY_ID=COLE_AQUI_O_ACCESS_KEY_ID_DO_R2
R2_SECRET_ACCESS_KEY=COLE_AQUI_O_SECRET_ACCESS_KEY_DO_R2
R2_BUCKET_NAME=mdca-arquivos
R2_PUBLIC_URL=https://pub-xxxxxxxxxxxxxxxxxxxx.r2.dev
```

Para deploy no Cloud Run, edite `backend/env-vars.yaml` com os mesmos valores reais.

No frontend, edite `frontend/app.js` e troque `API_BASE_URL` pela URL gerada pelo Cloud Run.

## Rodar backend localmente

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Endpoints disponíveis:

- `GET /health`: testa se a API está no ar.
- `GET /db/health`: testa conexão com o banco Neon.
- `GET /storage/health`: testa conexão com o bucket Cloudflare R2.
- `POST /files`: envia um arquivo genérico para o bucket R2.

## Deploy do backend

```bash
cd backend
gcloud run deploy mdca-backend --source . --region southamerica-east1 --allow-unauthenticated --env-vars-file env-vars.yaml
```

Copie a `Service URL` gerada pelo Cloud Run e cole em `frontend/app.js`.

## Deploy do frontend

No Cloudflare Pages:

- Framework preset: `None`
- Build command: vazio
- Build output directory: `frontend`

Arquivos com segredos (`backend/.env` e `backend/env-vars.yaml`) estão ignorados pelo Git.
