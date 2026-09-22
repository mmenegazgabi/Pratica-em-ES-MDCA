# Pratica-em-ES-MDCA

Monorepo compartilhado entre o **Módulo Financeiro** e o **Módulo de Gestão**.
Cada módulo vive em sua própria subpasta de domínio dentro de `backend/` e
`frontend/`, e código comum aos dois fica em `shared/`.

## Estrutura

```
backend/
  financeiro/   # backend do Módulo Financeiro — dono: time Financeiro
  gestao/       # backend do Módulo de Gestão   — dono: time de Gestão
  shared/       # código de backend comum aos dois módulos
frontend/
  financeiro/   # frontend do Módulo Financeiro — dono: time Financeiro
  gestao/       # frontend do Módulo de Gestão   — dono: time de Gestão
  shared/       # código de frontend comum aos dois módulos
```

Regra geral: só mexa fora do seu domínio (`shared/` ou a pasta do outro
time) combinando antes com o time dono.

## Como rodar localmente

### Backend

Cada domínio de backend tem seu próprio `requirements.txt`. Exemplo para o
Financeiro (o mesmo vale para `backend/gestao`, trocando o caminho):

```bash
cd backend/financeiro
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Frontend

Cada domínio de frontend é servido de forma independente. Exemplo para o
Financeiro (o mesmo vale para `frontend/gestao`, trocando o caminho):

```bash
cd frontend/financeiro
python3 -m http.server 8080
# abrir http://localhost:8080
```

### Testes

```bash
# Financeiro
cd backend/financeiro && pip install -r requirements.txt && pytest

# Gestão
cd backend/gestao && pip install -r requirements.txt && pytest
```

## CI

O workflow em [.github/workflows/ci.yml](.github/workflows/ci.yml) roda os
testes de `backend/financeiro` e `backend/gestao` em jobs independentes, para
que uma alteração em um módulo não quebre o build do outro.


