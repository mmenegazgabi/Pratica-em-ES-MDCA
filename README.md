# Pratica-em-ES-MDCA

Monorepo compartilhado entre o **Módulo Financeiro** e o **Módulo de Gestão**.
Cada módulo vive em sua própria subpasta de domínio dentro de `Backend/` e
`Frontend/`, e código comum aos dois fica em `Shared/`.

## Estrutura

```
Backend/
  Financeiro/   # backend do Módulo Financeiro — dono: time Financeiro
  Gestao/       # backend do Módulo de Gestão   — dono: time de Gestão
  Shared/       # código de backend comum aos dois módulos
Frontend/
  Financeiro/   # frontend do Módulo Financeiro — dono: time Financeiro
  Gestao/       # frontend do Módulo de Gestão   — dono: time de Gestão
  Shared/       # código de frontend comum aos dois módulos
```

Regra geral: só mexa fora do seu domínio (`Shared/` ou a pasta do outro
time) combinando antes com o time dono.

## Como rodar localmente

### Backend

Cada domínio de backend tem seu próprio `requirements.txt`. Exemplo para o
Financeiro (o mesmo vale para `Backend/Gestao`, trocando o caminho):

```bash
cd Backend/Financeiro
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Frontend

Cada domínio de frontend é servido de forma independente. Exemplo para o
Financeiro (o mesmo vale para `Frontend/Gestao`, trocando o caminho):

```bash
cd Frontend/Financeiro
python3 -m http.server 8080
# abrir http://localhost:8080
```

### Testes

```bash
# Financeiro
cd Backend/Financeiro && pip install -r requirements.txt && pytest

# Gestão
cd Backend/Gestao && pip install -r requirements.txt && pytest
```

## CI

O workflow em [.github/workflows/ci.yml](.github/workflows/ci.yml) roda os
testes de `Backend/Financeiro` e `Backend/Gestao` em jobs independentes, para
que uma alteração em um módulo não quebre o build do outro.


